"""One-entity extractor for PatentFamily.

复用专利聚合 SQL（keyset 游标分页），族号缺失不建点；溯源表名与旧口径一致
（dwd_patent_family）。MEMBER_OF_FAMILY 边由关系脚本承接。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import patent_family_record
from script.entity_extractors_one_entity.patent_entity import PATENT_SQL


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = [("dwd_patent", PATENT_SQL, patent_family_record)]
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=sources,
            cursor_column="source_row_id",
        )
    )


if __name__ == "__main__":
    main()
