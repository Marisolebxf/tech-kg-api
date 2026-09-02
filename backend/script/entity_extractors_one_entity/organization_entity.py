"""One-entity transform for Organization（平台喂数抽取：脚本只输出实体 JSON）。

表集合与字段映射复刻旧 organization_entity_etl.py（含 dwd_org_stock_base 在内
的 Organization 表；enrichment 表稀疏行只下发非空字段）。同名冲突检测/人工
对齐裁决由平台在写图后统一执行（消歧）。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import organization_record
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES
from script.extract_transform_common import entity_transform

SOURCES = [{"table": t, "pk": "id", "time": "update_time"} for t in ORGANIZATION_TABLES]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=organization_record)
