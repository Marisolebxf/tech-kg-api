"""Shared, side-effect-free primitives for organization entity and relation ETLs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import math
import os
import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

logger = logging.getLogger("script.organization_etl_common")

DEFAULT_SPACE = "dev"
SOURCE_SYSTEM = "gkx_element"
MAX_TEXT_LENGTH = 20_000
VID_MAX_BYTES = 64
EDGE_PROVENANCE = ("source_table", "source_record_id", "ingest_batch", "ingest_time")
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "dev_organization_schema.ngql"
MAPPING_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "国内外机构要素库全字段图谱映射说明.md"
)


class RelationDataError(ValueError):
    """One source row cannot be converted into a safe graph relation."""


@dataclass(frozen=True)
class RelationSpec:
    """One ontology-backed Organization-origin relation extraction specification."""

    key: str
    source_table: str
    edge_type: str
    target_tag: str
    scope: str
    extractor: str
    required_columns: tuple[str, ...]
    edge_properties: tuple[str, ...]
    numeric_properties: frozenset[str] = frozenset()
    source_record_fields: tuple[str, ...] = ()


RELATION_SPECS: tuple[RelationSpec, ...] = (
    RelationSpec(
        "shareholder",
        "dwd_org_shareholder_info",
        "SHAREHOLDER_OF",
        "Organization",
        "domestic",
        "domestic_shareholder",
        ("org_id", "inv_org_id", "owners_type", "ownership_percentage"),
        ("ownership_percentage", "extra_json", *EDGE_PROVENANCE),
        frozenset({"ownership_percentage"}),
        ("inv_org_id", "org_id", "owners_type"),
    ),
    RelationSpec(
        "shareholder",
        "dwd_forg_shareholder_info",
        "SHAREHOLDER_OF",
        "Organization",
        "foreign",
        "foreign_shareholder",
        ("org_id", "owners_name", "ownership_percentage"),
        ("ownership_percentage", "extra_json", *EDGE_PROVENANCE),
        frozenset({"ownership_percentage"}),
        ("owners_name", "org_id"),
    ),
    RelationSpec(
        "investment",
        "dwd_org_invest_info",
        "INVESTS_IN",
        "Organization",
        "domestic",
        "investment",
        ("org_id", "inv_org_id", "investment_amount", "investment_ratio"),
        ("investment_amount", "investment_ratio", "extra_json", *EDGE_PROVENANCE),
        frozenset({"investment_amount", "investment_ratio"}),
        ("org_id", "inv_org_id"),
    ),
    RelationSpec(
        "acquisition",
        "dwd_org_merger_acquisition_info",
        "ACQUIRES",
        "Organization",
        "domestic",
        "acquisition",
        ("acquiring_org_id", "acquired_org_id", "ma_amount", "currency_code"),
        ("ma_amount", "currency_code", "extra_json", *EDGE_PROVENANCE),
        frozenset({"ma_amount"}),
        ("acquiring_org_id", "acquired_org_id"),
    ),
    RelationSpec(
        "subsidiary",
        "dwd_forg_subsidiary_info",
        "SUBSIDIARY_OF",
        "Organization",
        "foreign",
        "subsidiary",
        ("org_id", "affiliate", "affiliates_company_id", "affiliates_name"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "affiliate", "affiliates_company_id", "affiliates_name"),
    ),
    RelationSpec(
        "project",
        "dwd_zh_project",
        "PARTICIPATES_IN",
        "Project",
        "domestic",
        "project",
        ("id", "participating_institution"),
        EDGE_PROVENANCE,
        source_record_fields=("id",),
    ),
    RelationSpec(
        "project",
        "dwd_en_project",
        "PARTICIPATES_IN",
        "Project",
        "foreign",
        "project",
        ("id", "participating_institution"),
        EDGE_PROVENANCE,
        source_record_fields=("id",),
    ),
    RelationSpec(
        "news",
        "dwd_org_important_news_info",
        "HAS_NEWS",
        "News",
        "domestic",
        "news",
        ("org_id", "news_title", "news_date", "news_content"),
        ("extra_json", *EDGE_PROVENANCE),
    ),
    RelationSpec(
        "event",
        "dwd_org_annual_financial_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "year"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "year"),
    ),
    RelationSpec(
        "event",
        "dwd_org_stock_finance_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "occur_period"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "occur_period"),
    ),
    RelationSpec(
        "event",
        "dwd_forg_stock_fin_info",
        "INVOLVED_IN",
        "Event",
        "foreign",
        "event",
        ("org_id", "occur_period"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "occur_period"),
    ),
    RelationSpec(
        "event",
        "dwd_org_changerecord_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "update_date", "update_content"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "update_date", "update_content"),
    ),
    RelationSpec(
        "event",
        "dwd_org_financing_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "completion_date", "funding_round"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "completion_date", "funding_round"),
    ),
    RelationSpec(
        "event",
        "dwd_org_recruit_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "release_date", "job_title"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "release_date", "job_title"),
    ),
    RelationSpec(
        "event",
        "dwd_org_company_abnormal",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "abnormal_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("abnormal_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_company_punish",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "penalty_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("penalty_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_company_illegal",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "sv_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("sv_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_risk_tax_punish",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "tax_vio_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("tax_vio_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_opt_judicial_case",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "case_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("case_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_risk_shixin",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "dishonest_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("dishonest_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_risk_zhixing",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "exec_person_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("exec_person_id",),
    ),
    RelationSpec(
        "event",
        "dwd_org_bankruptcy_public_cases_list",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bankruptcy_party",
        ("org_id", "case_no", "bankruptcy_party_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("bankruptcy_party_id",),
    ),
    RelationSpec(
        "event",
        "dwd_bid_win_candidate_out",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bid_party",
        ("u_id", "org_id", "relate_type"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("u_id", "org_id", "ranking"),
    ),
    RelationSpec(
        "event",
        "dwd_bid_purchase_agency_out",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bid_party",
        ("u_id", "company_id", "relate_type"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("u_id", "company_id", "relate_type"),
    ),
    RelationSpec(
        "industry_node",
        "dwd_org_industry_chain_dtl",
        "BELONGS_TO_NODE",
        "IndustryNode",
        "domestic",
        "industry_node",
        ("antitypic", "node_id", "chain_score"),
        ("chain_score", *EDGE_PROVENANCE),
        frozenset({"chain_score"}),
        ("antitypic", "node_id"),
    ),
    RelationSpec(
        "product",
        "dwd_org_industry_chain_prod_dtl",
        "PRODUCES",
        "Product",
        "domestic",
        "product",
        ("antitypic", "tech_product", "tech_product_seq"),
        ("tech_product_seq", *EDGE_PROVENANCE),
        frozenset({"tech_product_seq"}),
        ("antitypic", "tech_product"),
    ),
)

RELATION_KEYS = tuple(dict.fromkeys(spec.key for spec in RELATION_SPECS))


def clean_text(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    """Trim text-like input and return None for null or blank values."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, datetime):
        result = value.isoformat(sep=" ")
    elif isinstance(value, date):
        result = value.isoformat()
    else:
        result = str(value).strip()
    if not result:
        return None
    if len(result) > max_length:
        logger.warning("truncate overlong value from %d to %d characters", len(result), max_length)
        result = result[:max_length]
    return result


