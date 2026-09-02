"""One-relation transform for COVERS_CHAIN（News → IndustryChain）（平台喂数抽取）。"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord, now_utc

SOURCES = [
    {"table": "dwd_industry_chain_news_info", "pk": "news_id", "time": "update_time"},
]


def covers_chain(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    news_id = str(row.get("news_id") or "").strip()
    chain_code = str(row.get("chain_code") or "").strip()
    if not news_id or not chain_code:
        return []
    return [
        EdgeRecord(
            "COVERS_CHAIN",
            f"news_{news_id}",
            f"chain_{chain_code}",
            {"source_table": table, "ingest_batch": batch, "ingest_time": now_utc()},
            rank=0,
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=covers_chain)
