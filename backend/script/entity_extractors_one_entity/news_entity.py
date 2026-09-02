"""One-entity transform for News（平台喂数抽取：脚本只输出实体 JSON）。

两个来源的 mapper 不同（机构要闻 / 产业链新闻），按来源表名分发。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import news_chain_record, news_org_record
from script.extract_transform_common import entity_transform

SOURCES = [
    {"table": "dwd_org_important_news_info", "pk": "id", "time": "update_time"},
    {"table": "dwd_industry_chain_news_info", "pk": "news_id", "time": "update_time"},
]

MAPPER_BY_TABLE = {
    "dwd_org_important_news_info": news_org_record,
    "dwd_industry_chain_news_info": news_chain_record,
}


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, mapper_by_table=MAPPER_BY_TABLE)
