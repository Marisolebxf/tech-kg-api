"""实体置信度：图上已有值优先，否则按证据规则计算，最后兜底默认值，并尽力写回图。

规则与 ``script.organization_etl_common.entity_confidence`` 同口径（DWD 来源 / 稳定 ID /
展示名 / 辅助属性），供重点科技企业关系、产业链点 TOP-N 实体 tab 使用，避免展示「暂无」。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ENTITY_CONFIDENCE = 0.80

_PREFERRED_TAGS = (
    "Person",
    "Organization",
    "Event",
    "News",
    "IndustryNode",
    "IndustryChain",
    "Project",
    "Product",
)

_ID_FIELDS = (
    "organization_id",
    "org_id",
    "company_id",
    "entity_eid",
    "source_record_id",
    "node_id",
    "chain_code",
    "scholar_id",
)

_NAME_FIELDS = (
    "name_cn",
    "name_zh",
    "name_en",
    "company_name",
    "org_loc_name",
    "executives_name",
    "bo_name",
    "entity_name",
    "news_title",
    "title",
    "job_title",
    "target_item_name",
    "main_prod",
    "main_products",
    "node_name",
    "chain_name",
)

_SUPPORT_FIELDS = (
    "country_code",
    "country",
    "province",
    "city",
    "address",
    "updated_time",
    "ingest_time",
    "node_imp_level",
    "external_id",
    "credit_no",
)

_altered_tags: set[str] = set()


def reset_persist_state() -> None:
    """测试隔离：清空已尝试 ALTER 的 tag 记录。"""
    _altered_tags.clear()


def _text(value: object) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def parse_confidence(value: object) -> float | None:
    """读取已有置信度；缺失或非法则视为无。"""
    if value in (None, ""):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return round(min(max(number, 0.0), 1.0), 4)


def compute_entity_confidence(
    properties: Mapping[str, Any] | None,
    labels: Sequence[str] | set[str] | None = None,
) -> float | None:
    """按入图证据打分；没有任何可用字段时返回 None，由调用方兜底。"""
    del labels  # 预留按 tag 微调；当前与 ETL 一样只看属性
    props = properties or {}
    source_table = _text(props.get("organization_base")) or _text(props.get("source_table")) or ""
    has_id = any(_text(props.get(name)) is not None for name in _ID_FIELDS)
    has_name = any(_text(props.get(name)) is not None for name in _NAME_FIELDS)
    has_support = any(_text(props.get(name)) is not None for name in _SUPPORT_FIELDS)
    if not (source_table or has_id or has_name or has_support):
        return None

    score = 0.40 if source_table.startswith("dwd_") else 0.30
    if has_id:
        score += 0.20
    if any(_text(props.get(name)) is not None for name in ("external_id", "credit_no")):
        score += 0.10
    if has_name:
        score += 0.20
    if any(
        _text(props.get(name)) is not None
        for name in (
            "country_code",
            "country",
            "province",
            "city",
            "address",
            "updated_time",
            "ingest_time",
            "node_imp_level",
        )
    ):
        score += 0.10
    return round(min(max(score, 0.0), 1.0), 4)


def resolve_entity_confidence(
    properties: Mapping[str, Any] | None,
    labels: Sequence[str] | set[str] | None = None,
) -> float:
    """已有值 → 规则计算 → 默认 0.80。"""
    existing = parse_confidence((properties or {}).get("confidence"))
    if existing is not None:
        return existing
    computed = compute_entity_confidence(properties, labels)
    if computed is not None:
        return computed
    return DEFAULT_ENTITY_CONFIDENCE


def primary_tag(labels: Sequence[str] | set[str] | None) -> str | None:
    if not labels:
        return None
    label_set = set(labels)
    for tag in _PREFERRED_TAGS:
        if tag in label_set:
            return tag
    return next(iter(labels), None)


def _ngql_vid(vid: str) -> str:
    return json.dumps(str(vid), ensure_ascii=False)


def persist_entity_confidence(client: Any, vid: str, tag: str, value: float) -> bool:
    """把计算出的置信度写回顶点。列不存在时 ALTER 一次再重试；失败不影响查询。"""
    if client is None or not vid or not tag:
        return False
    query = f"UPDATE VERTEX ON `{tag}` {_ngql_vid(vid)} SET `{tag}`.`confidence` = {value:.4f};"
    try:
        client.execute_write(query)
        return True
    except Exception as exc:
        if tag in _altered_tags:
            logger.warning("写回实体置信度失败 vid=%s tag=%s: %s", vid, tag, exc)
            return False
        try:
            client.execute_write(f"ALTER TAG `{tag}` ADD (`confidence` double NULL);")
            _altered_tags.add(tag)
            client.execute_write(query)
            return True
        except Exception as alter_exc:
            _altered_tags.add(tag)
            logger.warning(
                "补 confidence 列或写回失败 vid=%s tag=%s: %s",
                vid,
                tag,
                alter_exc,
            )
            return False


def fill_entity_confidence(
    properties: dict[str, Any] | None,
    labels: Sequence[str] | set[str] | None = None,
    *,
    vid: str | None = None,
    client: Any = None,
) -> float:
    """解析或计算置信度；缺图上的值时写回（best-effort），并填进 properties。"""
    props = properties if properties is not None else {}
    existing = parse_confidence(props.get("confidence"))
    value = resolve_entity_confidence(props, labels)
    props["confidence"] = value
    if existing is None and client is not None and vid:
        tag = primary_tag(labels)
        if tag:
            persist_entity_confidence(client, vid, tag, value)
    return value
