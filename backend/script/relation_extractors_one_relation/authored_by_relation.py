"""One-relation transform for AUTHORED_BY（Paper → Person）（平台喂数抽取：只输出边 JSON）。

dwd_zh/en_author，paper 端去 ``__数字`` 后缀，author_id 非空；边属性
(author_order, is_corresponding, confidence=1.0)。Person 顶点由 person 抽取先行写入。
"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord
from script.relation_extractors_one_relation.resolvers import paper_source_id

SOURCES = [
    {
        "table": "dwd_zh_author",
        "pk": "row_id",
        "time": "update_time",
        "query_sql": "SELECT *, CONCAT(paper_id, '__', author_id) AS row_id FROM dwd_zh_author",
    },
    {
        "table": "dwd_en_author",
        "pk": "row_id",
        "time": "update_time",
        "query_sql": "SELECT *, CONCAT(paper_id, '__', author_id) AS row_id FROM dwd_en_author",
    },
]


def authored_by(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("paper_id"))
    aid = str(row.get("author_id")) if row.get("author_id") else ""
    if not pid or not aid:
        return []
    return [
        EdgeRecord(
            "AUTHORED_BY",
            f"paper_{pid}",
            f"person_{aid}",
            {
                "author_order": str(row.get("author_sequence"))
                if row.get("author_sequence") is not None
                else "",
                "is_corresponding": str(row.get("correspond"))
                if row.get("correspond") is not None
                else "",
                "confidence": 1.0,
            },
            rank=0,
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=authored_by)
