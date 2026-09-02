"""One-entity transform for IndustryChain（平台喂数抽取：脚本只输出实体 JSON）。

同一 chain_code 的首个链名胜出（setdefault 语义，dedupe="first"——由图库
merge 幂等保证）。上游表无 update_time，走 pk keyset 增量（time 留空）。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import industry_chain_record
from script.extract_transform_common import entity_transform

SOURCES = [
    {"table": "dwd_industry_chain_info", "pk": "chain_code", "time": ""},
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=industry_chain_record)
