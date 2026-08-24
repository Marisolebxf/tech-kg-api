"""One-entity extractor for Product.

复刻旧 organization_entity_etl.py 口径：从全部 10 张 Organization 表的行内
main_prod/main_products/tech_product 抽取主营产品（缺机构 ID 的行不建 Product），
VID 为规范化产品名的完整 32 位 md5。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import product_record
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *ORGANIZATION_TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = ORGANIZATION_TABLES if args.table == "all" else (args.table,)
    sources = [(table, f"SELECT * FROM {table} ORDER BY 1", product_record) for table in tables]
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
