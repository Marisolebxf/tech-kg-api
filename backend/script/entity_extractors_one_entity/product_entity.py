"""One-entity transform for Product（平台喂数抽取：脚本只输出实体 JSON）。

从全部 Organization 表的行内 main_prod/main_products/tech_product 抽取主营产品
（缺机构 ID 的行不建 Product），VID 为规范化产品名的完整 32 位 md5。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import product_record
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES
from script.extract_transform_common import entity_transform

SOURCES = [{"table": t, "pk": "id", "time": "update_time"} for t in ORGANIZATION_TABLES]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=product_record)
