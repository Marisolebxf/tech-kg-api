"""One-entity transform for Paper（平台喂数抽取：脚本只输出实体 JSON）。

入库/索引/消歧/游标推进全部由平台完成；本脚本只做 行 → 实体 转换，
逐行解析失败进 ``failures``（平台落 T_EXTRACT_FAIL 审核 case 供重跑）。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import paper_record
from script.extract_transform_common import entity_transform

# 来源绑定元数据（script/register_platform_extraction.py 读取建 GraphSchemaSource）
SOURCES = [
    {"table": "dwd_zh_paper", "pk": "id", "time": "update_time"},
    {"table": "dwd_en_paper", "pk": "id", "time": "update_time"},
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=paper_record)
