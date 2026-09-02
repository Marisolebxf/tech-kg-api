"""One-relation transform for CITES/CITED_BY/RELATED_TO（Paper 引文域）（平台喂数抽取）。

六张引文表按表名分发（CONFIG_BY_TABLE），DOI 桩端点不验存（旧口径）。
"""

from collections.abc import Mapping
from typing import Any

from script.extract_transform_common import edge_transform
from script.relation_extractors_one_relation.common import EdgeRecord
from script.relation_extractors_one_relation.resolvers import paper_source_id, paper_stub_vid

# (表, 边类型, 桩前缀, 标识字段, confidence)
CONFIGS = (
    ("dwd_zh_paper_reference", "CITES", "paper_ref", "reference_identifier", 0.5),
    ("dwd_en_paper_reference", "CITES", "paper_ref", "reference_identifier", 0.5),
    ("dwd_zh_paper_citation", "CITED_BY", "paper_cit", "citation_identifier", 0.5),
    ("dwd_en_paper_citation", "CITED_BY", "paper_cit", "citation_identifier", 0.5),
    ("dwd_zh_paper_related", "RELATED_TO", "paper_rel", None, 0.7),
    ("dwd_en_paper_related", "RELATED_TO", "paper_rel", None, 0.7),
)

CONFIG_BY_TABLE = {config[0]: config for config in CONFIGS}

SOURCES = [{"table": table, "pk": "id", "time": "updated_time"} for table in CONFIG_BY_TABLE]


def paper_cites(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    _, edge_type, stub_prefix, id_field, confidence = CONFIG_BY_TABLE[table]
    pid = paper_source_id(row.get("id"))
    doi = str(row.get("doi") or "").strip()
    if not pid or not doi:
        return []
    props: dict[str, Any] = {"confidence": confidence}
    if id_field:
        props[id_field] = doi
    return [
        EdgeRecord(
            edge_type,
            f"paper_{pid}",
            paper_stub_vid(stub_prefix, doi),
            props,
            rank=0,
            validate_endpoints=False,
        )
    ]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=paper_cites)
