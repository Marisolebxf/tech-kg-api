"""One-relation transform for CHILD_OF（IndustryNode 父子）（平台喂数抽取）。

dwd_industry_chain_info 上游表无 update_time，走 pk keyset 增量（time 留空）；
row_id 为合成唯一主键（chain_code__node_id）。
"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord

_ROW_ID_SQL = "SELECT *, CONCAT(chain_code, '__', node_id) AS row_id FROM dwd_industry_chain_info"

SOURCES = [
    {"table": "dwd_industry_chain_info", "pk": "row_id", "time": "", "query_sql": _ROW_ID_SQL}
]


def child_of(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    node_id = str(row.get("node_id") or "").strip()
    parent_id = str(row.get("parent_id") or "").strip()
    if not node_id or not parent_id:
        return []
    return [EdgeRecord("CHILD_OF", f"node_{node_id}", f"node_{parent_id}", {}, rank=0)]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=child_of)
