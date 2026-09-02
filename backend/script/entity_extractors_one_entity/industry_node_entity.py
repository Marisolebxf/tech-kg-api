"""One-entity transform for IndustryNode（平台喂数抽取：脚本只输出实体 JSON）。

上游表无 update_time，走 pk keyset 增量（time 留空）。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import industry_node_record
from script.extract_transform_common import entity_transform

SOURCES = [
    {"table": "dwd_industry_chain_info", "pk": "node_id", "time": ""},
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=industry_node_record)
