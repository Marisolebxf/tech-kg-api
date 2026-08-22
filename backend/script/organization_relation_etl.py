"""Extract organization-domain relations from gkx_element into TRSGraph ``dev``.

This ETL deliberately does not create vertices.  It resolves stable VIDs, checks
both endpoints in batches, and inserts only ontology-approved directed edges.
Organization may be the source or target according to the ontology.  An exact
existing edge-type/source/target/rank identity is skipped instead of overwritten.

Examples:

    python -m script.organization_relation_etl --relation all --dry-run
    python -m script.organization_relation_etl --relation project --batch-size 500 --dry-run
    python -m script.organization_relation_etl --relation all --write
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from infra.gkx_element import gkx_element_read_session
from infra.graph_db import TRSGraphClient, get_trs_graph_client
from infra.milvus import OrganizationMilvusStore
from script.organization_etl_common import (
    DEFAULT_SPACE,
    DOMAIN_TABLE_BY_NAME,
    RELATION_KEYS,
    RELATION_SPECS,
    RelationDataError,
    RelationSpec,
    bounded_json,
    bounded_vid,
    chunks,
    clean_text,
    compact_json,
    edge_rank,
    event_vid,
    exclusive_etl_lock,
    is_virtual_source_row,
    news_vid,
    ngql_identifier,
    ngql_literal,
    normalize_json,
    organization_id_from_row,
    organization_vid,
    parse_json_list,
    person_vid,
    product_vid,
    project_vid,
    relation_confidence,
    stable_rank,
    stable_record_id,
    to_bool,
    to_float,
    to_int,
)
from service.organization_entity_alignment import (
    AlignmentAuditWriter,
    BM25SparseEncoder,
    HashingDenseEncoder,
    HybridOrganizationResolver,
    OrganizationHybridMatcher,
)

logger = logging.getLogger("script.organization_relation_etl")

DEFAULT_BATCH_SIZE = 500
DEFAULT_ALIGNMENT_STATE_DIR = Path(".cache/organization_milvus")
DEFAULT_ALIGNMENT_DENSE_DIMENSION = 384
assert {spec.source_table for spec in RELATION_SPECS} <= set(DOMAIN_TABLE_BY_NAME)

__all__ = [
    "RELATION_KEYS",
    "RELATION_SPECS",
    "RelationDataError",
    "RelationSpec",
    "bounded_json",
    "clean_text",
    "ngql_literal",
    "parse_json_list",
    "stable_rank",
    "to_bool",
    "to_float",
    "to_int",
]


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
    source_tag: str = "Organization"

    @property
    def identity(self) -> tuple[str, str, str, int]:
        return (self.edge_type, self.source_vid, self.target_vid, self.rank)


@dataclass
class RelationStats:
    """Counters for one source table."""

    queried: int = 0
    valid: int = 0
    written: int = 0
    updated: int = 0
    skipped: int = 0
    source_missing: int = 0
    target_missing: int = 0
    invalid: int = 0
    unresolved_identifier: int = 0
    duplicate: int = 0
    existing: int = 0
    failed: int = 0
    batches: int = 0
    examples: list[str] = field(default_factory=list)


class SchemaMismatchError(RuntimeError):
    """Required graph schema or source columns are absent."""


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

    def resolve(
        self,
        name: Any,
        context: Mapping[str, Any] | None = None,
    ) -> str | None:
        return self.resolve_exact(name)

    def resolve_exact(self, name: Any) -> str | None:
        key = clean_text(name)
        if key is None:
            return None
        candidates = self._by_name.get(key, set())
        if len(candidates) != 1:
            return None
        return next(iter(candidates))


def resolved_organization_vid(
    raw_id_or_name: Any,
    resolver: Any,
    *,
    fallback_name: Any = None,
    context: Mapping[str, Any] | None = None,
) -> str:
    """Prefer an exact base-table name match, otherwise treat the value as an ID."""
    raw = clean_text(raw_id_or_name)
    exact_id = resolver.resolve(raw, context) if raw is not None else None
    exact_id = exact_id or resolver.resolve(fallback_name, context)
    if exact_id is not None:
        return organization_vid(exact_id)
    if raw is None:
        raise RelationDataError("organization has no stable or exact unique identifier")
    return organization_vid(raw)


def _person_vid_for_row(
    spec: RelationSpec,
    row: Mapping[str, Any],
    person_kind: str,
    name_field: str,
) -> str:
    name = clean_text(row.get(name_field))
    if name is None:
        raise RelationDataError("missing person name")
    birth_date = first_value(
        row,
        "dm_birthdate",
        "bo_birthdate",
        "birth_date",
    )
    country = first_value(
        row,
        "dm_nationalities",
        "bo_country_code",
        "country_code",
    )
    return person_vid(person_kind, row.get("org_id"), name, birth_date, country)


def first_value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if clean_text(row.get(name)) is not None:
            return row.get(name)
    return None


def parse_entity_list(value: Any) -> list[Any]:
    """Accept a JSON array/object or one exact plain-text organization name."""
    if isinstance(value, list):
        return parse_json_list(value)
    if isinstance(value, dict):
        return [value]
    raw = clean_text(value)
    if raw is None:
        return []
    if raw.startswith(("[", "{")):
        return parse_json_list(raw)
    return [raw]


def _edge_props(
    spec: RelationSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
    business: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "organization_id": organization_id_from_row(row),
        "confidence": relation_confidence(row, source_table=spec.source_table),
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
    *,
    source_tag: str | None = None,
    target_tag: str | None = None,
) -> EdgeCandidate:
    return EdgeCandidate(
        edge_type=spec.edge_type,
        source_vid=source_vid,
        target_vid=target_vid,
        source_tag=source_tag or spec.source_tags[0],
        target_tag=target_tag or spec.target_tag,
        rank=edge_rank(spec.edge_type, source_vid, target_vid, record_id),
        properties=properties,
        source_table=spec.source_table,
        source_record_id=record_id,
    )


def _alignment_context(
    spec: RelationSpec,
    row: Mapping[str, Any],
    record_id: str,
    *,
    external_id_fields: Sequence[str] = (),
    country_code_fields: Sequence[str] = (),
    country_fields: Sequence[str] = (),
    province_fields: Sequence[str] = (),
    city_fields: Sequence[str] = (),
    address_fields: Sequence[str] = (),
) -> dict[str, Any]:
    """Collect structured evidence without inventing any source value."""
    return {
        "source_table": spec.source_table,
        "source_record_id": record_id,
        "external_id": first_value(row, *external_id_fields),
        "country_code": first_value(row, *country_code_fields),
        "country": first_value(row, *country_fields),
        "province": first_value(row, *province_fields),
        "city": first_value(row, *city_fields),
        "address": first_value(row, *address_fields),
    }


def _organization_vid_from_row(
    spec: RelationSpec,
    row: Mapping[str, Any],
    resolver: Any,
    record_id: str,
    *,
    id_fields: Sequence[str],
    name_fields: Sequence[str],
    external_id_fields: Sequence[str] = (),
    country_code_fields: Sequence[str] = (),
    country_fields: Sequence[str] = (),
    province_fields: Sequence[str] = (),
    city_fields: Sequence[str] = (),
    address_fields: Sequence[str] = (),
) -> str:
    """Resolve an existing Organization, using hybrid matching only as fallback."""
    raw_id = first_value(row, *id_fields)
    if clean_text(raw_id) is not None:
        exact_resolver = getattr(resolver, "resolve_exact", None)
        if exact_resolver is not None and (exact_id := exact_resolver(raw_id)) is not None:
            return organization_vid(exact_id)
        return organization_vid(raw_id)
    name = first_value(row, *name_fields)
    context = _alignment_context(
        spec,
        row,
        record_id,
        external_id_fields=external_id_fields,
        country_code_fields=country_code_fields,
        country_fields=country_fields,
        province_fields=province_fields,
        city_fields=city_fields,
        address_fields=address_fields,
    )
    return resolved_organization_vid(
        name,
        resolver,
        context=context,
    )


def extract_candidates(
    spec: RelationSpec,
    row: Mapping[str, Any],
    resolver: Any,
    ingest_batch: str,
    ingest_time: str,
) -> list[EdgeCandidate]:
    """Convert one source row without creating or guessing any vertex."""
    base_record_id = stable_record_id(spec.source_table, row, spec.source_record_fields)
    extractor = spec.extractor

    if extractor == "legal_representative":
        legal_name = first_value(row, "lerep", "legal_person")
        source = person_vid(
            "legal_representative",
            row.get("org_id"),
            legal_name,
        )
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_cn", "company_name"),
            external_id_fields=("external_id",),
            province_fields=("province",),
            city_fields=("city",),
            address_fields=("address", "company_address"),
        )
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time)
        return [
            _candidate(
                spec,
                source,
                target,
                base_record_id,
                props,
                source_tag="Person",
            )
        ]

    if extractor == "domestic_shareholder":
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_cn",),
            external_id_fields=("external_id",),
        )
        owner_type = (clean_text(row.get("owners_type")) or "").casefold()
        organization_types = {"机构", "企业", "公司", "organization", "company", "enterprise"}
        person_types = {"自然人", "个人", "person", "individual", "natural person"}
        owner_name = first_value(row, "owners_name", "inv_name")
        if clean_text(row.get("inv_org_id")) is not None or owner_type in organization_types:
            source = _organization_vid_from_row(
                spec,
                row,
                resolver,
                base_record_id,
                id_fields=("inv_org_id",),
                name_fields=("owners_name", "inv_name"),
            )
            source_tag = "Organization"
        elif owner_type in person_types:
            source = person_vid("shareholder", row.get("org_id"), owner_name)
            source_tag = "Person"
        else:
            raise RelationDataError("shareholder endpoint type is not explicit")
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"ownership_percentage": to_float(row.get("ownership_percentage"))},
        )
        return [
            _candidate(
                spec,
                source,
                target,
                base_record_id,
                props,
                source_tag=source_tag,
            )
        ]

    if extractor == "foreign_shareholder":
        context = _alignment_context(
            spec,
            row,
            base_record_id,
            country_code_fields=("owners_country_code",),
            country_fields=("owners_country",),
        )
        owner_org_id = resolver.resolve(row.get("owners_name"), context)
        if owner_org_id is None:
            raise RelationDataError(
                "foreign shareholder type is unknown and is not an exact unique Organization"
            )
        source = organization_vid(owner_org_id)
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_en", "name_cn"),
        )
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"ownership_percentage": to_float(row.get("ownership_percentage"))},
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "executive":
        source = _person_vid_for_row(spec, row, "executive", "executives_name")
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_cn", "name_en"),
            external_id_fields=("external_id",),
        )
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"position": clean_text(row.get("executives_position"))},
        )
        return [
            _candidate(
                spec,
                source,
                target,
                base_record_id,
                props,
                source_tag="Person",
            )
        ]

    if extractor == "beneficial_owner":
        source = _person_vid_for_row(spec, row, "beneficial_owner", "bo_name")
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_en", "name_cn"),
        )
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {
                "direct_percent": to_float(row.get("direct_percent")),
                "indirect_percent": to_float(row.get("indirect_percent")),
                "total_percent": to_float(row.get("total_percent")),
            },
        )
        return [
            _candidate(
                spec,
                source,
                target,
                base_record_id,
                props,
                source_tag="Person",
            )
        ]

    if extractor == "actual_controller":
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_en", "name_cn"),
        )
        entity_type = (clean_text(row.get("entity_type")) or "").casefold()
        organization_types = {"organization", "company", "enterprise", "机构", "企业", "公司"}
        person_types = {"person", "individual", "natural person", "自然人", "个人"}
        if entity_type in organization_types:
            source = _organization_vid_from_row(
                spec,
                row,
                resolver,
                base_record_id,
                id_fields=("entity_eid",),
                name_fields=("entity_name",),
                external_id_fields=("entity_eid",),
                country_code_fields=("entity_country_code", "country_code"),
                country_fields=("entity_country", "country"),
            )
            source_tag = "Organization"
        elif entity_type in person_types:
            source = _person_vid_for_row(
                spec,
                row,
                "actual_controller",
                "entity_name",
            )
            source_tag = "Person"
        else:
            context = _alignment_context(
                spec,
                row,
                base_record_id,
                external_id_fields=("entity_eid",),
                country_code_fields=("entity_country_code", "country_code"),
                country_fields=("entity_country", "country"),
            )
            exact_id = resolver.resolve(row.get("entity_name"), context)
            if exact_id is None:
                raise RelationDataError(
                    "actual controller entity_type is unknown and name is not an exact Organization"
                )
            source = organization_vid(exact_id)
            source_tag = "Organization"
        if source == target:
            raise RelationDataError("actual controller resolves to target Organization itself")
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {
                "direct_pct": to_float(first_value(row, "direct_pct_num", "direct_pct")),
                "total_pct": to_float(first_value(row, "total_pct_num", "total_pct")),
            },
        )
        return [
            _candidate(
                spec,
                source,
                target,
                base_record_id,
                props,
                source_tag=source_tag,
            )
        ]

    if extractor == "investment":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_cn",),
            external_id_fields=("external_id",),
        )
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("inv_org_id",),
            name_fields=("inv_name",),
            external_id_fields=("inv_external_id",),
        )
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
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("acquiring_org_id",),
            name_fields=("acquiring_name",),
            external_id_fields=("acquiring_external_id",),
        )
        target = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("acquired_org_id",),
            name_fields=("acquired_name",),
            external_id_fields=("acquired_external_id",),
        )
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
        parent = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_en", "name_cn"),
        )
        target_id = clean_text(row.get("affiliate")) or clean_text(row.get("affiliates_company_id"))
        if target_id is None:
            target_id = resolver.resolve(
                row.get("affiliates_name"),
                _alignment_context(
                    spec,
                    row,
                    base_record_id,
                    external_id_fields=("affiliates_company_id",),
                    country_code_fields=("affiliates_country_code",),
                    country_fields=("affiliates_country",),
                ),
            )
        if target_id is None:
            raise RelationDataError(
                "subsidiary target has no stable or exact unique Organization id"
            )
        subsidiary = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("affiliate", "affiliates_company_id"),
            name_fields=("affiliates_name",),
            external_id_fields=("affiliates_company_id",),
            country_code_fields=("affiliates_country_code",),
            country_fields=("affiliates_country",),
        )
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time)
        return [_candidate(spec, subsidiary, parent, base_record_id, props)]

    if extractor == "project":
        target = project_vid(row.get("id"))
        result: list[EdgeCandidate] = []
        for index, item in enumerate(parse_entity_list(row.get("participating_institution"))):
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

    if extractor == "project_funder":
        source = project_vid(row.get("id"))
        result: list[EdgeCandidate] = []
        for index, item in enumerate(parse_entity_list(row.get("funded_institution"))):
            name = item.get("name") if isinstance(item, dict) else item
            target_id = None
            if isinstance(item, dict):
                target_id = clean_text(
                    item.get("org_id") or item.get("organization_id") or item.get("institution_id")
                )
            target_id = target_id or resolver.resolve(name)
            if target_id is None:
                continue
            record_id = f"{base_record_id}|funder|{index}|{clean_text(name) or target_id}"
            props = _edge_props(
                spec,
                row,
                record_id,
                ingest_batch,
                ingest_time,
                {
                    "funded_amount": to_float(row.get("funded_amount")),
                    "fund_category": clean_text(row.get("fund_category")),
                },
            )
            result.append(
                _candidate(
                    spec,
                    source,
                    organization_vid(target_id),
                    record_id,
                    props,
                    source_tag="Project",
                )
            )
        if not result:
            raise RelationDataError("project has no funder with a stable or exact unique org id")
        return result

    if extractor == "news":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_cn",),
            external_id_fields=("external_id",),
        )
        target = news_vid(f"{spec.source_table}_{base_record_id}")
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time)
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "event":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=(
                "name_cn",
                "company_name",
                "taxpayer_name",
                "exec_person_name",
            ),
            external_id_fields=("external_id", "credit_no"),
            province_fields=("province",),
            city_fields=("city",),
            address_fields=("address", "reg_address"),
        )
        target = event_vid(spec.source_table, base_record_id)
        role = clean_text(row.get("case_role") or row.get("exec_person_type")) or "subject"
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time, {"role": role})
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "bankruptcy_party":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("related_person_name", "name_cn"),
            external_id_fields=("external_id",),
        )
        case_no = clean_text(row.get("case_no"))
        if case_no is None:
            raise RelationDataError("bankruptcy party has no case_no")
        target = event_vid("dwd_org_bankruptcy_public_cases", case_no)
        role = clean_text(row.get("party_role_type")) or "bankruptcy_party"
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time, {"role": role})
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "bankruptcy_admin":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("admin_org_id",),
            name_fields=("admin_org",),
        )
        case_no = clean_text(row.get("case_no"))
        if case_no is None:
            raise RelationDataError("bankruptcy case has no case_no")
        target = event_vid(spec.source_table, case_no)
        props = _edge_props(
            spec,
            row,
            base_record_id,
            ingest_batch,
            ingest_time,
            {"role": "bankruptcy_administrator"},
        )
        return [_candidate(spec, source, target, base_record_id, props)]

    if extractor == "bid_party":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id", "company_id"),
            name_fields=("name_cn", "company_name"),
            external_id_fields=("external_id", "credit_no"),
        )
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

    if extractor == "organization_product":
        source = _organization_vid_from_row(
            spec,
            row,
            resolver,
            base_record_id,
            id_fields=("org_id",),
            name_fields=("name_cn", "name_en"),
            external_id_fields=("external_id",),
        )
        name = first_value(row, "main_prod", "main_products")
        target = product_vid(name)
        props = _edge_props(spec, row, base_record_id, ingest_batch, ingest_time)
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
                numeric=name in spec.numeric_properties or name == "confidence",
            )
            for name in spec.edge_properties
        )
        rows.append(
            f"{ngql_literal(item.source_vid)}->{ngql_literal(item.target_vid)}"
            f"@{item.rank}:({values})"
        )
    return f"INSERT EDGE {ngql_identifier(spec.edge_type)} ({props}) VALUES " + ",".join(rows) + ";"


def existing_edge_identities(
    graph: TRSGraphClient,
    spec: RelationSpec,
    candidates: Sequence[EdgeCandidate],
) -> set[tuple[str, str, str, int]]:
    """Return exact existing edge identities so shared edges are never overwritten."""
    if not candidates:
        return set()
    source_values = ",".join(
        ngql_literal(value) for value in sorted({item.source_vid for item in candidates})
    )
    target_values = ",".join(
        ngql_literal(value) for value in sorted({item.target_vid for item in candidates})
    )
    query = (
        f"MATCH (s)-[e:{ngql_identifier(spec.edge_type)}]->(t) "
        f"WHERE id(s) IN [{source_values}] AND id(t) IN [{target_values}] "
        "RETURN id(s) AS source_vid,id(t) AS target_vid,rank(e) AS edge_rank;"
    )
    identities: set[tuple[str, str, str, int]] = set()
    for record in graph.execute_read(query).records:
        source_vid = clean_text(record.get("source_vid"))
        target_vid = clean_text(record.get("target_vid"))
        raw_rank = record.get("edge_rank")
        try:
            rank = (
                raw_rank
                if isinstance(raw_rank, int) and not isinstance(raw_rank, bool)
                else int(clean_text(raw_rank) or "")
            )
        except ValueError:
            rank = None
        if source_vid is not None and target_vid is not None and rank is not None:
            identities.add((spec.edge_type, source_vid, target_vid, rank))
    return identities


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
    for source_tag in spec.source_tags:
        if source_tag not in labels:
            return False, f"{source_tag} tag is missing"
    if spec.target_tag not in labels:
        return False, f"{spec.target_tag} tag is missing"
    if spec.edge_type not in edge_types:
        return False, f"{spec.edge_type} edge is missing"
    return True, ""


def _build_organization_resolver(
    session: Session,
    *,
    alignment_mode: str,
    alignment_state_dir: str | None,
    alignment_threshold: float,
    alignment_margin: float,
    alignment_top_k: int,
    alignment_dense_dimension: int,
    alignment_audit_path: str | None,
) -> tuple[Any, OrganizationMilvusStore | None]:
    exact = ExactOrganizationResolver.load(session)
    if alignment_mode == "exact":
        return exact, None
    if alignment_mode != "hybrid":
        raise ValueError(f"unsupported alignment mode: {alignment_mode}")

    store = OrganizationMilvusStore()
    if not store.has_collection("Organization"):
        store.close()
        raise RuntimeError(
            "Organization Milvus index is missing; run "
            "`python -m script.organization_milvus_index --entity Organization --write` first"
        )
    state_dir = Path(
        alignment_state_dir or os.environ.get("ORG_MILVUS_STATE_DIR") or DEFAULT_ALIGNMENT_STATE_DIR
    ).resolve()
    model_path = state_dir / f"{store.collection_name('Organization')}.bm25.json"
    if not model_path.exists():
        store.close()
        raise RuntimeError(f"Organization BM25 model state is missing: {model_path}")
    matcher = OrganizationHybridMatcher(
        store,
        BM25SparseEncoder.load(model_path),
        HashingDenseEncoder(alignment_dense_dimension),
        threshold=alignment_threshold,
        margin=alignment_margin,
        top_k=alignment_top_k,
    )
    resolver = HybridOrganizationResolver(
        exact,
        matcher,
        AlignmentAuditWriter(Path(alignment_audit_path) if alignment_audit_path else None),
    )
    return resolver, store


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
    source_found: set[tuple[str, str]] = set()
    target_found: set[tuple[str, str]] = set()
    for tag in sorted({item.source_tag for item in unique}):
        source_found.update(
            (tag, vid)
            for vid in existing_vids(
                graph,
                tag,
                (item.source_vid for item in unique if item.source_tag == tag),
                batch_size=batch_size,
            )
        )
    for tag in sorted({item.target_tag for item in unique}):
        target_found.update(
            (tag, vid)
            for vid in existing_vids(
                graph,
                tag,
                (item.target_vid for item in unique if item.target_tag == tag),
                batch_size=batch_size,
            )
        )
    ready: list[EdgeCandidate] = []
    for item in unique:
        missing_source = (item.source_tag, item.source_vid) not in source_found
        missing_target = (item.target_tag, item.target_vid) not in target_found
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

    existing = existing_edge_identities(graph, spec, ready)
    stats.existing += sum(item.identity in existing for item in ready)
    stats.valid += len(ready)

    def write_edges(write_batch: Sequence[EdgeCandidate]) -> None:
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
            return
        try:
            graph.execute_write(query)
            stats.updated += sum(item.identity in existing for item in write_batch)
            stats.written += sum(item.identity not in existing for item in write_batch)
        except Exception:
            if len(write_batch) > 1:
                midpoint = len(write_batch) // 2
                logger.warning(
                    "split failed edge batch edge=%s table=%s size=%s query_chars=%s",
                    spec.edge_type,
                    spec.source_table,
                    len(write_batch),
                    len(query),
                )
                write_edges(write_batch[:midpoint])
                write_edges(write_batch[midpoint:])
                return
            stats.failed += 1
            logger.exception(
                "graph write failed edge=%s table=%s rows=%d ngql_prefix=%s",
                spec.edge_type,
                spec.source_table,
                len(write_batch),
                query[:500],
            )

    for write_batch in chunks(ready, batch_size):
        write_edges(write_batch)


def run_etl(
    *,
    relation: str = "all",
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = True,
    max_records: int | None = None,
    domestic_only: bool = False,
    foreign_only: bool = False,
    ingest_batch: str | None = None,
    alignment_mode: str = "exact",
    alignment_state_dir: str | None = None,
    alignment_threshold: float = 0.88,
    alignment_margin: float = 0.08,
    alignment_top_k: int = 20,
    alignment_dense_dimension: int = DEFAULT_ALIGNMENT_DENSE_DIMENSION,
    alignment_audit_path: str | None = None,
    resolver: Any | None = None,
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
    if alignment_mode not in {"exact", "hybrid"}:
        raise ValueError("alignment_mode must be exact or hybrid")
    if not 0.0 <= alignment_threshold <= 1.0:
        raise ValueError("alignment_threshold must be between 0 and 1")
    if not 0.0 <= alignment_margin <= 1.0:
        raise ValueError("alignment_margin must be between 0 and 1")
    if alignment_top_k <= 0:
        raise ValueError("alignment_top_k must be positive")
    if alignment_dense_dimension <= 0:
        raise ValueError("alignment_dense_dimension must be positive")
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

    milvus_store: OrganizationMilvusStore | None = None
    try:
        validate_source_schema(session, specs)
        if resolver is None:
            resolver, milvus_store = _build_organization_resolver(
                session,
                alignment_mode=alignment_mode,
                alignment_state_dir=alignment_state_dir,
                alignment_threshold=alignment_threshold,
                alignment_margin=alignment_margin,
                alignment_top_k=alignment_top_k,
                alignment_dense_dimension=alignment_dense_dimension,
                alignment_audit_path=alignment_audit_path,
            )
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
            for row in iter_source_rows(
                session,
                spec,
                max_records=max_records,
            ):
                stats.queried += 1
                if is_virtual_source_row(row):
                    stats.skipped += 1
                    logger.info("skip synthetic relation source row table=%s", spec.source_table)
                    continue
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
                    if any(
                        marker in str(exc)
                        for marker in ("exact unique", "stable", "high-confidence")
                    ):
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
        if milvus_store is not None:
            milvus_store.close()
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
    parser.add_argument("--space", default=DEFAULT_SPACE)
    parser.add_argument("--ingest-batch")
    parser.add_argument(
        "--alignment-mode",
        choices=("exact", "hybrid"),
        default="exact",
        help="use conservative Milvus hybrid alignment only when explicitly selected",
    )
    parser.add_argument("--alignment-state-dir")
    parser.add_argument("--alignment-threshold", type=float, default=0.88)
    parser.add_argument("--alignment-margin", type=float, default=0.08)
    parser.add_argument("--alignment-top-k", type=int, default=20)
    parser.add_argument(
        "--alignment-dense-dimension",
        type=int,
        default=DEFAULT_ALIGNMENT_DENSE_DIMENSION,
    )
    parser.add_argument(
        "--alignment-audit",
        help="JSONL path for matched, review and rejected alignment decisions",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    os.environ["TRS_GRAPH_SPACE"] = args.space
    now = datetime.now(UTC)
    ingest_batch = args.ingest_batch or f"ORG_REL_{now.strftime('%Y%m%dT%H%M%SZ')}"
    alignment_audit = args.alignment_audit
    if args.alignment_mode == "hybrid" and not alignment_audit:
        alignment_audit = f"output/organization_alignment_{ingest_batch}.jsonl"
    with exclusive_etl_lock("organization_relation_etl", ingest_batch):
        results = run_etl(
            relation=args.relation,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            max_records=args.max_records,
            domestic_only=args.domestic_only,
            foreign_only=args.foreign_only,
            ingest_batch=ingest_batch,
            alignment_mode=args.alignment_mode,
            alignment_state_dir=args.alignment_state_dir,
            alignment_threshold=args.alignment_threshold,
            alignment_margin=args.alignment_margin,
            alignment_top_k=args.alignment_top_k,
            alignment_dense_dimension=args.alignment_dense_dimension,
            alignment_audit_path=alignment_audit,
        )
    summary = {table: asdict(stats) for table, stats in results.items()}
    logger.info("organization relation ETL summary=%s", compact_json(summary))
    return 1 if any(item.failed for item in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
