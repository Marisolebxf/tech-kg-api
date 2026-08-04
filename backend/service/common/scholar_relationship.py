from __future__ import annotations

import re
from typing import Any

from dao.scholar import ScholarDAO
from db_model.scholar import DwdScholar

_ZH_INSTITUTION = re.compile(r"[^，。；;\n]{2,48}?(?:大学|学院|研究院|研究所|实验室|中心)")
_EN_INSTITUTION = re.compile(
    r"(?:[A-Z][A-Za-z&.-]*\s+){0,8}(?:University|College|Institute|Laboratory|Center)"
)


def resolve_scholar(dao: ScholarDAO, identifier: str) -> DwdScholar:
    identifier = identifier.strip()
    scholar = dao.get_by_scholar_id(identifier)
    if scholar is not None:
        return scholar
    matches = dao.search_by_name(identifier, limit=20)
    exact = [
        item
        for item in matches
        if identifier.casefold() in {item.name_zh.casefold(), item.name_en.casefold()}
    ]
    if len(exact) == 1:
        return exact[0]
    if not exact:
        raise KeyError(f"学者不存在: {identifier}")
    raise ValueError(f"学者标识不唯一，请使用 scholar_id: {identifier}")


def scholar_data(scholar: DwdScholar) -> dict[str, Any]:
    return {
        "id": scholar.scholar_id,
        "name": scholar.name_zh or scholar.name_en or scholar.scholar_id,
        "nameEn": scholar.name_en,
        "organization": scholar.scholar_org_name_zh or scholar.scholar_org_name_en,
        "organizationId": scholar.scholar_org_id,
        "paperCount": scholar.paper_nums,
        "citationCount": scholar.citation_nums,
        "hIndex": scholar.h_index,
    }


def institution_evidence(*values: str | None) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for value in values:
        if not value:
            continue
        for match in [*_ZH_INSTITUTION.findall(value), *_EN_INSTITUTION.findall(value)]:
            display = " ".join(match.strip(" ,，。；;|").split())
            normalized = re.sub(r"\W+", "", display).casefold()
            if normalized:
                evidence.setdefault(normalized, display)
        display = " ".join(value.strip().split())
        if len(display) <= 128:
            normalized = re.sub(r"\W+", "", display).casefold()
            if normalized:
                evidence.setdefault(normalized, display)
    return evidence


def shared_institutions(left: dict[str, str], right: dict[str, str]) -> list[str]:
    return [left[key] for key in left.keys() & right.keys()]
