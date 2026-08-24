"""One-relation extractor: AUTHORED_BY（Paper → Person，学者域跨域兜底）.

复刻旧 load_scholar_relations.load_authored_by_fallback 口径：
dwd_scholar_paper_relation（status=1），两端顶点在图中均已存在才写边
（写层端点验存），confidence=0.9（cross_domain_id_match）。
paper 端 VID 用原始 paper_id（与 Paper 实体 VID 一致，不去 ``__数字`` 后缀）。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.authored_by_fallback_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    now_utc,
    print_json,
    run_relation_extractor,
)

SQL = (
    "SELECT paper_id, scholar_id, citations FROM dwd_scholar_paper_relation "
    "WHERE status = 1 ORDER BY paper_id, scholar_id"
)


def authored_by_fallback(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    paper_id = str(row.get("paper_id") or "").strip()
    scholar_id = str(row.get("scholar_id") or "").strip()
    if not paper_id or not scholar_id:
        return []
    record_id = f"{paper_id}_{scholar_id}"
    props = {
        "citations": int(row.get("citations") or 0),
        "source_table": table,
        "source_record_id": record_id,
        "ingest_batch": batch,
        "ingest_time": now_utc(),
        "confidence": 0.9,
        "match_method": "cross_domain_id_match",
        "match_evidence": "paper_id 与 scholar_id 分别命中已存在的 Paper、Person 顶点",
    }
    return [
        EdgeRecord(
            "AUTHORED_BY",
            f"paper_{paper_id}",
            f"person_{scholar_id}",
            props,
            identity={"source_record_id": record_id},
            source_tag="Paper",
            target_tag="Person",
        )
    ]


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_scholar_paper_relation", SQL, authored_by_fallback)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources()
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


def workflow(payload: dict) -> dict:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources()
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
