"""One-relation extractor: COVERS_CHAIN（News → IndustryChain）.

复刻旧 load_industry_chain_graph.py 口径：dwd_industry_chain_news_info，
news_id + chain_code 均非空即建边，属性 (source_table, ingest_batch, ingest_time)，
rank@0。News 顶点由 news_entity.py 先行写入。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
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


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=[("dwd_industry_chain_news_info", SQL, covers_chain)],
        )
    )


if __name__ == "__main__":
    main()
