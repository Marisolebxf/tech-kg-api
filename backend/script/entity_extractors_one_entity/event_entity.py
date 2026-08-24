"""One-entity extractor for Event.

表集合、复合稳定键与字段候选链复刻旧 organization_entity_etl.py
（含 dwd_org_bankruptcy_public_cases，不含只用于关系的 _list 当事人表）。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import event_record
from script.entity_extractors_one_entity.org_catalog import EVENT_TABLES


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *EVENT_TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = EVENT_TABLES if args.table == "all" else (args.table,)
    sources = [(table, f"SELECT * FROM {table} ORDER BY 1", event_record) for table in tables]
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
