"""One-relation extractor: AFFILIATED_WITH（Person → Organization）.

复刻旧 load_scholar_relations.py 口径：dwd_scholar（status=1），机构端优先
``scholar_org_id`` 直连（confidence=1.0），否则机构名 md5 16 位桩 VID
（confidence=0.6，桩顶点可不存在，后续由 SAME_AS 对齐认领）；
REST merge_edge 按 source_record_id 幂等。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.affiliated_with_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

import hashlib
from typing import Any

from sqlalchemy import text

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    ensure_edge_schema,
    graph_client,
    mysql_engine,
    now_utc,
    print_json,
    run_relation_extractor,
)

# 旧 ensure_schema 补齐的边属性（类型与 dwd_scholar 源一致）。
EDGE_SCHEMA = {
    "affiliation_name": "string",
    "work_experience_date": "string",
    "work_experience_department_zh": "string",
    "work_experience_position_zh": "string",
    "source": "string",
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
    "organization_base": "string",
    "organization_id": "string",
    "confidence": "double",
    "match_method": "string",
    "match_evidence": "string",
}

_PROBE_COLUMNS = (
    "scholar_org_id",
    "work_experience_date",
    "work_experience_department_zh",
    "work_experience_position_zh",
    "scholar_org_name_zh",
    "scholar_org_name_en",
)


def _org_vid(scholar_org_id: str | None, org_name: str | None) -> str | None:
    """旧 org_vid：优先机构 ID，否则机构名小写 md5 前 16 位桩。"""
    if scholar_org_id and scholar_org_id.strip():
        return f"org_{scholar_org_id.strip()}"
    if org_name and org_name.strip():
        key = org_name.strip().lower()
        return f"org_{hashlib.md5(key.encode('utf-8')).hexdigest()[:16]}"
    return None


def affiliated_with(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    sid = str(row.get("scholar_id") or "").strip()
    org_name = str(row.get("scholar_org_name_zh") or row.get("scholar_org_name_en") or "")
    dst = _org_vid(str(row.get("scholar_org_id")) if row.get("scholar_org_id") else None, org_name)
    if not sid or not dst:
        return []
    has_org_id = bool(row.get("scholar_org_id") and str(row.get("scholar_org_id")).strip())
    if has_org_id:
        confidence = 1.0
        method = "source_org_id"
        evidence = "dwd_scholar.scholar_org_id 直接指向机构，无需名称推断"
    else:
        confidence = 0.6
        method = "org_name_md5_placeholder"
        evidence = (
            "源表无 scholar_org_id，机构顶点按机构名 md5 生成桩 VID，待正式 Organization 落地后对齐"
        )
    props = {
        "affiliation_name": org_name,
        "work_experience_date": row.get("work_experience_date") or "",
        "work_experience_department_zh": row.get("work_experience_department_zh") or "",
        "work_experience_position_zh": row.get("work_experience_position_zh") or "",
        "source": "scholar",
        "source_table": "dwd_scholar",
        "source_record_id": sid,
        "ingest_batch": batch,
        "ingest_time": now_utc(),
        "organization_base": "dwd_scholar" if has_org_id else "",
        "organization_id": str(row.get("scholar_org_id") or "").strip(),
        "confidence": confidence,
        "match_method": method,
        "match_evidence": evidence,
    }
    return [
        EdgeRecord(
            "AFFILIATED_WITH",
            f"person_{sid}",
            dst,
            props,
            identity={"source_record_id": sid},
            # 桩端点允许悬空（旧口径不做端点验存）。
            validate_endpoints=False,
        )
    ]


def _build_sql(engine) -> str:
    """新列缺失的环境用 NULL AS 兜底（旧 _has_dwd_scholar_column 口径）。"""
    with engine.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = 'dwd_scholar'"
                )
            )
        }
    columns = ["scholar_id"] + [
        col if col in existing else f"NULL AS {col}" for col in _PROBE_COLUMNS
    ]
    select = ", ".join(columns)
    return f"SELECT {select} FROM dwd_scholar WHERE status = 1 ORDER BY scholar_id"


def build_sources(database: str) -> list[tuple[str, str, Any]]:
    """构造 sources；需先连 MySQL 动态探测列后构造 SQL（旧 _build_sql 口径）。

    传入 database 是为了 workflow 与 main 都能从 ``mysql_engine(database)`` 拿 engine
    并在用完后 dispose（与原 main 行为一致）。CLI vars(args) 与 workflow payload
    形态都带 ``database`` 字段，故可作为统一入口。
    """
    engine = mysql_engine(database)
    try:
        sql = _build_sql(engine)
    finally:
        engine.dispose()
    return [("dwd_scholar", sql, affiliated_with)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    if not args.dry_run:
        graph = graph_client()
        try:
            ensure_edge_schema(graph, "AFFILIATED_WITH", EDGE_SCHEMA)
        finally:
            graph.close()
    sources = build_sources(args.database)
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=sources,
        )
    )


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    if not common["dry_run"]:
        graph = graph_client()
        try:
            ensure_edge_schema(graph, "AFFILIATED_WITH", EDGE_SCHEMA)
        finally:
            graph.close()
    sources = build_sources(common["database"])
    return run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        since=common["since"],
        sources=sources,
    )


if __name__ == "__main__":
    main()
