"""One-entity extractor for IndustryChain.

复刻旧 load_industry_chain_graph.py 口径：同一 chain_code 的首个链名胜出
（setdefault 语义，dedupe="first"）。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import industry_chain_record


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sql = "SELECT * FROM dwd_industry_chain_info ORDER BY id"
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=[("dwd_industry_chain_info", sql, industry_chain_record)],
            dedupe="first",
        )
    )


if __name__ == "__main__":
    main()
