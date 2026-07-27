"""Extract Organization-origin relations from gkx_element into TRSGraph ``dev``.

This ETL deliberately does not create vertices.  It resolves stable VIDs, checks
both endpoints in batches, and inserts only ontology-approved outgoing edges
whose source vertex has the ``Organization`` tag.

Examples:

    python -m script.organization_relation_etl --relation all --dry-run
    python -m script.organization_relation_etl --relation project --batch-size 500 --dry-run
    python -m script.organization_relation_etl --relation all --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from infra.gkx_element import gkx_element_read_session
from infra.graph_db import TRSGraphClient, get_trs_graph_client

logger = logging.getLogger("script.organization_relation_etl")

DEFAULT_SPACE = "dev"
DEFAULT_BATCH_SIZE = 500
SOURCE_SYSTEM = "gkx_element"
MAX_TEXT_LENGTH = 20_000
VID_MAX_BYTES = 64


@dataclass(frozen=True)
class RelationSpec:
    """Static, ontology-backed extraction specification."""

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


EDGE_PROVENANCE = ("source_table", "source_record_id", "ingest_batch", "ingest_time")

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


@dataclass(frozen=True)
class EdgeCandidate:
    """One deterministic edge ready for endpoint validation."""

    edge_type: str
    source_vid: str
    target_vid: str
    target_tag: str
    rank: int
    properties: dict[str, Any]
    source_table: str
    source_record_id: str

    @property
    def identity(self) -> tuple[str, str, str, int]:
        return (self.edge_type, self.source_vid, self.target_vid, self.rank)


@dataclass
class RelationStats:
    """Counters for one source table."""

    queried: int = 0
    valid: int = 0
    written: int = 0
    skipped: int = 0
    source_missing: int = 0
    target_missing: int = 0
    invalid: int = 0
    unresolved_identifier: int = 0
    duplicate: int = 0
    failed: int = 0
    batches: int = 0
    examples: list[str] = field(default_factory=list)


class RelationDataError(ValueError):
    """A single source row cannot be converted safely."""


class SchemaMismatchError(RuntimeError):
    """Required graph schema or source columns are absent."""


def clean_text(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    """Trim a text-like value; return ``None`` for null/blank values."""
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
    """Convert common numeric strings without treating invalid data as zero."""
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
        normalized = raw.replace(",", "").replace("%", "")
        normalized = re.sub(r"[^0-9eE.+-]", "", normalized)
        return float(Decimal(normalized)) if normalized else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def to_bool(value: Any) -> bool | None:
    """Normalize common database and text boolean representations."""
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
    """Keep extra_json bounded while retaining a digest and a readable preview."""
    rendered = compact_json(value)
    if len(rendered) <= max_length:
        return rendered
    logger.warning(
        "replace overlong extra_json (%d chars) with bounded audit summary",
        len(rendered),
    )
    return compact_json(
        {
            "truncated": True,
            "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "original_length": len(rendered),
            "preview": rendered[: max_length // 2],
        }
    )


def parse_json_list(value: Any) -> list[Any]:
    """Parse a JSON array; tolerate a scalar but reject malformed JSON."""
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
    """Apply the dev space FIXED_STRING(64) byte limit deterministically."""
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


def stable_rank(value: str) -> int:
    """Return a deterministic positive Nebula edge rank."""
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") & (
        (1 << 63) - 1
    )


def stable_record_id(
    table: str,
    row: Mapping[str, Any],
    preferred_fields: Iterable[str] = (),
) -> str:
    """Use a business key when complete, otherwise hash the canonical row."""
    preferred = [clean_text(row.get(name)) for name in preferred_fields]
    if preferred and all(preferred):
        return "|".join(value for value in preferred if value is not None)
    canonical = compact_json({key: normalize_json(row[key]) for key in sorted(row)})
    return md5_hex(f"{table}|{canonical}")


def ngql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe nGQL identifier: {value!r}")
    return f"`{value}`"


def ngql_literal(value: Any, *, numeric: bool = False) -> str:
    """Render a safe nGQL literal from already-cleaned values."""
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


class ExactOrganizationResolver:
    """Resolve names to IDs only when the exact trimmed name is unique."""

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
    def load(cls, session: Session) -> ExactOrganizationResolver:
        by_name: dict[str, set[str]] = defaultdict(set)
        for table, id_column, name_columns in cls._SOURCES:
            columns = (id_column, *name_columns)
            select = ",".join(f"`{name}`" for name in columns)
            rows = session.execute(text(f"SELECT {select} FROM `{table}`")).mappings()
            for row in rows:
                org_id = clean_text(row.get(id_column))
                if org_id is None:
                    continue
                for name_column in name_columns:
                    name = clean_text(row.get(name_column))
                    if name is not None:
                        by_name[name].add(org_id)
        return cls(by_name)

    def resolve(self, name: Any) -> str | None:
        key = clean_text(name)
        if key is None:
            return None
        candidates = self._by_name.get(key, set())
        if len(candidates) != 1:
            return None
        return next(iter(candidates))


def _edge_props(
    spec: RelationSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
    business: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "source_table": spec.source_table,
        "source_record_id": record_id,
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
    }
    if "extra_json" in spec.edge_properties:
        props["extra_json"] = bounded_json(
            {key: normalize_json(value) for key, value in row.items()}
        )
    if business:
        props.update(business)
    return {name: props.get(name) for name in spec.edge_properties}


def _candidate(
    spec: RelationSpec,
    source_vid: str,
    target_vid: str,
    record_id: str,
    properties: dict[str, Any],
) -> EdgeCandidate:
    rank_key = f"{spec.edge_type}|{source_vid}|{target_vid}|{record_id}"
    return EdgeCandidate(
        edge_type=spec.edge_type,
        source_vid=source_vid,
        target_vid=target_vid,
        target_tag=spec.target_tag,
        rank=stable_rank(rank_key),
        properties=properties,
        source_table=spec.source_table,
        source_record_id=record_id,
    )


def extract_candidates(
    spec: RelationSpec,
    row: Mapping[str, Any],
    resolver: ExactOrganizationResolver,
    ingest_batch: str,
    ingest_time: str,
) -> list[EdgeCandidate]:
    """Convert one source row without creating or guessing any vertex."""
    base_record_id = stable_record_id(spec.source_table, row, spec.source_record_fields)
    extractor = spec.extractor

    if extractor == "domestic_shareholder":
        source = organization_vid(row.get("inv_org_id"))
        target = organization_vid(row.get("org_id"))
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"ownership_percentage": to_float(row.get("ownership_percentage"))},
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "foreign_shareholder":
        owner_org_id = resolver.resolve(row.get("owners_name"))
        if owner_org_id is None:
            raise RelationDataError("foreign shareholder is not an exact unique Organization")
        source = organization_vid(owner_org_id)
        target = organization_vid(row.get("org_id"))
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"ownership_percentage": to_float(row.get("ownership_percentage"))},
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "investment":
        source = organization_vid(row.get("org_id"))
        target = organization_vid(row.get("inv_org_id"))
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {
                "investment_amount": to_float(row.get("investment_amount")),
                "investment_ratio": to_float(row.get("investment_ratio")),
            },
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "acquisition":
        source = organization_vid(row.get("acquiring_org_id"))
        target = organization_vid(row.get("acquired_org_id"))
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {
                "ma_amount": to_float(row.get("ma_amount")),
                "currency_code": clean_text(row.get("currency_code")),
            },
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "subsidiary":
        source = organization_vid(row.get("org_id"))
        target_id = clean_text(row.get("affiliate")) or clean_text(row.get("affiliates_company_id"))
        if target_id is None:
            target_id = resolver.resolve(row.get("affiliates_name"))
        if target_id is None:
            raise RelationDataError(
                "subsidiary target has no stable or exact unique Organization id"
            )
        target = organization_vid(target_id)
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time)
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "project":
        target = project_vid(row.get("id"))
        result: list[EdgeCandidate] = []
        for index, item in enumerate(parse_json_list(row.get("participating_institution"))):
            name = item.get("name") if isinstance(item, dict) else item
            source_id = None
            if isinstance(item, dict):
                source_id = clean_text(
                    item.get("org_id") or item.get("organization_id") or item.get("institution_id")
                )
            source_id = source_id or resolver.resolve(name)
            if source_id is None:
                logger.debug(
                    "project participant unresolved table=%s record=%s name=%r",
                    spec.source_table,
                    base_record_id,
                    name,
                )
                continue
            record_id = f"{base_record_id}|participant|{index}|{clean_text(name) or source_id}"
            props = _edge_props(spec, row, record_id, ingest_batch, ingest_time)
            result.append(_candidate(spec, organization_vid(source_id), target, record_id, props))
        if not result:
            raise RelationDataError(
                "project has no participant with a stable or exact unique org id"
            )
        return result

    if extractor == "news":
        source = organization_vid(row.get("org_id"))
        target = bounded_vid(f"news_{spec.source_table}_{base_record_id}")
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time)
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "event":
        source = organization_vid(row.get("org_id"))
        target = event_vid(spec.source_table, base_record_id)
        role = clean_text(row.get("case_role") or row.get("exec_person_type")) or "subject"
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time, {"role": role})
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "bankruptcy_party":
        source = organization_vid(row.get("org_id"))
        case_no = clean_text(row.get("case_no"))
        if case_no is None:
            raise RelationDataError("bankruptcy party has no case_no")
        target = event_vid("dwd_org_bankruptcy_public_cases", case_no)
        role = clean_text(row.get("party_role_type")) or "bankruptcy_party"
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time, {"role": role})
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "bid_party":
        source_id = clean_text(row.get("org_id")) or clean_text(row.get("company_id"))
        source = organization_vid(source_id)
        raw_id = clean_text(row.get("u_id"))
        if raw_id is None:
            raise RelationDataError("bid party has no u_id")
        target = event_vid("dwd_bid_base_out", raw_id)
        role = (
            "winner_candidate"
            if spec.source_table == "dwd_bid_win_candidate_out"
            else "purchase_agency"
        )
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time, {"role": role})
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "industry_node":
        source = organization_vid(row.get("antitypic"))
        node_id = clean_text(row.get("node_id"))
        if node_id is None:
            raise RelationDataError("missing industry node id")
        target = bounded_vid(f"node_{node_id}")
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"chain_score": to_float(row.get("chain_score"))},
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "product":
        source = organization_vid(row.get("antitypic"))
        target = product_vid(row.get("tech_product"))
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"tech_product_seq": to_int(row.get("tech_product_seq"))},
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    raise ValueError(f"unsupported extractor: {extractor}")


def source_columns(session: Session, table: str) -> set[str]:
    rows = session.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table"
        ),
        {"table": table},
    )
    return {row[0] for row in rows}


def validate_source_schema(session: Session, specs: Sequence[RelationSpec]) -> None:
    errors: list[str] = []
    for spec in specs:
        columns = source_columns(session, spec.source_table)
        if not columns:
            errors.append(f"{spec.source_table}: table missing")
            continue
        missing = sorted(set(spec.required_columns) - columns)
        if missing:
            errors.append(f"{spec.source_table}: missing columns {', '.join(missing)}")
    if errors:
        raise SchemaMismatchError("; ".join(errors))


def iter_source_rows(
    session: Session,
    spec: RelationSpec,
    *,
    max_records: int | None,
) -> Iterator[dict[str, Any]]:
    sql = f"SELECT * FROM `{spec.source_table}` ORDER BY 1"
    params: dict[str, Any] = {}
    if max_records is not None:
        sql += " LIMIT :limit"
        params["limit"] = max_records
    rows = session.execute(text(sql), params).mappings().yield_per(500)
    for row in rows:
        yield dict(row)


def existing_vids(
    graph: TRSGraphClient,
    tag: str,
    vids: Iterable[str],
    *,
    batch_size: int,
) -> set[str]:
    """Batch-fetch tagged vertices and cache the positive results."""
    unique = sorted(set(vids))
    found: set[str] = set()
    tag_identifier = ngql_identifier(tag)
    for batch in chunks(unique, batch_size):
        values = ",".join(ngql_literal(vid) for vid in batch)
        query = f"FETCH PROP ON {tag_identifier} {values} YIELD id(vertex) AS vid;"
        result = graph.execute_read(query)
        for record in result.records:
            vid = clean_text(record.get("vid"))
            if vid is not None:
                found.add(vid)
    return found


def render_edge_insert(spec: RelationSpec, candidates: Sequence[EdgeCandidate]) -> str:
    """Build one deterministic, property-ordered INSERT EDGE statement."""
    if not candidates:
        raise ValueError("cannot render an empty edge insert")
    props = ",".join(ngql_identifier(name) for name in spec.edge_properties)
    rows: list[str] = []
    for item in candidates:
        values = ",".join(
            ngql_literal(
                item.properties.get(name),
                numeric=name in spec.numeric_properties,
            )
            for name in spec.edge_properties
        )
        rows.append(
            f"{ngql_literal(item.source_vid)}->{ngql_literal(item.target_vid)}"
            f"@{item.rank}:({values})"
        )
    return f"INSERT EDGE {ngql_identifier(spec.edge_type)} ({props}) VALUES " + ",".join(rows) + ";"


def _selected_specs(
    relation: str,
    *,
    domestic_only: bool,
    foreign_only: bool,
) -> list[RelationSpec]:
    specs = [spec for spec in RELATION_SPECS if relation == "all" or spec.key == relation]
    if domestic_only:
        specs = [spec for spec in specs if spec.scope == "domestic"]
    if foreign_only:
        specs = [spec for spec in specs if spec.scope == "foreign"]
    return specs


def _schema_available(
    spec: RelationSpec,
    *,
    labels: set[str],
    edge_types: set[str],
) -> tuple[bool, str]:
    if "Organization" not in labels:
        return False, "Organization tag is missing"
    if spec.target_tag not in labels:
        return False, f"{spec.target_tag} tag is missing"
    if spec.edge_type not in edge_types:
        return False, f"{spec.edge_type} edge is missing"
    return True, ""


def _process_candidate_batch(
    spec: RelationSpec,
    candidates: Sequence[EdgeCandidate],
    *,
    graph: TRSGraphClient,
    batch_size: int,
    dry_run: bool,
    stats: RelationStats,
) -> None:
    deduplicated: dict[tuple[str, str, str, int], EdgeCandidate] = {}
    for candidate in candidates:
        if candidate.identity in deduplicated:
            stats.duplicate += 1
            continue
        deduplicated[candidate.identity] = candidate

    unique = list(deduplicated.values())
    source_found = existing_vids(
        graph,
        "Organization",
        (item.source_vid for item in unique),
        batch_size=batch_size,
    )
    target_found = existing_vids(
        graph,
        spec.target_tag,
        (item.target_vid for item in unique),
        batch_size=batch_size,
    )
    ready: list[EdgeCandidate] = []
    for item in unique:
        missing_source = item.source_vid not in source_found
        missing_target = item.target_vid not in target_found
        if missing_source:
            stats.source_missing += 1
        if missing_target:
            stats.target_missing += 1
        if missing_source or missing_target:
            stats.skipped += 1
            logger.info(
                "skip missing endpoint table=%s record=%s source=%s target=%s",
                item.source_table,
                item.source_record_id,
                item.source_vid if missing_source else "ok",
                item.target_vid if missing_target else "ok",
            )
            continue
        ready.append(item)

    stats.valid += len(ready)
    for write_batch in chunks(ready, batch_size):
        query = render_edge_insert(spec, write_batch)
        if len(stats.examples) < 3:
            stats.examples.append(query[:1_500])
        if dry_run:
            logger.info(
                "dry-run relation=%s table=%s edges=%d",
                spec.edge_type,
                spec.source_table,
                len(write_batch),
            )
            continue
        try:
            graph.execute_write(query)
            stats.written += len(write_batch)
        except Exception:
            stats.failed += len(write_batch)
            logger.exception(
                "graph write failed edge=%s table=%s rows=%d ngql_prefix=%s",
                spec.edge_type,
                spec.source_table,
                len(write_batch),
                query[:500],
            )


def run_etl(
    *,
    relation: str = "all",
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = True,
    max_records: int | None = None,
    domestic_only: bool = False,
    foreign_only: bool = False,
    ingest_batch: str | None = None,
    graph: TRSGraphClient | None = None,
    session: Session | None = None,
) -> dict[str, RelationStats]:
    """Run selected relation extractors and return per-table statistics."""
    if domestic_only and foreign_only:
        raise ValueError("domestic_only and foreign_only are mutually exclusive")
    if relation != "all" and relation not in RELATION_KEYS:
        raise ValueError(f"unknown relation: {relation}")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_records is not None and max_records <= 0:
        raise ValueError("max_records must be positive")

    specs = _selected_specs(
        relation,
        domestic_only=domestic_only,
        foreign_only=foreign_only,
    )
    if not specs:
        raise ValueError("no relation specs selected")

    now = datetime.now(UTC)
    ingest_time = now.isoformat(timespec="seconds")
    ingest_batch = ingest_batch or f"ORG_REL_{now.strftime('%Y%m%dT%H%M%SZ')}"
    graph = graph or get_trs_graph_client()

    owns_session = session is None
    session_cm = gkx_element_read_session() if owns_session else None
    if session is None:
        assert session_cm is not None
        session = session_cm.__enter__()

    try:
        validate_source_schema(session, specs)
        resolver = ExactOrganizationResolver.load(session)
        labels = set(graph.labels())
        edge_types = set(graph.edge_types())
        results: dict[str, RelationStats] = {}

        for spec in specs:
            stats = RelationStats()
            results[spec.source_table] = stats
            available, reason = _schema_available(spec, labels=labels, edge_types=edge_types)
            if not available:
                if relation != "all":
                    raise SchemaMismatchError(
                        f"{spec.key}: {reason}; initialize the ontology schema first"
                    )
                logger.warning("skip relation=%s table=%s: %s", spec.key, spec.source_table, reason)
                continue

            pending: list[EdgeCandidate] = []
            for row in iter_source_rows(session, spec, max_records=max_records):
                stats.queried += 1
                try:
                    extracted = extract_candidates(
                        spec,
                        row,
                        resolver,
                        ingest_batch,
                        ingest_time,
                    )
                except RelationDataError as exc:
                    stats.invalid += 1
                    stats.skipped += 1
                    if "exact unique" in str(exc) or "stable" in str(exc):
                        stats.unresolved_identifier += 1
                    logger.info(
                        "skip invalid table=%s record=%s reason=%s",
                        spec.source_table,
                        stable_record_id(spec.source_table, row, spec.source_record_fields),
                        exc,
                    )
                    continue
                except Exception:
                    stats.invalid += 1
                    stats.skipped += 1
                    logger.exception(
                        "skip dirty row table=%s row=%s",
                        spec.source_table,
                        compact_json(row)[:500],
                    )
                    continue
                pending.extend(extracted)
                if len(pending) >= batch_size:
                    stats.batches += 1
                    _process_candidate_batch(
                        spec,
                        pending,
                        graph=graph,
                        batch_size=batch_size,
                        dry_run=dry_run,
                        stats=stats,
                    )
                    pending = []

            if pending:
                stats.batches += 1
                _process_candidate_batch(
                    spec,
                    pending,
                    graph=graph,
                    batch_size=batch_size,
                    dry_run=dry_run,
                    stats=stats,
                )
            logger.info(
                "completed relation=%s edge=%s table=%s stats=%s",
                spec.key,
                spec.edge_type,
                spec.source_table,
                compact_json(asdict(stats)),
            )
        return results
    finally:
        if owns_session and session_cm is not None:
            session_cm.__exit__(None, None, None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract Organization-origin edges into existing TRSGraph dev vertices."
    )
    parser.add_argument(
        "--relation",
        choices=("all", *RELATION_KEYS),
        default="all",
        help="relation family to process",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-records", type=int)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--domestic-only", action="store_true")
    scope.add_argument("--foreign-only", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--write", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)
    parser.add_argument("--space", choices=(DEFAULT_SPACE,), default=DEFAULT_SPACE)
    parser.add_argument("--ingest-batch")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    os.environ["TRS_GRAPH_SPACE"] = args.space
    results = run_etl(
        relation=args.relation,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        max_records=args.max_records,
        domestic_only=args.domestic_only,
        foreign_only=args.foreign_only,
        ingest_batch=args.ingest_batch,
    )
    summary = {table: asdict(stats) for table, stats in results.items()}
    logger.info("organization relation ETL summary=%s", compact_json(summary))
    return 1 if any(item.failed for item in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
