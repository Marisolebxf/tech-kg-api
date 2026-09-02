"""One-relation transform for HAS_NODE（IndustryChain → IndustryNode）（平台喂数抽取）。"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord

_ROW_ID_SQL = "SELECT *, CONCAT(chain_code, '__', node_id) AS row_id FROM dwd_industry_chain_info"

SOURCES = [
    {"table": "dwd_industry_chain_info", "pk": "row_id", "time": "", "query_sql": _ROW_ID_SQL}
]


def has_node(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    chain_code = str(row.get("chain_code") or "").strip()
    node_id = str(row.get("node_id") or "").strip()
    if not chain_code or not node_id:
        return []
    return [EdgeRecord("HAS_NODE", f"chain_{chain_code}", f"node_{node_id}", {}, rank=0)]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=has_node)
