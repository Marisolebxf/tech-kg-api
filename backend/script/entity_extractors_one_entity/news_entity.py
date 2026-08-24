"""One-entity extractor for News.

两个来源分别复刻旧脚本口径：

- ``dwd_org_important_news_info``：旧 organization_entity_etl.py
  （VID 含表名 + 整行哈希稳定键，动态置信度）。
- ``dwd_industry_chain_news_info``：旧 load_industry_chain_graph.py
  （news_{news_id}，缺 news_id 跳过，release_date 取源表 relaese_date 列）。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import news_chain_record, news_org_record

TABLES = ("dwd_org_important_news_info", "dwd_industry_chain_news_info")

MAPPER_BY_TABLE = {
    "dwd_org_important_news_info": news_org_record,
    "dwd_industry_chain_news_info": news_chain_record,
}


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = TABLES if args.table == "all" else (args.table,)
    sources = [
        (table, f"SELECT * FROM {table} ORDER BY 1", MAPPER_BY_TABLE[table]) for table in tables
    ]
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=sources,
        )
    )


if __name__ == "__main__":
    main()
