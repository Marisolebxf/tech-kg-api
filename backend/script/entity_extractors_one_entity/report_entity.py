"""One-entity extractor for Report（论文工作流旧口径，支持 --since 增量）。"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import report_record

TABLES = ("dwd_zh_report", "dwd_en_report")


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = TABLES if args.table == "all" else (args.table,)
    sources = [
        (table, f"SELECT * FROM {table} ORDER BY report_id", report_record) for table in tables
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
