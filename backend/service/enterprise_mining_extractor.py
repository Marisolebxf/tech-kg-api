"""专家-企业关系 LLM 抽取：从学者传记文本抽取关联企业及关系属性。

单次 LLM 调用做结构化抽取；LLM 不可用或解析失败时降级为正则抽取。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

ENTERPRISE_KEYWORDS = ("公司", "集团", "厂", "股份", "有限")
VALID_RELATION_TYPES = {
    "employment",
    "advisor",
    "rd_cooperation",
    "project_cooperation",
    "tech_cooperation",
}
VALID_ROLES = {"chief_scientist", "cto", "technical_advisor", "rd_lead", "engineer"}
DEFAULT_RELATION_TYPE = "tech_cooperation"
DEFAULT_ROLE = "engineer"

_EXTRACT_PROMPT = """你是科技专家-企业关系抽取助手。下面是学者{name}的简介、工作经历、教育背景与所属机构。
请从中抽取该学者与【企业】（公司/集团/厂/股份，不含高校/研究所/政府/医院）的关联关系。
重要：enterprise_name 必须是企业的完整全称（如"福建帝视信息科技有限公司"），不要只抽"科技有限公司""有限公司"等后缀碎片。
只返回 JSON 数组，每个元素形如：
{{"enterprise_name":"企业完整全称","relation_type":"employment|advisor|rd_cooperation|project_cooperation|tech_cooperation","role":"chief_scientist|cto|technical_advisor|rd_lead|engineer","tech_field":"技术领域","period_start":"YYYY-MM-DD或空","period_end":"YYYY-MM-DD或空","evidence":"原文依据片段"}}
无可抽取的企业关系时返回 []。只输出 JSON，不要解释。

中文简介：{bio_zh}
工作经历：{work_experience_zh}
教育背景：{education_background_zh}
所属机构：{scholar_org_name_zh}"""


def extract_relations(llm: Any, profile: dict[str, Any]) -> tuple[list[dict], bool]:
    """返回 (抽取结果列表, degraded)。

    degraded=True 表示走了正则降级（LLM 不可用或解析失败）。
    """
    if llm is None:
        return _fallback_extract(profile), True
    text = llm.synthesize(_build_prompt(profile))
    parsed = _parse_json_array(text) if text else None
    if parsed is None:
        logger.warning("LLM 抽取解析失败，降级正则")
        return _fallback_extract(profile), True
    items = [_normalize(it) for it in parsed if isinstance(it, dict)]
    items = [it for it in items if it["enterprise_name"]]
    return items, False


def _build_prompt(profile: dict[str, Any]) -> str:
    return _EXTRACT_PROMPT.format(
        name=profile.get("name_zh", ""),
        bio_zh=profile.get("bio_zh", ""),
        work_experience_zh=profile.get("work_experience_zh", ""),
        education_background_zh=profile.get("education_background_zh", ""),
        scholar_org_name_zh=profile.get("scholar_org_name_zh", ""),
    )


def _parse_json_array(text: str) -> list | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001
        return None


def _normalize(it: dict) -> dict:
    rt = it.get("relation_type")
    role = it.get("role")
    return {
        "enterprise_name": (it.get("enterprise_name") or "").strip(),
        "relation_type": rt if rt in VALID_RELATION_TYPES else DEFAULT_RELATION_TYPE,
        "role": role if role in VALID_ROLES else DEFAULT_ROLE,
        "tech_field": (it.get("tech_field") or "").strip(),
        "period_start": _norm_date(it.get("period_start")),
        "period_end": _norm_date(it.get("period_end")),
        "evidence": (it.get("evidence") or "").strip(),
    }


def _norm_date(v: Any) -> str:
    s = (str(v or "")).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-01-01"
    return ""


def _fallback_extract(profile: dict[str, Any]) -> list[dict]:
    """LLM 不可用时，从工作经历/简介中按关键词正则抽取企业名。"""
    items: list[dict] = []
    seen: set[str] = set()
    for field in ("work_experience_zh", "bio_zh", "education_background_zh"):
        text = profile.get(field) or ""
        for tok in re.split(r"[\n,，;；、0-9\-\.]+", text):
            tok = tok.strip(" ：:·-")
            if len(tok) < 3:
                continue
            if not any(kw in tok for kw in ENTERPRISE_KEYWORDS):
                continue
            if tok in seen:
                continue
            seen.add(tok)
            items.append(
                {
                    "enterprise_name": tok,
                    "relation_type": "employment",
                    "role": DEFAULT_ROLE,
                    "tech_field": "",
                    "period_start": "",
                    "period_end": "",
                    "evidence": tok,
                }
            )
    return items
