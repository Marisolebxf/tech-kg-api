"""One-relation transform for REFERENCED_BY（Paper ← Report）（平台喂数抽取）。

dwd_zh_report_paper 无独立主键/时间列，row_id 合成 + keyset 增量（time 留空）。
"""

import json
from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord

SOURCES = [
    {
        "table": "dwd_zh_report_paper",
        "pk": "row_id",
        "time": "",
        "query_sql": (
            "SELECT *, CONCAT(paper_id, '__', report_id) AS row_id FROM dwd_zh_report_paper"
        ),
    },
]


def _report_ids(raw: str) -> list[str]:
    raw = str(raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            return [str(item) for item in parsed if item]
        except json.JSONDecodeError:
            return [raw]
    return [raw]


def referenced_by(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    paper_id = str(row.get("paper_id") or "").strip()
    if not paper_id:
        return []
    records = []
    for rid in _report_ids(row.get("report_id")):
        records.append(
            EdgeRecord(
                "REFERENCED_BY",
                f"paper_rp_{paper_id}",
                f"report_{rid}",
                {"confidence": 0.8},
                rank=0,
                validate_endpoints=False,
            )
        )
    return records


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=referenced_by)
