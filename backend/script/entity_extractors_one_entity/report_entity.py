"""One-entity transform for Report（平台喂数抽取：脚本只输出实体 JSON）。"""

from typing import Any

from script.entity_extractors_one_entity.mappers import report_record
from script.extract_transform_common import entity_transform

SOURCES = [
    {"table": "dwd_zh_report", "pk": "report_id", "time": "update_time"},
    {"table": "dwd_en_report", "pk": "report_id", "time": "update_time"},
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=report_record)
