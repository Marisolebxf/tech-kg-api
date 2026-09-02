"""One-relation transform for PUBLISHED_IN（Paper → Journal）（平台喂数抽取）。"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord
from script.relation_extractors_one_relation.resolvers import paper_source_id

SOURCES = [
    {"table": "dwd_zh_paper", "pk": "id", "time": "updated_time"},
    {"table": "dwd_en_paper", "pk": "id", "time": "updated_time"},
]


def published_in(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("id"))
    jid = str(row.get("publication_id")) if row.get("publication_id") else ""
    if not pid or not jid:
        return []
    return [
        EdgeRecord("PUBLISHED_IN", f"paper_{pid}", f"journal_{jid}", {"confidence": 1.0}, rank=0)
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=published_in)
