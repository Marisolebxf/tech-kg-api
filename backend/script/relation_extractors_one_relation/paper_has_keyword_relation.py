"""One-relation transform for HAS_KEYWORD（Paper → Keyword，论文分类）（平台喂数抽取）。"""

import json
from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord
from script.relation_extractors_one_relation.resolvers import keyword_vid, paper_source_id

SOURCES = [
    {"table": "dwd_zh_paper_classification", "pk": "id", "time": "updated_time"},
    {"table": "dwd_en_paper_classification", "pk": "id", "time": "updated_time"},
]


def _parse_keywords(raw: str, lang: str) -> list[str]:
    if lang == "en":
        try:
            return [str(x).strip() for x in json.loads(raw) if x]
        except (json.JSONDecodeError, TypeError):
            return [s.strip() for s in raw.split(",") if s.strip()]
    return [s.strip() for s in raw.split(",") if s.strip()]


def paper_has_keyword(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("id"))
    raw = str(row.get("keywords") or "")
    if not pid or not raw:
        return []
    lang = "en" if table == "dwd_en_paper_classification" else "zh"
    records = []
    for kw in _parse_keywords(raw, lang):
        if not kw:
            continue
        records.append(
            EdgeRecord("HAS_KEYWORD", f"paper_{pid}", keyword_vid(kw), {"confidence": 1.0}, rank=0)
        )
    return records


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=paper_has_keyword)
