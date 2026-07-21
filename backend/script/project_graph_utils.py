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


def build_project_props(
    row: Any,
    *,
    source: str,
    source_table: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    """从 ods_*_project ORM 行构建 Project 属性（不含产出计数）。"""
    return {
        "vid": project_vid(row.id),
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
        "source_system": "gkx_local",
        "source_table": source_table,
        "source_record_id": row.id,
        "source_url": row.project_page_url or "",
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
        "source_update_time": to_str_date(row.update_time),
    }


def build_output_count_props(row: Any) -> dict[str, Any]:
    return {
        "total_outputs": to_int(row.total_outputs),
        "journal_articles_count": to_int(row.journal_articles_count),
        "conference_papers_count": to_int(row.conference_papers_count),
        "books_count": to_int(row.books_count),
        "degree_papers_count": to_int(row.degree_papers_count),
        "patents_count": to_int(row.patents_count),
        "clinical_trials_count": to_int(row.clinical_trials_count),
        "products_count": to_int(row.products_count),
        "awards_count": to_int(row.awards_count),
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
