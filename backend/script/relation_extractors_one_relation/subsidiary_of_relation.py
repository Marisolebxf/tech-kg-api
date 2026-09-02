"""One-relation transform for SUBSIDIARY_OF（子公司）（平台喂数抽取：脚本只输出边 JSON）。

机构域 spec 驱动；resolver 每批从 mysql ctx 构建，端点不建点。
入库/索引/消歧/游标由平台负责，逐行失败进 failures（审核重跑）。
"""

from collections.abc import Mapping
from typing import Any

from script.relation_extractors_one_relation.org_edges import (
    org_relation_sources,
    transform_org_relation,
)

RELATION_KEY = "subsidiary"

# 来源绑定元数据（script/register_platform_extraction.py 读取建 GraphSchemaSource）
SOURCES = org_relation_sources(RELATION_KEY)


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return transform_org_relation(RELATION_KEY, payload)
