"""纯函数：项目入图用的解析 / VID / 属性构建（便于单测）。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip())


def normalize_keyword(value: str | None) -> str:
    return normalize_name(value).lower()


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def person_vid(name: str) -> str:
    return f"person_{md5_hex(normalize_name(name))}"


def org_vid(name: str) -> str:
    return f"org_{md5_hex(normalize_name(name))}"


def keyword_vid(keyword: str) -> str:
    return f"keyword_{md5_hex(normalize_keyword(keyword))}"


def project_vid(project_id: str) -> str:
    return f"project_{project_id}"


def paper_stub_vid(*, doi: str | None = None, title: str | None = None) -> str:
    key = normalize_name(doi) or normalize_name(title)
    if not key:
        key = "unknown"
    return f"paper_{md5_hex(key.lower() if doi else key)}"


def patent_stub_vid(*, patent_number: str | None = None, title: str | None = None) -> str:
    number = normalize_name(patent_number)
    if number:
        # keep alnum for safer VID within FIXED_STRING(64)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", number)
        vid = f"patent_{safe}"
        return vid[:64]
    title_key = normalize_name(title) or "unknown"
    return f"patent_{md5_hex(title_key)}"


def parse_list(raw: Any) -> list[str]:
    """解析 JSON 数组 / 逗号分隔 / 单字符串 → 非空字符串列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [normalize_name(str(x)) for x in raw if normalize_name(str(x))]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [normalize_name(str(x)) for x in data if normalize_name(str(x))]
        except json.JSONDecodeError:
            pass
    if "," in text:
        return [normalize_name(p) for p in text.split(",") if normalize_name(p)]
    return [normalize_name(text)]


def parse_json_objects(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    text = str(raw).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def to_str_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# 实体（Project）置信度核心字段：标题为强字段，其余按完整度加权。
# 与关系匹配置信度（confidence_from_method，写在边上）互补：这里度量
# “这条项目源记录本身有多完整可信”，与匹配结果无关、可在灌点阶段一次算定。
PROJECT_CONFIDENCE_FIELDS = (
    "title",
    "abstract",
    "funded_amount",
    "discipline",
    "approval_year",
    "fund_category",
)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, Decimal):
        return float(value) != 0.0
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    return bool(value)


def project_confidence(row: Any) -> float:
    """实体置信度：源记录核心字段完整度（接受 ORM 行或图节点属性 dict）。

    标题缺失直接封顶 0.6（强字段）；否则按填充比例，下限 0.3、上限 1.0。
    """
    if isinstance(row, dict):
        values = {f: row.get(f) for f in PROJECT_CONFIDENCE_FIELDS}
    else:
        values = {f: getattr(row, f, None) for f in PROJECT_CONFIDENCE_FIELDS}
    filled = sum(1 for v in values.values() if _has_value(v))
    ratio = filled / len(PROJECT_CONFIDENCE_FIELDS)
    if not _has_value(values["title"]):
        ratio = min(ratio, 0.6)
    return round(max(0.3, ratio), 4)


