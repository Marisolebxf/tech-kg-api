"""One-relation transform for AUTHORED_BY 兜底（Paper → Person，学者域跨域）（平台喂数抽取）。

dwd_scholar_paper_relation（status=1），两端顶点在图中均已存在才写边（写层
端点验存），confidence=0.9（cross_domain_id_match）。paper 端 VID 用原始 paper_id。
"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord, now_utc

SOURCES = [
    {
        "table": "dwd_scholar_paper_relation",
        "pk": "row_id",
        "time": "update_time",
        "query_sql": (
            "SELECT *, CONCAT(paper_id, '__', scholar_id) AS row_id "
            "FROM dwd_scholar_paper_relation WHERE status = 1"
        ),
    },
]


def authored_by_fallback(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    paper_id = str(row.get("paper_id") or "").strip()
    scholar_id = str(row.get("scholar_id") or "").strip()
    if not paper_id or not scholar_id:
        return []
    record_id = f"{paper_id}_{scholar_id}"
    props = {
        "citations": int(row.get("citations") or 0),
        "source_table": table,
        "source_record_id": record_id,
        "ingest_batch": batch,
        "ingest_time": now_utc(),
        "confidence": 0.9,
        "match_method": "cross_domain_id_match",
        "match_evidence": "paper_id 与 scholar_id 分别命中已存在的 Paper、Person 顶点",
    }
    return [
        EdgeRecord(
            "AUTHORED_BY",
            f"paper_{paper_id}",
            f"person_{scholar_id}",
            props,
            identity={"source_record_id": record_id},
            source_tag="Paper",
            target_tag="Person",
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=authored_by_fallback)
