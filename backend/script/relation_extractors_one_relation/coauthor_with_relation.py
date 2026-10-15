"""One-relation transform for COAUTHOR_WITH（Person ↔ Person）（平台喂数抽取）。

dwd_scholar_coauthor（status=1），主键直接抽取未经推断（confidence=1.0）。
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord, edge_provenance

SOURCES = [
    {
        "table": "dwd_scholar_coauthor",
        "pk": "row_id",
        "time": "update_time",
        "query_sql": (
            "SELECT *, CONCAT(scholar_id, '__', co_scholar_id) AS row_id "
            "FROM dwd_scholar_coauthor WHERE status = 1"
        ),
    },
]


def coauthor_with(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    sid = str(row.get("scholar_id") or "").strip()
    co_sid = str(row.get("co_scholar_id") or "").strip()
    if not sid or not co_sid:
        return []
    record_id = f"{sid}_{co_sid}"
    # 无真实合作时间字段：与旧 load_scholar_relations / dao 直查口径一致，用行更新
    # 时间代理（直接关系模块的时间过滤依赖 relation_time，缺字段则限时查询全空）。
    rel_time = row.get("update_time") or row.get("create_time")
    if isinstance(rel_time, datetime):
        rel_time_text = rel_time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        rel_time_text = str(rel_time or "")
    props = {
        "co_paper_count": int(row.get("co_paper_count") or 0),
        "relation_time": rel_time_text,
        "confidence": 1.0,
        "match_method": "source_primary_key",
        "match_evidence": "dwd_scholar_coauthor.scholar_id 主键直接抽取，未经推断",
        **edge_provenance(source_table=table, source_record_id=record_id, ingest_batch=batch),
    }
    return [
        EdgeRecord(
            "COAUTHOR_WITH",
            f"person_{sid}",
            f"person_{co_sid}",
            props,
            identity={"source_record_id": record_id},
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=coauthor_with)