def build_project_props(
    row: Any,
    *,
    source: str,
    source_table: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    """从 dwd_*_project ORM 行构建 Project 属性（不含产出计数）。"""
    return {
        "vid": project_vid(row.id),
        "confidence": project_confidence(row),
        "project_number": row.project_number or "",
        "title": row.title or "",
        "project_source": row.project_source or "",
        "project_level": row.project_level or "",
        "funded_amount": to_float(row.funded_amount),
        "discipline": row.discipline or "",
        "discipline_code": row.discipline_code or "",
        "fund_category": row.fund_category or "",
        "funded_region": row.funded_province or "",
        "approval_year": to_str_date(row.approval_year),
        "approval_time": to_str_date(row.approval_time),
        "research_period": row.research_period or "",
        "abstract": row.abstract or "",
        "final_report_abstract": getattr(row, "final_report_abstract", None) or "",
        "project_page_url": row.project_page_url or "",
        "source": source,
        "source_system": "gkx_element",
        "source_table": source_table,
        "source_record_id": row.id,
        "source_url": row.project_page_url or "",
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
        "source_update_time": to_str_date(
            getattr(row, "updated_time", None) or getattr(row, "update_time", None)
        ),
    }


def to_output_awards_json(raw: Any) -> str:
    """把 dwd_*_project_output.output_awards 规范成图属性 string（JSON 数组）。"""
    if raw is None:
        return "[]"
    if isinstance(raw, (list, dict)):
        return json.dumps(raw, ensure_ascii=False)
    text = str(raw).strip()
    if not text:
        return "[]"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps([text], ensure_ascii=False)
    if isinstance(parsed, (list, dict)):
        return json.dumps(parsed, ensure_ascii=False)
    return "[]"


def build_output_count_props(row: Any) -> dict[str, Any]:
    return {
        "total_outputs": to_int(row.total_outputs),
        "journal_articles_count": to_int(row.journal_articles_count),
        "conference_papers_count": to_int(row.conference_papers_count),
        "books_count": to_int(getattr(row, "books_count", None)),
        "degree_papers_count": to_int(row.degree_papers_count),
        "patents_count": to_int(row.patents_count),
        "clinical_trials_count": to_int(getattr(row, "clinical_trials_count", None)),
        "products_count": to_int(getattr(row, "products_count", None)),
        "awards_count": to_int(row.awards_count),
        "output_awards": to_output_awards_json(getattr(row, "output_awards", None)),
        "reports_count": to_int(row.reports_count),
        "other_outputs_count": to_int(row.other_outputs_count),
    }


def edge_provenance(
    *,
    source_table: str,
    source_record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, str]:
    return {
        "source_table": source_table,
        "source_record_id": source_record_id,
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
    }


# 逻辑/标书溯源表名（真实 MySQL 多为 dwd_org_base_info；图属性用此逻辑名）。
ORGANIZATION_SOURCE_TABLE = "organization_base"

EXACT_MATCH_METHODS = frozenset(
    {
        "name_exact",
        "doi_exact",
        "doi_registry_exact",
        "patent_number_exact",
        "patent_number_registry_exact",
        "title_exact",
        "title_year_exact",
    }
)


def confidence_from_method(method: str, evidence: str = "") -> float:
    """实体/关系匹配置信度：精确类 1.0；hybrid 取 evidence 中 score；否则 0.9。"""
    if method in EXACT_MATCH_METHODS:
        return 1.0
    match = re.search(r"score=([0-9.]+)", evidence or "")
    if match:
        try:
            return round(float(match.group(1)), 4)
        except ValueError:
            pass
    return 0.9


def organization_id_from_vid(vid: str) -> str:
    """从 Organization VID 解析稳定 ID（org_{id} → id；否则原样返回）。"""
    text = str(vid or "").strip()
    if text.startswith("org_"):
        return text[4:] or text
    return text


def resolve_organization_id(
    vid: str,
    *,
    node_props: dict[str, Any] | None = None,
    cache: dict[str, str] | None = None,
) -> str:
    """优先 cache / 节点 source_record_id|org_id|organization_id，再回退 VID 解析。"""
    if cache and vid in cache and cache[vid]:
        return cache[vid]
    props = node_props or {}
    for key in ("source_record_id", "org_id", "organization_id"):
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return organization_id_from_vid(vid)


def match_audit_props(method: str, evidence: str = "") -> dict[str, Any]:
    """边审计三件套：match_method / match_evidence / confidence。"""
    return {
        "match_method": method or "",
        "match_evidence": evidence or "",
        "confidence": confidence_from_method(method or "", evidence or ""),
    }


def funded_by_org_props(organization_id: str) -> dict[str, str]:
    return {
        "organization_id": organization_id,
        "organization_source_table": ORGANIZATION_SOURCE_TABLE,
    }
