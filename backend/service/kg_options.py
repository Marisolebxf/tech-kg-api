"""测试参数下拉选项聚合：图库(学者/关系边) + MySQL(企业) + 目录(关系类型/角色/维度/领域/CPC)。"""

from __future__ import annotations

import logging
from typing import Any

from db_model.domestic_organization import DwdOrgRegInfo
from sqlalchemy import select

from db_model.scholar import Scholar
from infra.graph_db import get_techkg_client
from infra.mysql import get_mysql_client
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


def _scholars() -> list[dict[str, str]]:
    """从 techkg `scholar` 表读真实学者（如 COOP-SCH001 陈建国）。"""
    out: list[dict[str, str]] = []
    try:
        session = get_mysql_client().session()
        try:
            for r in session.execute(select(Scholar).limit(500)).scalars():
                out.append({"scholarId": r.scholar_id, "name": r.name_zh or r.scholar_id})
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("load scholars failed: %s", exc)
    return out


def _enterprises() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        session = get_mysql_client().session()
        try:
            for r in session.execute(select(DwdOrgRegInfo).limit(200)).scalars():
                out.append({"enterpriseId": r.org_id, "name": r.name_cn})
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("load enterprises failed: %s", exc)
    return out


def _edges() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        res = get_techkg_client().get_edges_by_type("EMPLOYED_BY", limit=100)
        for e in res.items[:50]:
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
