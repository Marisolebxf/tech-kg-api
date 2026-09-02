"""One-relation transform for BELONGS_TO_NODE（Organization → IndustryNode）（平台喂数抽取）。"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord, now_utc

SOURCES = [
    {
        "table": "dwd_org_industry_chain_dtl",
        "pk": "row_id",
        "time": "update_time",
        "query_sql": (
            "SELECT *, CONCAT(antitypic, '__', node_id) AS row_id FROM dwd_org_industry_chain_dtl"
        ),
    },
]


def belongs_to_node(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    antitypic = str(row.get("antitypic") or "").strip()
    node_id = str(row.get("node_id") or "").strip()
    if not antitypic or not node_id:
        return []
    try:
        chain_score = float(row.get("chain_score") or 0)
    except (TypeError, ValueError):
        chain_score = 0.0
    return [
        EdgeRecord(
            "BELONGS_TO_NODE",
            f"org_{antitypic}",
            f"node_{node_id}",
            {
                "chain_score": chain_score,
                "source_table": table,
                "source_record_id": antitypic,
                "ingest_batch": batch,
                "ingest_time": now_utc(),
            },
            rank=0,
            source_tag="Organization",
            target_tag="IndustryNode",
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=belongs_to_node)