def to_float(value: Any) -> float | None:
    """Convert common numeric strings without silently treating invalid values as zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if isinstance(value, (int, float, Decimal)):
            return float(value)
        raw = clean_text(value)
        if raw is None or raw.casefold() in {"-", "n/a", "n.a.", "null", "none"}:
            return None
        normalized = re.sub(r"[^0-9eE.+-]", "", raw.replace(",", "").replace("%", ""))
        return float(Decimal(normalized)) if normalized else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return None if number is None else int(number)


def to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    raw = (clean_text(value) or "").casefold()
    if raw in {"1", "true", "yes", "y", "是"}:
        return True
    if raw in {"0", "false", "no", "n", "否"}:
        return False
    return None


def normalize_json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=normalize_json,
        separators=(",", ":"),
    )


def bounded_json(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    rendered = compact_json(value)
    if len(rendered) <= max_length:
        return rendered
    logger.warning("replace overlong extra_json (%d chars) with audit summary", len(rendered))
    return compact_json(
        {
            "truncated": True,
            "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "original_length": len(rendered),
            "preview": rendered[: max_length // 2],
        }
    )


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    raw = clean_text(value)
    if raw is None:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RelationDataError(f"invalid JSON array: {raw[:120]}") from exc
    if parsed is None:
        return []
    return parsed if isinstance(parsed, list) else [parsed]


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def bounded_vid(value: str, max_bytes: int = VID_MAX_BYTES) -> str:
    if len(value.encode("utf-8")) <= max_bytes:
        return value
    suffix = "_" + md5_hex(value)
    budget = max_bytes - len(suffix.encode("utf-8"))
    chars: list[str] = []
    used = 0
    for char in value:
        width = len(char.encode("utf-8"))
        if used + width > budget:
            break
        chars.append(char)
        used += width
    return "".join(chars) + suffix


def organization_vid(org_id: Any) -> str:
    raw = clean_text(org_id)
    if raw is None:
        raise RelationDataError("missing organization id")
    return bounded_vid(f"org_{raw}")


def project_vid(project_id: Any) -> str:
    raw = clean_text(project_id)
    if raw is None:
        raise RelationDataError("missing project id")
    return bounded_vid(f"project_{raw}")


def event_vid(table: str, record_id: str) -> str:
    return bounded_vid(f"event_{table}_{record_id}")


def product_vid(name: Any) -> str:
    raw = clean_text(name)
    if raw is None:
        raise RelationDataError("missing product name")
    normalized = unicodedata.normalize("NFKC", raw).casefold()
    return bounded_vid(f"product_{md5_hex(normalized)}")


def datasource_vid(table: str, *, raw: bool = False) -> str:
    prefix = "raw" if raw else "ds"
    return bounded_vid(f"{prefix}_{table}")


def stable_record_id(
    table: str,
    row: Mapping[str, Any],
    preferred_fields: Iterable[str] = (),
) -> str:
    """Return the single canonical source_record_id algorithm used by every ETL."""
    preferred = [clean_text(row.get(name)) for name in preferred_fields]
    if preferred and all(preferred):
        return "|".join(value for value in preferred if value is not None)
    canonical = compact_json({key: normalize_json(row[key]) for key in sorted(row)})
    return md5_hex(f"{table}|{canonical}")


def stable_rank(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") & (
        (1 << 63) - 1
    )


def edge_rank(edge_type: str, source_vid: str, target_vid: str, source_record_id: str) -> int:
    """Return the only supported deterministic graph edge rank."""
    return stable_rank(f"{edge_type}|{source_vid}|{target_vid}|{source_record_id}")


def edge_provenance(
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


def node_provenance(
    table: str,
    record_id: str,
    row: Mapping[str, Any],
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    return {
        "source_system": SOURCE_SYSTEM,
        "source_table": table,
        "source_record_id": record_id,
        "source_url": clean_text(
            row.get("source_url")
            or row.get("original_link")
            or row.get("original_textlink")
            or row.get("web_link")
        ),
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
        "source_update_time": clean_text(row.get("updated_time") or row.get("update_time")),
    }


def ngql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe nGQL identifier: {value!r}")
    return f"`{value}`"


def ngql_literal(value: Any, *, numeric: bool = False) -> str:
    if numeric:
        number = to_float(value)
        if number is None:
            return "NULL"
        return str(int(number)) if number.is_integer() else format(number, ".15g")
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(clean_text(value) or "", ensure_ascii=False)


def chunks(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    for start in range(0, len(items), size):
        yield items[start : start + size]


@contextmanager
def exclusive_etl_lock(
    process_name: str,
    ingest_batch: str,
    *,
    lock_path: Path | None = None,
) -> Iterator[None]:
    """Prevent entity and relation writers from running at the same time."""
    path = lock_path or Path(
        os.environ.get("ORGANIZATION_ETL_LOCK_FILE", "/tmp/tech_kg_organization_etl.lock")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "unknown owner"
            raise RuntimeError(f"another organization ETL is running: {owner}") from exc
        owner = {
            "pid": os.getpid(),
            "process": process_name,
            "ingest_batch": ingest_batch,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        handle.seek(0)
        handle.truncate()
        handle.write(compact_json(owner))
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
