"""One-entity transform for Project（平台喂数抽取：脚本只输出实体 JSON）。

复刻旧 load_project_graph.py 口径：zh/en 两表 LEFT JOIN 产出统计字段，
置信度按核心字段完整度打分（mapper 内打分，与旧一致）。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import project_record
from script.extract_transform_common import entity_transform

QUERY_SQL_BY_TABLE = {
    "dwd_zh_project": """
        SELECT p.*, o.total_outputs, o.journal_articles_count, o.conference_papers_count,
               o.books_count, o.degree_papers_count, o.patents_count, 0 AS clinical_trials_count,
               0 AS products_count, o.awards_count, o.reports_count, o.other_outputs_count
        FROM dwd_zh_project p
        LEFT JOIN dwd_zh_project_output o ON o.id = p.id
    """,
    "dwd_en_project": """
        SELECT p.*, o.total_outputs, o.journal_articles_count, o.conference_papers_count,
               o.books_count, o.degree_papers_count, o.patents_count, o.clinical_trials_count,
               0 AS products_count, o.awards_count, o.reports_count, o.other_outputs_count
        FROM dwd_en_project p
        LEFT JOIN dwd_en_project_output o ON o.id = p.id
    """,
}

SOURCES = [
    {"table": t, "pk": "id", "time": "update_time", "query_sql": sql}
    for t, sql in QUERY_SQL_BY_TABLE.items()
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=project_record)
