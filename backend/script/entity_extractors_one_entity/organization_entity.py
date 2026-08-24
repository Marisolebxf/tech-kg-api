"""One-entity extractor for Organization.

表集合与字段映射复刻旧 organization_entity_etl.py（含 dwd_org_stock_base 在内
的 10 张 Organization 表；enrichment 表稀疏行只下发非空字段）。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import organization_record
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *ORGANIZATION_TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = ORGANIZATION_TABLES if args.table == "all" else (args.table,)
    sources = [
        (table, f"SELECT * FROM {table} ORDER BY 1", organization_record) for table in tables
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
