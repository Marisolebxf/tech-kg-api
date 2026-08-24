"""One-entity extractor for DataSource metadata.

复刻旧 organization_entity_etl.datasource_records 口径：39 张机构域表的目录点，
VID 为 ``ds_{table}``，仅 4 个目录属性（无溯源字段）。
"""

from script.entity_extractors_one_entity.common import (
    EntityRecord,
    build_parser,
    configure_logging,
    datasource_vid,
    print_json,
    write_records,
)
from script.entity_extractors_one_entity.org_catalog import TABLE_CN_NAMES


def datasource_records() -> list[EntityRecord]:
    records: list[EntityRecord] = []
    for table, cn_name in sorted(TABLE_CN_NAMES.items()):
        library = (
            "国外机构要素库" if table.startswith(("dwd_forg_", "dwd_en_")) else "国内机构要素库"
        )
        records.append(
            EntityRecord(
                "DataSource",
                datasource_vid(table),
                {
                    "source_table": table,
                    "table_cn_name": cn_name,
                    "tier": "DWD",
                    "library": library,
                },
            )
        )
    return records


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    records = datasource_records()
    if args.limit:
        records = records[: args.limit]
    print_json(write_records(records, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
