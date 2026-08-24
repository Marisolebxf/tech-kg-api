"""One-entity extractor for IndustryNode."""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import industry_node_record


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sql = "SELECT * FROM dwd_industry_chain_info ORDER BY node_id"
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=[("dwd_industry_chain_info", sql, industry_node_record)],
        )
    )


if __name__ == "__main__":
    main()
