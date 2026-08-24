"""One-relation extractor: AUTHORED_BY（Paper → Person，论文工作流口径）.

复刻旧 paper_journal_chain_etl.py：dwd_zh/en_author，paper 端去 ``__数字``
后缀，author_id 非空；边属性 (author_order, is_corresponding, confidence=1.0)，
rank@0。Person 顶点由 person_entity.py --source paper-author 先行写入。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.authored_by_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from typing import Any

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import paper_source_id

TABLES = ("dwd_zh_author", "dwd_en_author")


def authored_by(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("paper_id"))
    aid = str(row.get("author_id")) if row.get("author_id") else ""
    if not pid or not aid:
        return []
    return [
        EdgeRecord(
            "AUTHORED_BY",
            f"paper_{pid}",
            f"person_{aid}",
            {
                "author_order": str(row.get("author_sequence"))
                if row.get("author_sequence") is not None
                else "",
                "is_corresponding": str(row.get("correspond"))
                if row.get("correspond") is not None
                else "",
                "confidence": 1.0,
            },
            rank=0,
        )
    ]


def build_sources(payload: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """从 payload dict 构造 sources；CLI vars(args) 与 workflow payload 同形态。"""
    table_choice = payload.get("table", "all")
    tables = TABLES if table_choice == "all" else (table_choice,)
    return [
        (table, f"SELECT * FROM {table} ORDER BY paper_id, author_id", authored_by)
        for table in tables
    ]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources(vars(args))
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
    sources = build_sources(payload)
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
