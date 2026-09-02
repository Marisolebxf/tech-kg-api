"""One-entity transform for Event（平台喂数抽取：脚本只输出实体 JSON）。"""

from typing import Any

from script.entity_extractors_one_entity.mappers import event_record
from script.entity_extractors_one_entity.org_catalog import EVENT_TABLES
from script.extract_transform_common import entity_transform

SOURCES = [{"table": t, "pk": "id", "time": "update_time"} for t in EVENT_TABLES]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=event_record)
