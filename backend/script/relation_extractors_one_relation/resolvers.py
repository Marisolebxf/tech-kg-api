"""端点解析与共享匹配原语。

VID 公式一律复用 ``entity_extractors_one_entity.common``，保证边端点与实体点
同源。两处有意修复的旧分叉（拆分设计文档中声明的统一决策）：

- ``person_vid_for_row`` 采用实体侧公式：身份值用 ``first_value(org_id, external_id)``
  且 birth/country 恒参与哈希（旧关系侧 shareholder 分支不带 birth/country、
  只用 org_id，会导致边起点对不上实体点）。
- ``keyword_vid`` 三域统一为 NFKC+空白折叠+casefold 后的完整 md5（旧口径中
  论文=md5(原文)、项目=md5(lower)、专利=md5(casefold) 三处不一致）。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from script.entity_extractors_one_entity.common import (
    first_value,
    organization_vid,
    person_vid,
    text_or_none,
)

_PAPER_SUFFIX_RE = re.compile(r"__\d+$")


# ---------------------------------------------------------------------------
# Keyword / Paper 端点
# ---------------------------------------------------------------------------


def keyword_vid(keyword: str) -> str:
    """三域统一：NFKC + 空白折叠 + casefold 后的完整 md5（专利域旧公式）。"""
    normalized = " ".join(unicodedata.normalize("NFKC", str(keyword)).strip().split())
    return f"keyword_{hashlib.md5(normalized.casefold().encode('utf-8')).hexdigest()}"


def paper_source_id(raw_id: Any) -> str:
    """论文端点旧口径：去掉 ``__数字`` 后缀（仅用于关系端点）。"""
    raw = str(raw_id or "")
    return _PAPER_SUFFIX_RE.sub("", raw) if raw else ""


def paper_stub_vid(prefix: str, key: str) -> str:
    """论文工作流旧口径的 md5 桩：``{prefix}_{md5(key)[:16]}``（key 不做归一）。"""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


# ---------------------------------------------------------------------------
# 机构端点解析（机构域旧 ExactOrganizationResolver）
# ---------------------------------------------------------------------------


class ExactOrganizationResolver:
    """名称仅在精确匹配且唯一时解析为机构 ID（旧口径）。"""

    _SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("dwd_org_base_info", "org_id", ("name_cn",)),
        ("dwd_org_heis_info", "org_id", ("name_cn", "name_en")),
        ("dwd_research_institute_base_info", "org_id", ("name_cn", "name_en")),
        (
            "dwd_special_hongkong_company",
            "org_id",
            ("name_cn", "name_en", "traditional_name"),
        ),
        (
            "dwd_special_taiwan_company",
            "org_id",
            ("company_name", "n_company_name", "name_en"),
        ),
        ("dwd_special_aomen_company", "org_id", ("org_loc_name", "en_name")),
        ("dwd_forg_base_info", "org_id", ("name_en", "name_alias")),
    )

    def __init__(self, by_name: Mapping[str, set[str]]) -> None:
        self._by_name = {name: set(ids) for name, ids in by_name.items()}

    @classmethod
    def load(cls, engine: Engine, database: str = "gkx_element") -> ExactOrganizationResolver:
        by_name: dict[str, set[str]] = defaultdict(set)
        with engine.connect() as conn:
            for table, id_column, name_columns in cls._SOURCES:
                columns = (id_column, *name_columns)
                select = ",".join(f"`{name}`" for name in columns)
                rows = conn.execute(text(f"SELECT {select} FROM `{table}`")).mappings()
                for row in rows:
                    org_id = text_or_none(row.get(id_column))
                    if org_id is None:
                        continue
                    for name_column in name_columns:
                        name = text_or_none(row.get(name_column))
                        if name is not None:
                            by_name[name].add(org_id)
        return cls(by_name)

    def resolve_exact(self, name: Any) -> str | None:
        key = text_or_none(name)
        if key is None:
            return None
        candidates = self._by_name.get(key, set())
        if len(candidates) != 1:
            return None
        return next(iter(candidates))

    resolve = resolve_exact


def resolved_organization_vid(
    raw_id_or_name: Any,
    resolver: ExactOrganizationResolver,
    *,
    fallback_name: Any = None,
) -> str:
    """优先精确唯一名解析，否则视值为机构 ID（旧 resolved_organization_vid）。"""
    raw = text_or_none(raw_id_or_name)
    exact_id = resolver.resolve_exact(raw) if raw is not None else None
    exact_id = exact_id or resolver.resolve_exact(fallback_name)
    if exact_id is not None:
        return organization_vid(exact_id)
    if raw is None:
        raise ValueError("organization has no stable or exact unique identifier")
    return organization_vid(raw)


def organization_vid_from_row(
    row: Mapping[str, Any],
    resolver: ExactOrganizationResolver,
    *,
    id_fields: Sequence[str],
    name_fields: Sequence[str],
) -> str:
    """旧 _organization_vid_from_row 的 exact 模式：ID 优先，缺 ID 走精确名解析。"""
    raw_id = first_value(row, *id_fields)
    if text_or_none(raw_id) is not None:
        exact_id = resolver.resolve_exact(raw_id)
        return organization_vid(exact_id if exact_id is not None else raw_id)
    name = first_value(row, *name_fields)
    return resolved_organization_vid(name, resolver)


# ---------------------------------------------------------------------------
# Person 端点（实体侧统一公式）
# ---------------------------------------------------------------------------


def person_vid_for_row(
    row: Mapping[str, Any],
    person_kind: str,
    name_field: str,
) -> str:
    """实体侧统一公式：kind|first(org_id, external_id)|name|birth_date|country。"""
    name = text_or_none(row.get(name_field))
    if name is None:
        raise ValueError("missing person name")
    target_identity = first_value(row, "org_id", "external_id")
    birth_date = first_value(row, "dm_birthdate", "bo_birthdate", "birth_date")
    country = first_value(row, "dm_nationalities", "bo_country_code", "country_code")
    return person_vid(person_kind, target_identity, name, birth_date, country)


# ---------------------------------------------------------------------------
# 实体列表解析（旧 parse_entity_list）
# ---------------------------------------------------------------------------


def parse_entity_list(value: Any) -> list[Any]:
    """接受 JSON 数组/对象或一个精确纯文本机构名。"""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    raw = text_or_none(value)
    if raw is None:
        return []
    if raw.startswith(("[", "{")):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return [parsed]
    return [raw]
