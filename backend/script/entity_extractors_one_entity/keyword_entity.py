"""One-entity transform for Keyword（平台喂数抽取：脚本只输出实体 JSON）。

关键词来源：学者研究方向、论文分类、项目表、专利关键词（复用专利聚合 SQL）。
VID 为 keyword_{md5(lower(keyword))} 完整 32 位。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import keyword_records
from script.entity_extractors_one_entity.patent_entity import PATENT_QUERY_SQL
from script.extract_transform_common import entity_transform

TABLES = (
    "dwd_scholar_research_direction",
    "dwd_zh_paper_classification",
    "dwd_en_paper_classification",
    "dwd_zh_project",
    "dwd_en_project",
)

SOURCES = [
    *[{"table": t, "pk": "id", "time": "update_time"} for t in TABLES],
    {
        "table": "dwd_patent",
        "pk": "source_row_id",
        "time": "update_time",
        "query_sql": PATENT_QUERY_SQL,
    },
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=keyword_records)
