"""One-entity transform for DataSource metadata（平台喂数抽取：脚本只输出实体 JSON）。

39 张机构域表的目录点，VID 为 ``ds_{table}``，仅 4 个目录属性（无溯源字段）。
目录为静态内容、与行无关：绑定一个占位查询（单行），transform 忽略 rows。
"""

from typing import Any

from script.entity_extractors_one_entity.common import EntityRecord, datasource_vid
from script.entity_extractors_one_entity.org_catalog import TABLE_CN_NAMES
from script.extract_transform_common import entity_transform

SOURCES = [{"table": "placeholder", "pk": "id", "time": "", "query_sql": "SELECT 1 AS id"}]


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


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：静态目录 → {"entities": [...]}。"""
    return entity_transform(payload, builder=lambda table, row, batch: datasource_records())
