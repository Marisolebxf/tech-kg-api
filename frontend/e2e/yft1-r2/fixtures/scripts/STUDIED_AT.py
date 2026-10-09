"""STUDIED_AT 关系抽取步（@step，yunfei_test 空间还原专用）。

复刻 ``script/load_scholar_relations.load_studied_at`` 的抽取逻辑：
``dwd_scholar`` 教育院校字段（education_background_institution_zh/en）按名称
精确匹配图中已存在 Organization（中→英、精确→小写，index 由图内 Organization
的 name_cn/name_en 构建），匹配不到跳过（不建桩机构），边为
``person_{scholar_id}`` -[STUDIED_AT]-> org vid，属性与老脚本一致
（confidence=0.6 占位、match_method=edu_org_name_match）。

与老脚本的差异仅在执行模型：老脚本一次性全图批量跑，本步按平台喂数管道
逐批转换（每批重建一次 org name→vid 索引，Organization 体量小，代价可忽略）；
写图/幂等由平台负责。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from kg_sdk import step

logger = logging.getLogger("studied_at")


def resolve_org_vid_by_name(
    name_zh: str | None, name_en: str | None, index: dict[str, str]
) -> str | None:
    """``scholar_org_id`` 缺失时,用机构名(中→英,精确→小写)在 index 里查 org 真实 vid。

    index 来自 :func:`build_org_name_vid_index`(图里已存在 Organization 的 name->vid)。
    找不到返回 None——调用方应跳过,不建悬挂边(替代旧的 md5 桩 vid 回退)。
    """
    for name in (name_zh, name_en):
        if not (name and name.strip()):
            continue
        key = name.strip()
        if key in index:
            return index[key]
        key_l = key.lower()
        if key_l in index:
            return index[key_l]
    return None


def build_org_name_vid_index(graph) -> dict[str, str]:
    """从图里已存在 Organization 节点建 name->vid 索引(只读)。

    匹配 ``organization_entity_etl`` 已灌的真实 vid(org_{org_id}),替代失效的 md5 桩 vid,
    避免 AFFILIATED_WITH 边指向不存在的 org。读失败/空 → 返回 {}(调用方跳过无 id 的)。
    """
    index: dict[str, str] = {}
    try:
        result = graph.execute_read(
            "MATCH (v:Organization) RETURN id(v) AS vid, "
            "v.Organization.name_cn AS name_cn, v.Organization.name_en AS name_en;"
        )
    except Exception:  # noqa: BLE001
        logger.warning("build_org_name_vid_index: 读 Organization 失败,返回空索引")
        return index
    for rec in result.records if result else []:
        vid = rec.get("vid")
        if not vid:
            continue
        for k in ("name_cn", "name_en"):
            name = rec.get(k)
            if isinstance(name, str) and name.strip():
                index[name.strip()] = str(vid)
                index[name.strip().lower()] = str(vid)
    return index


CONFIDENCE_PLACEHOLDER_ORG = 0.6


_BATCH = "yunfei_restore_studied_at"


@step("studied_at")
def emit(payload: Mapping[str, Any]) -> dict[str, Any]:
    from kg_sdk import current_context

    ctx = current_context()
    graph = ctx.graph if ctx is not None else None
    index = build_org_name_vid_index(graph) if graph is not None else {}
    failures = []
    edges = []
    for row in payload.get("rows") or []:
        sid = str(row.get("scholar_id") or "").strip()
        if not sid:
            continue
        inst_zh = str(row.get("education_background_institution_zh") or "").strip()
        inst_en = str(row.get("education_background_institution_en") or "").strip()
        if not inst_zh and not inst_en:
            continue
        dst = resolve_org_vid_by_name(inst_zh or None, inst_en or None, index)
        if not dst:
            continue
        rid = f"{sid}|studied|{dst}"
        edges.append(
            {
                "fromId": f"person_{sid}",
                "toId": dst,
                "props": {
                    "degree_zh": str(row.get("education_background_degree_zh") or ""),
                    "degree_en": str(row.get("education_background_degree_en") or ""),
                    "education_date": str(row.get("education_background_date") or ""),
                    "institution_zh": inst_zh,
                    "institution_en": inst_en,
                    "source_system": "gkx_element",
                    "source_table": "dwd_scholar",
                    "source_record_id": rid,
                    "ingest_batch": _BATCH,
                    "confidence": CONFIDENCE_PLACEHOLDER_ORG,
                    "match_method": "edu_org_name_match",
                    "match_evidence": "education_background_institution_* 按名称匹配图中 Organization",
                },
            }
        )
    return {"edges": edges, "failures": failures}
