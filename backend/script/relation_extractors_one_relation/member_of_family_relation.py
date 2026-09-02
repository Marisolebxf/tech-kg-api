"""One-relation transform for MEMBER_OF_FAMILY（Patent → PatentFamily）（平台喂数抽取）。

族号缺失不建边；来源复用专利聚合 SQL（平台包水位条件）。
"""

from collections.abc import Mapping
from typing import Any

from script.entity_extractors_one_entity.patent_entity import PATENT_QUERY_SQL
from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord

SOURCES = [
    {
        "table": "dwd_patent",
        "pk": "source_row_id",
        "time": "update_time",
        "query_sql": PATENT_QUERY_SQL,
    },
]


def member_of_family(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    number = str(row.get("simple_family_number") or "").strip()
    patent_id = str(row.get("patent_id") or "").strip()
    if not number or not patent_id:
        return []
    return [
        EdgeRecord(
            "MEMBER_OF_FAMILY",
            f"patent_{patent_id}",
            f"patent_family_{number}",
            {
                "confidence": 1.0,
                "match_method": "source_family_number",
                "match_evidence": "simple_family_number由源表直接给出",
                "source_table": "dwd_patent_family",
                "source_record_id": patent_id,
            },
            rank=0,
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=member_of_family)
