"""One-entity transform for PatentFamily（平台喂数抽取：脚本只输出实体 JSON）。

复用专利聚合 SQL（PATENT_QUERY_SQL），族号缺失不建点；溯源表名与旧口径一致
（dwd_patent）。MEMBER_OF_FAMILY 边由关系脚本承接。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import patent_family_record
from script.entity_extractors_one_entity.patent_entity import PATENT_QUERY_SQL
from script.extract_transform_common import entity_transform

SOURCES = [
    {
        "table": "dwd_patent",
        "pk": "source_row_id",
        "time": "update_time",
        "query_sql": PATENT_QUERY_SQL,
    },
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=patent_family_record)
