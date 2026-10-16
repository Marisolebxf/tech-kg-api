"""One-relation transform for AUTHORED_BY（Paper → Person）（平台喂数抽取：只输出边 JSON）。

四源：dwd_zh/en_author（旧口径）+ dwd_scholar_paper_relation（厂商全量）
+ dwd_scholar_paper_relation_element（element 旧 relation，paper_id 为厂商 id 空间）。
paper 端去 ``__数字`` 后缀，author_id 非空；边属性
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
    # 厂商全量 relation（dwd_scholar_paper_relation，真主键 dwd_id 走 keyset）：
    # paper 端 join papers 保证落图的 paper_id 全部有 Paper 点、scholar 端 join
    # dwd_scholar（本地 = element 2,175 ∪ 追加的厂商学者）保证作者全有 Person 点。
    {
        "table": "dwd_scholar_paper_relation",
        "pk": "dwd_id",
        "time": "",
        "query_sql": (
            "SELECT r.dwd_id, r.paper_id, r.scholar_id AS author_id, r.updated_time "
            "FROM dwd_scholar_paper_relation r "
            "JOIN dwd_scholar_papers p ON r.paper_id = p.id AND p.is_deleted = 0 "
            "JOIN dwd_scholar s ON r.scholar_id = s.scholar_id AND s.status = 1 "
            "WHERE r.is_deleted = 0"
        ),
    },
    # element 旧 relation（无主键表，(paper_id, scholar_id) 已验唯一，CONCAT 合成游标）：
    # paper_id 是厂商 id 空间，join 迁入的厂商 papers 表落锚点。
    {
        "table": "dwd_scholar_paper_relation_element",
        "pk": "row_id",
        "time": "",
        "query_sql": (
            "SELECT CONCAT(r.paper_id, '__', r.scholar_id) AS row_id, r.paper_id, "
            "r.scholar_id AS author_id, r.update_time "
            "FROM dwd_scholar_paper_relation_element r "
            "JOIN dwd_scholar_papers p ON r.paper_id = p.id AND p.is_deleted = 0 "
            "WHERE r.status = 1"
        ),
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
