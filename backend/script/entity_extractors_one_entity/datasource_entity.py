"""One-entity extractor for DataSource metadata.

复刻旧 organization_entity_etl.datasource_records 口径：39 张机构域表的目录点，
VID 为 ``ds_{table}``，仅 4 个目录属性（无溯源字段）。

Dual-mode 入口：
- CLI: ``python -m script.entity_extractors_one_entity.datasource_entity --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from script.entity_extractors_one_entity.common import (
    EntityRecord,
    build_parser,
    common_args_from_payload,
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


def _limited_records(payload: dict) -> list[EntityRecord]:
    records = datasource_records()
    limit = payload.get("limit")
    if limit:
        records = records[: int(limit)]
    return records


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    records = _limited_records(vars(args))
    print_json(write_records(records, dry_run=args.dry_run))


def workflow(payload: dict) -> dict:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    records = _limited_records(payload)
    return write_records(records, dry_run=common["dry_run"])


if __name__ == "__main__":
    main()
