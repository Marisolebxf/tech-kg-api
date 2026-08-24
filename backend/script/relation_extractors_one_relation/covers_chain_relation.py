"""One-relation extractor: COVERS_CHAIN（News → IndustryChain）.

复刻旧 load_industry_chain_graph.py 口径：dwd_industry_chain_news_info，
news_id + chain_code 均非空即建边，属性 (source_table, ingest_batch, ingest_time)，
rank@0。News 顶点由 news_entity.py 先行写入。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.covers_chain_relation --dry-run --limit 1``
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

SQL = "SELECT * FROM dwd_industry_chain_news_info ORDER BY news_id"


def covers_chain(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    news_id = str(row.get("news_id") or "").strip()
    chain_code = str(row.get("chain_code") or "").strip()
    if not news_id or not chain_code:
        return []
    return [
        EdgeRecord(
            "COVERS_CHAIN",
            f"news_{news_id}",
            f"chain_{chain_code}",
            {
                "source_table": table,
                "ingest_batch": batch,
                "ingest_time": now_utc(),
            },
            rank=0,
        )
    ]


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_industry_chain_news_info", SQL, covers_chain)]


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
