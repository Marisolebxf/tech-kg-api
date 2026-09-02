"""One-relation transform for HAS_KEYWORD（Patent → Keyword，专利域）（平台喂数抽取）。

解析 dwd_patent.keywords（NFKC 归一 + 去重），Keyword 顶点由 keyword 抽取先行写入。
来源复用专利聚合 SQL（平台包水位条件）。
"""

from collections.abc import Mapping
from typing import Any

from script.entity_extractors_one_entity.mappers import _keyword_values
from script.entity_extractors_one_entity.patent_entity import PATENT_QUERY_SQL
from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord
from script.relation_extractors_one_relation.resolvers import keyword_vid

SOURCES = [
    {
        "table": "dwd_patent",
        "pk": "source_row_id",
        "time": "update_time",
        "query_sql": PATENT_QUERY_SQL,
    },
]


def patent_has_keyword(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    patent_id = str(row.get("patent_id") or "").strip()
    if not patent_id:
        return []
    records: list[EdgeRecord] = []
    for keyword in _keyword_values(row.get("keywords")):
        records.append(
            EdgeRecord(
                "HAS_KEYWORD",
                f"patent_{patent_id}",
                keyword_vid(keyword),
                {
                    "confidence": 1.0,
                    "source_table": "dwd_patent",
                    "source_record_id": patent_id,
                },
                rank=0,
            )
        )
    return records


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=patent_has_keyword)
