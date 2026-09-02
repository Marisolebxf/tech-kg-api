"""One-relation transform for DOWNSTREAM_OF（IndustryNode 下游链）（平台喂数抽取）。"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord

_ROW_ID_SQL = "SELECT *, CONCAT(chain_code, '__', node_id) AS row_id FROM dwd_industry_chain_info"

SOURCES = [
    {"table": "dwd_industry_chain_info", "pk": "row_id", "time": "", "query_sql": _ROW_ID_SQL}
]


def downstream_of(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    node_id = str(row.get("node_id") or "").strip()
    downstream = str(row.get("downstream_link_code") or "").strip()
    if not node_id or not downstream:
        return []
    return [EdgeRecord("DOWNSTREAM_OF", f"node_{node_id}", f"node_{downstream}", {}, rank=0)]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=downstream_of)
