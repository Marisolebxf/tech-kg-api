"""参数下拉选项：当前图空间的学者、企业、关系，以及固定分类目录。"""

from __future__ import annotations

import logging
from typing import Any

from infra.graph_db import get_trs_graph_client
from service.enterprise_relation_catalog import RELATION_TYPES, ROLE_CATALOG

logger = logging.getLogger(__name__)

DIMENSIONS: list[tuple[str, str]] = [
    ("industry_status", "行业地位"),
    ("core_tech", "核心技术"),
    ("financial", "经营财务"),
]
TECH_FIELDS: list[str] = ["人工智能", "集成电路", "新能源", "生物医药", "高端装备", "新材料"]
CPC_CODES: list[str] = [
    "G06N",
    "G06F",
    "G06N3/04",
    "H04L9/00",
    "H01M10/0525",
    "A61B5/00",
    "G16H50/20",
]


def _graph_options(labels: list[str], id_key: str) -> list[dict[str, str]]:
    out = []
    seen = set()
    for label in labels:
        try:
            graph = get_trs_graph_client()
            nodes = graph.find_nodes([label], {}, limit=200).items
            for node in nodes:
                if node.properties.get("manual_disabled") is True or str(node.id) in seen:
                    continue
                seen.add(str(node.id))
                props = node.properties
                name = next((str(props[k]) for k in ("name_zh", "name_cn", "name", "name_en") if props.get(k)), str(node.id))
                source_id = props.get("scholar_id" if id_key == "scholarId" else "org_id") or node.id
                out.append({id_key: str(source_id), "name": name})
        except Exception as exc:
            logger.warning("load graph options %s failed: %s", label, exc)
    return out


def _scholars() -> list[dict[str, str]]:
    return _graph_options(["Person", "Scholar"], "scholarId")


def _enterprises() -> list[dict[str, str]]:
    return _graph_options(["Organization"], "enterpriseId")


def _edges() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        res = get_trs_graph_client().get_edges_by_type("EMPLOYED_BY", limit=100)
        for e in res.items[:50]:
            if e.properties.get("manual_disabled") is True:
                continue
            out.append(
                {
                    "relationId": str(e.id),
                    "scholarId": str(e.source_id),
                    "enterpriseId": str(e.target_id),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("load edges failed: %s", exc)
    return out


def get_options() -> dict[str, Any]:
    """聚合测试参数下拉选项。任一数据源异常时返回空列表，不阻塞整体。"""
    return {
        "scholars": _scholars(),
        "enterprises": _enterprises(),
        "edges": _edges(),
        "relationTypes": [{"value": k, "label": v} for k, v in RELATION_TYPES.items()],
        "roles": [{"value": k, "label": v[0]} for k, v in ROLE_CATALOG.items()],
        "dimensions": [{"value": val, "label": label} for val, label in DIMENSIONS],
        "techFields": TECH_FIELDS,
        "cpcCodes": CPC_CODES,
    }
