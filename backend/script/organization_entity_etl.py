"""Load organization-domain business vertices from gkx_element into TRSGraph ``dev``.

This is the only organization-domain vertex loader.  It creates real
Organization, Person, News, Event, Project, Product and DataSource vertices,
but never creates graph edges.  Existing non-empty canonical properties are
preserved; source payloads are merged into ``extra_json`` for auditability.
Organization relations are owned exclusively by ``script.organization_relation_etl``.

Examples:

    python -m script.organization_entity_etl load --full --dry-run
    python -m script.organization_entity_etl load --table dwd_org_base_info --full --write
    python -m script.organization_entity_etl init-schema
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from infra.gkx_element import gkx_element_read_session
from infra.graph_db import TRSGraphClient, get_trs_graph_client
from script.etl_watermark import Watermark
from script.organization_etl_common import (
    DEFAULT_SPACE,
    DOMAIN_TABLE_SPECS,
    RELATION_SPECS,
    SCHEMA_PATH,
    DomainTableSpec,
    RelationDataError,
    bounded_json,
    chunks,
    clean_text,
    datasource_vid,
    event_vid,
    exclusive_etl_lock,
    is_virtual_source_row,
    news_vid,
    ngql_identifier,
    ngql_literal,
    node_provenance,
    organization_vid,
    person_vid,
    product_vid,
    project_vid,
    stable_record_id,
    to_float,
    to_int,
)

logger = logging.getLogger("script.organization_entity_etl")

DEFAULT_BATCH_SIZE = 100

TAG_PROPERTIES: dict[str, tuple[str, ...]] = {
    "Organization": (
        "org_id",
        "organization_id",
        "confidence",
        "name_cn",
        "name_en",
        "external_id",
        "province",
        "city",
        "area",
        "country_code",
        "country",
        "address",
        "postal_code",
        "phone",
        "email",
        "legal_rep",
        "org_type",
        "org_size",
        "founded_year",
        "listing_status",
        "listed_date",
        "registered_capital",
        "capital_currency",
        "industry_class",
        "stock_code",
        "stock_noun",
        "stock_type",
        "org_kind",
        "description",
        "main_products",
        "extra_json",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
    ),
    "Person": (
        "name_cn",
        "name_en",
        "person_kind",
        "country_code",
        "country",
        "birth_date",
        "gender",
        "biography",
        "organization_id",
        "confidence",
        "extra_json",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
    ),
    "News": (
        "title",
        "content",
        "release_date",
        "original_url",
        "organization_id",
        "confidence",
        "extra_json",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
    ),
    "Event": (
        "event_type",
        "raw_id",
        "title",
        "content",
        "case_no",
        "case_cause",
        "occur_date",
        "amount",
        "currency",
        "organization_id",
        "confidence",
        "extra_json",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
    ),
    "Project": (
        "project_number",
        "title",
        "project_source",
        "project_level",
        "funded_amount",
        "discipline",
        "discipline_code",
        "fund_category",
        "funded_region",
        "approval_year",
        "approval_time",
        "research_period",
        "abstract",
        "final_report_abstract",
        "project_page_url",
        "extra_json",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
    ),
    "Product": (
        "name",
        "category",
        "description",
        "organization_id",
        "confidence",
        "extra_json",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
    ),
    "DataSource": ("source_table", "table_cn_name", "tier", "library"),
    "organization_base": (
        "organization_id",
        "confidence",
        "source_system",
        "source_table",
        "source_record_id",
        "source_url",
        "ingest_batch",
        "ingest_time",
        "source_update_time",
        "extra_json",
    ),
}
TAG_NUMERIC_PROPERTIES: dict[str, frozenset[str]] = {
    "Organization": frozenset({"founded_year", "registered_capital", "confidence"}),
    "Person": frozenset({"confidence"}),
    "News": frozenset({"confidence"}),
    "Event": frozenset({"amount", "confidence"}),
    "Project": frozenset({"funded_amount"}),
    "Product": frozenset({"confidence"}),
    "organization_base": frozenset({"confidence"}),
}

ENTITY_TABLE_SPECS: tuple[DomainTableSpec, ...] = tuple(
    spec for spec in DOMAIN_TABLE_SPECS if spec.entity_tag is not None
)
ENTITY_TABLE_BY_NAME = {spec.name: spec for spec in ENTITY_TABLE_SPECS}

TABLE_CN_NAMES: dict[str, str] = {spec.name: spec.cn_name for spec in DOMAIN_TABLE_SPECS}
TABLE_CN_NAMES.update(
    {
        "dwd_org_shareholder_info": "国内机构股东信息",
        "dwd_org_executive_info": "国内机构高管信息",
        "dwd_forg_shareholder_info": "海外机构股东信息",
        "dwd_forg_executive_info": "海外机构高管信息",
        "dwd_forg_beneficiary_info": "海外机构受益人",
        "dwd_forg_act_contro_info": "海外机构实际控制人",
        "dwd_org_invest_info": "投资事件",
        "dwd_org_merger_acquisition_info": "并购事件",
        "dwd_forg_subsidiary_info": "海外机构子公司",
        "dwd_org_important_news_info": "重点资讯",
        "dwd_org_annual_financial_info": "年报财务信息",
        "dwd_org_stock_finance_info": "上市企业财务信息",
        "dwd_forg_stock_fin_info": "海外上市企业财务信息",
        "dwd_org_changerecord_info": "工商变更",
        "dwd_org_financing_info": "融资事件",
        "dwd_org_recruit_info": "招聘信息",
        "dwd_org_company_abnormal": "经营异常",
        "dwd_org_company_punish": "行政处罚",
        "dwd_org_company_illegal": "严重违法",
        "dwd_org_risk_tax_punish": "税收违法",
        "dwd_org_opt_judicial_case": "司法案件",
        "dwd_org_risk_shixin": "失信被执行人",
        "dwd_org_risk_zhixing": "被执行人",
        "dwd_org_bankruptcy_public_cases_list": "破产案件当事人",
        "dwd_org_bankruptcy_public_cases": "破产案件",
        "dwd_bid_base_out": "招投标公告",
        "dwd_bid_win_candidate_out": "中标候选人",
        "dwd_bid_purchase_agency_out": "采购代理",
        "dwd_bid_target_item_out": "招投标标的物",
    }
)
assert len(TABLE_CN_NAMES) == 39


@dataclass(frozen=True)
class VertexRecord:
    tag: str
    vid: str
    properties: dict[str, Any]


@dataclass
class EntityStats:
    queried: int = 0
    valid: int = 0
    written: int = 0
    updated: int = 0
    skipped: int = 0
    existing: int = 0
    invalid: int = 0
    failed: int = 0
    batches: int = 0
    examples: list[str] = field(default_factory=list)


def first_value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if clean_text(value) is not None:
            return value
    return None


def organization_kind(table: str) -> str:
    return {
        "dwd_org_heis_info": "domestic_university",
        "dwd_research_institute_base_info": "domestic_research_institute",
        "dwd_special_hongkong_company": "hong_kong_company",
        "dwd_special_taiwan_company": "taiwan_company",
        "dwd_special_aomen_company": "macao_company",
        "dwd_forg_base_info": "foreign_organization",
        "dwd_forg_product_info": "foreign_organization",
    }.get(table, "domestic_organization")


def organization_properties(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    """Map one source row without inventing an organization identifier."""
    raw_org_id = first_value(row, "org_id", "company_id", "entity_eid")
    org_id = clean_text(raw_org_id)
    if org_id is None:
        raise RelationDataError("missing stable organization id")
    incorporation = first_value(row, "incorporation_year", "est_year", "incorporation_date")
    values: dict[str, Any] = {
        "org_id": org_id,
        "name_cn": clean_text(
            first_value(
                row,
                "name_cn",
                "org_loc_name",
                "company_name",
                "n_company_name",
                "traditional_name",
                "name_alias",
                "name_en",
            )
        ),
        "name_en": clean_text(first_value(row, "name_en", "en_name")),
        "external_id": clean_text(
            first_value(row, "external_id", "company_code", "school_code", "credit_no")
        ),
        "province": clean_text(first_value(row, "province", "project_region_province")),
        "city": clean_text(first_value(row, "city", "project_region_city")),
        "area": clean_text(first_value(row, "area", "project_region_district")),
        "country_code": clean_text(first_value(row, "country_code", "entity_country_code")),
        "country": clean_text(row.get("country")),
        "address": clean_text(first_value(row, "address", "company_address", "reg_address")),
        "postal_code": clean_text(row.get("postal_code")),
        "phone": clean_text(row.get("phone")),
        "email": clean_text(row.get("email")),
        "legal_rep": clean_text(first_value(row, "lerep", "legal_person", "legal_name")),
        "org_type": clean_text(
            first_value(row, "org_type", "univ_type", "company_type", "industry_type")
        ),
        "org_size": clean_text(first_value(row, "person_num", "employees_number")),
        "founded_year": to_int(incorporation),
        "listing_status": clean_text(first_value(row, "listing_status", "listed_status")),
        "listed_date": clean_text(first_value(row, "listing_date", "listed_date")),
        "registered_capital": to_float(
            first_value(row, "registered_capital_value", "capital_num", "capital")
        ),
        "capital_currency": clean_text(
            first_value(
                row,
                "capital_currency",
                "registered_capital_currency_code",
                "currency_code",
                "currency",
            )
        ),
        "industry_class": clean_text(
            first_value(row, "industry", "industry_class", "industry_l1_name")
        ),
        "stock_code": clean_text(row.get("stock_code")),
        "stock_noun": clean_text(row.get("stock_noun")),
        "stock_type": clean_text(row.get("stock_type")),
        "org_kind": organization_kind(spec.name),
        "description": clean_text(
            first_value(row, "description", "main_activities", "business_scope")
        ),
        "main_products": clean_text(first_value(row, "main_products", "main_prod")),
        "extra_json": bounded_json(dict(row)),
        **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
    }
    if spec.entity_kind == "organization_enrichment":
        # Enrichment rows update only fields they actually carry.  This prevents
        # a sparse product/stock row from replacing base attributes with NULL.
        return {name: value for name, value in values.items() if value is not None}
    return values


def person_record(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> VertexRecord | None:
    name = clean_text(first_value(row, "executives_name", "bo_name", "entity_name", "owners_name"))
    if name is None:
        raise RelationDataError("missing person name")
    if spec.entity_kind == "shareholder":
        owner_type = (clean_text(row.get("owners_type")) or "").casefold()
        organization_types = {"organization", "company", "enterprise", "机构", "企业", "公司"}
        person_types = {"person", "individual", "natural person", "自然人", "个人"}
        if clean_text(row.get("inv_org_id")) is not None or owner_type in organization_types:
            return None
        if owner_type not in person_types:
            raise RelationDataError("shareholder endpoint type does not identify a Person")
    if spec.entity_kind == "actual_controller":
        entity_type = (clean_text(row.get("entity_type")) or "").casefold()
        person_types = {"person", "individual", "natural person", "自然人", "个人"}
        organization_types = {"organization", "company", "enterprise", "机构", "企业", "公司"}
        if entity_type in organization_types:
            return None
        if entity_type not in person_types:
            raise RelationDataError("actual controller entity_type does not identify a Person")
    birth_date = clean_text(first_value(row, "dm_birthdate", "bo_birthdate", "birth_date"))
    country = clean_text(first_value(row, "dm_nationalities", "bo_country_code", "country_code"))
    target_identity = first_value(row, "org_id", "external_id")
    vid = person_vid(spec.entity_kind, target_identity, name, birth_date, country)
    properties = {
        "name_cn": name,
        "name_en": name if spec.scope == "foreign" else None,
        "person_kind": spec.entity_kind,
        "country_code": clean_text(first_value(row, "bo_country_code", "country_code")),
        "country": clean_text(first_value(row, "dm_nationalities", "country")),
        "birth_date": birth_date,
        "gender": clean_text(first_value(row, "bo_gender", "gender")),
        "biography": clean_text(row.get("dm_biography")),
        "extra_json": bounded_json(dict(row)),
        **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
    }
    return VertexRecord("Person", vid, properties)


def event_properties(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    title = first_value(
        row,
        "title",
        "project_name",
        "case_title",
        "job_title",
        "funding_round",
        "update_name",
        "abn_reason",
        "violation_type",
        "category",
        "case_type",
        "target_item_name",
        "bid_item_name",
    )
    content = first_value(
        row,
        "content",
        "project_content",
        "service_content",
        "job_description",
        "penalty_content",
        "violation_fact",
        "illegal_fact",
        "legal_obligation",
        "update_content",
        "dishonest_behavior",
        "exec_target",
    )
    occur_date = first_value(
        row,
        "publish_time",
        "public_date",
        "publish_date",
        "penalty_date",
        "procedure_date",
        "completion_date",
        "release_date",
        "update_date",
        "abn_date",
        "filing_date",
        "occur_period",
        "year",
    )
    amount = first_value(
        row,
        "amount",
        "funding_amount",
        "fine_amount",
        "exec_target",
        "total_amount",
        "project_budget_amount",
        "total_assets",
        "unit_price_amount",
    )
    return {
        "event_type": spec.entity_kind,
        "raw_id": record_id,
        "title": clean_text(title) or spec.cn_name,
        "content": clean_text(content) or bounded_json(dict(row)),
        "case_no": clean_text(
            first_value(row, "case_no", "reg_no", "decision_no", "project_number")
        ),
        "case_cause": clean_text(first_value(row, "case_cause", "case_type", "case_type_tag")),
        "occur_date": clean_text(occur_date),
        "amount": to_float(amount),
        "currency": clean_text(
            first_value(
                row,
                "currency",
                "currency_code",
                "funding_currency_code",
                "amount_unit",
                "total_amount_unit",
                "project_budget_amount_unit",
            )
        ),
        "extra_json": bounded_json(dict(row)),
        **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
    }


def project_properties(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    project_id = clean_text(row.get("id"))
    if project_id is None:
        raise RelationDataError("missing project id")
    return {
        "project_number": clean_text(row.get("project_number")),
        "title": clean_text(row.get("title")),
        "project_source": clean_text(row.get("project_source")),
        "project_level": clean_text(row.get("project_level")),
        "funded_amount": to_float(row.get("funded_amount")),
        "discipline": clean_text(row.get("discipline")),
        "discipline_code": clean_text(row.get("discipline_code")),
        "fund_category": clean_text(row.get("fund_category")),
        "funded_region": clean_text(row.get("funded_province")),
        # The shared dev ontology defines Project.approval_year as string.
        "approval_year": clean_text(row.get("approval_year")),
        "approval_time": clean_text(row.get("approval_time")),
        "research_period": clean_text(row.get("research_period")),
        "abstract": clean_text(row.get("abstract")),
        "final_report_abstract": clean_text(row.get("final_report_abstract")),
        "project_page_url": clean_text(row.get("project_page_url")),
        "extra_json": bounded_json(dict(row)),
        **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
    }


def product_record(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> VertexRecord | None:
    name = clean_text(first_value(row, "main_prod", "main_products", "tech_product"))
    if name is None:
        return None
    properties = {
        "name": name,
        "category": clean_text(first_value(row, "target_item_type", "industry_class")),
        "description": clean_text(first_value(row, "description", "main_activities")),
        "extra_json": bounded_json(dict(row)),
        **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
    }
    return VertexRecord("Product", product_vid(name), properties)


def vertices_from_row(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    ingest_batch: str,
    ingest_time: str,
) -> list[VertexRecord]:
    preferred = spec.raw_id_fields
    if spec.entity_tag == "Organization" and not preferred:
        preferred = ("org_id",)
    record_id = stable_record_id(spec.name, row, preferred)
    if spec.entity_tag == "Organization":
        properties = organization_properties(spec, row, record_id, ingest_batch, ingest_time)
        vid = organization_vid(properties["org_id"])
        records = [VertexRecord("Organization", vid, properties)]
        records.append(
            VertexRecord(
                "organization_base",
                vid,
                {
                    "organization_id": properties["organization_id"],
                    "confidence": properties["confidence"],
                    "source_system": properties["source_system"],
                    "source_table": properties["source_table"],
                    "source_record_id": properties["source_record_id"],
                    "source_url": properties.get("source_url"),
                    "ingest_batch": properties["ingest_batch"],
                    "ingest_time": properties["ingest_time"],
                    "source_update_time": properties.get("source_update_time"),
                    "extra_json": properties["extra_json"],
                },
            )
        )
        legal_name = clean_text(first_value(row, "lerep", "legal_person"))
        if legal_name is not None:
            legal_record_id = f"{record_id}|legal_representative|{legal_name}"
            records.append(
                VertexRecord(
                    "Person",
                    person_vid(
                        "legal_representative",
                        properties["org_id"],
                        legal_name,
                    ),
                    {
                        "name_cn": legal_name,
                        "person_kind": "legal_representative",
                        "extra_json": bounded_json(dict(row)),
                        **node_provenance(
                            spec.name,
                            legal_record_id,
                            row,
                            ingest_batch,
                            ingest_time,
                        ),
                    },
                )
            )
        product = product_record(spec, row, record_id, ingest_batch, ingest_time)
        if product is not None:
            records.append(product)
        return records
    if spec.entity_tag == "Person":
        person = person_record(spec, row, record_id, ingest_batch, ingest_time)
        return [] if person is None else [person]
    if spec.entity_tag == "News":
        properties = {
            "title": clean_text(row.get("news_title")),
            "content": clean_text(row.get("news_content")),
            "release_date": clean_text(row.get("news_date")),
            "original_url": clean_text(row.get("original_textlink")),
            "extra_json": bounded_json(dict(row)),
            **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
        }
        return [
            VertexRecord(
                "News",
                news_vid(f"{spec.name}_{record_id}"),
                properties,
            )
        ]
    if spec.entity_tag == "Event":
        return [
            VertexRecord(
                "Event",
                event_vid(spec.name, record_id),
                event_properties(spec, row, record_id, ingest_batch, ingest_time),
            )
        ]
    if spec.entity_tag == "Project":
        properties = project_properties(spec, row, record_id, ingest_batch, ingest_time)
        return [VertexRecord("Project", project_vid(row.get("id")), properties)]
    raise ValueError(f"unsupported entity tag: {spec.entity_tag}")


def vertex_from_row(
    spec: DomainTableSpec,
    row: Mapping[str, Any],
    ingest_batch: str,
    ingest_time: str,
) -> VertexRecord:
    """Compatibility helper for callers that expect exactly one vertex."""
    records = vertices_from_row(spec, row, ingest_batch, ingest_time)
    primary = [record for record in records if record.tag == spec.entity_tag]
    if len(primary) != 1:
        raise RelationDataError(f"source row produced {len(primary)} primary vertices")
    return primary[0]


def datasource_records() -> list[VertexRecord]:
    records: list[VertexRecord] = []
    for table, cn_name in sorted(TABLE_CN_NAMES.items()):
        library = (
            "国外机构要素库" if table.startswith(("dwd_forg_", "dwd_en_")) else "国内机构要素库"
        )
        records.append(
            VertexRecord(
                "DataSource",
                datasource_vid(table),
                {
                    "source_table": table,
                    "table_cn_name": cn_name,
                    "tier": "DWD",
                    "library": library,
                },
            )
        )
    return records


def render_vertex_insert(records: Sequence[VertexRecord]) -> str:
    if not records:
        raise ValueError("cannot render an empty vertex batch")
    tag = records[0].tag
    if any(record.tag != tag for record in records):
        raise ValueError("one INSERT VERTEX batch must contain one tag")
    allowed = TAG_PROPERTIES[tag]
    properties = tuple(name for name in allowed if name in records[0].properties)
    if any(
        tuple(name for name in allowed if name in record.properties) != properties
        for record in records
    ):
        raise ValueError("one INSERT VERTEX batch must have one property signature")
    numeric = TAG_NUMERIC_PROPERTIES.get(tag, frozenset())
    prop_clause = ",".join(ngql_identifier(name) for name in properties)
    values: list[str] = []
    for record in records:
        literals = [
            ngql_literal(record.properties.get(name), numeric=name in numeric)
            for name in properties
        ]
        values.append(f"{ngql_literal(record.vid)}:({','.join(literals)})")
    return f"INSERT VERTEX {ngql_identifier(tag)} ({prop_clause}) VALUES " + ",".join(values) + ";"


def source_columns(session: Session, table: str) -> set[str]:
    query = text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table"
    )
    return {str(row[0]) for row in session.execute(query, {"table": table})}


def iter_source_rows(
    session: Session,
    spec: DomainTableSpec,
    *,
    max_records: int | None,
    since: str | None = None,
) -> Iterator[dict[str, Any]]:
    columns = source_columns(session, spec.name)
    if not columns:
        raise RuntimeError(f"source table does not exist: {spec.name}")
    query = f"SELECT * FROM `{spec.name}`"
    params: dict[str, Any] = {}
    # 增量:表有 updated_time/update_time 列时按水位过滤;无则退化全量(安全)
    if since:
        ts_col = next((c for c in ("updated_time", "update_time") if c in columns), None)
        if ts_col:
            query += f" WHERE `{ts_col}` > :since"
            params["since"] = since
    query += " ORDER BY 1"
    if max_records is not None:
        query += " LIMIT :max_records"
        params["max_records"] = max_records
    statement = text(query)
    for row in session.execute(statement, params).mappings():
        yield dict(row)


def split_schema_statements(source: str) -> list[str]:
    lines = [line for line in source.splitlines() if not line.lstrip().startswith("--")]
    return [
        statement.strip() + ";" for statement in "\n".join(lines).split(";") if statement.strip()
    ]


def schema_fields(graph: TRSGraphClient, kind: str, name: str) -> set[str]:
    result = graph.execute_read(f"DESCRIBE {kind} {ngql_identifier(name)};")
    fields: set[str] = set()
    for record in result.records:
        for key in ("Field", "field", "Property", "property"):
            value = clean_text(record.get(key))
            if value is not None:
                fields.add(value)
                break
    return fields


def reconcile_existing_schema(graph: TRSGraphClient) -> None:
    """Add properties that CREATE IF NOT EXISTS cannot add to an existing schema."""
    additions: list[tuple[str, str, str, str]] = []
    additions.extend(
        (
            ("TAG", "Organization", "organization_base", "string NULL"),
            ("TAG", "Person", "organization_base", "string NULL"),
            ("TAG", "Project", "extra_json", "string NULL"),
            ("EDGE", "PARTICIPATES_IN", "extra_json", "string NULL"),
            ("EDGE", "FUNDED_BY", "extra_json", "string NULL"),
        )
    )
    for tag in ("Organization", "Person", "News", "Event", "Product"):
        additions.extend(
            (
                ("TAG", tag, "organization_id", "string NULL"),
                ("TAG", tag, "confidence", "double NULL"),
            )
        )
    for edge_type in sorted({spec.edge_type for spec in RELATION_SPECS}):
        additions.extend(
            (
                ("EDGE", edge_type, "organization_id", "string NULL"),
                ("EDGE", edge_type, "confidence", "double NULL"),
            )
        )
    for kind, name, field_name, field_type in additions:
        if field_name in schema_fields(graph, kind, name):
            continue
        statement = (
            f"ALTER {kind} {ngql_identifier(name)} "
            f"ADD ({ngql_identifier(field_name)} {field_type});"
        )
        graph.execute_write(statement)


def initialize_schema(graph: TRSGraphClient | None = None) -> None:
    client = graph or get_trs_graph_client()
    statements = split_schema_statements(SCHEMA_PATH.read_text(encoding="utf-8"))
    owned_tags = {
        "Organization",
        "organization_base",
        "Person",
        "News",
        "Event",
        "Product",
        "DataSource",
    }
    owned_edges = {spec.edge_type for spec in RELATION_SPECS}
    schema_prefixes = tuple(
        [f"CREATE TAG IF NOT EXISTS `{name}`" for name in owned_tags]
        + [f"CREATE EDGE IF NOT EXISTS `{name}`" for name in owned_edges]
    )
    schema_statements = [
        statement for statement in statements if statement.startswith(schema_prefixes)
    ]
    index_statements = [
        statement
        for statement in statements
        if statement.upper().startswith(("CREATE TAG INDEX", "CREATE EDGE INDEX"))
        and any(f" ON `{name}`" in statement for name in owned_tags | owned_edges)
    ]
    for statement in schema_statements:
        client.execute_write(statement)
    # Existing dev tags/edges need ALTER before indexes can reference new fields.
    reconcile_existing_schema(client)
    for statement in index_statements:
        client.execute_write(statement)


def existing_vids(
    graph: TRSGraphClient,
    tag: str,
    vids: Sequence[str],
) -> set[str]:
    """Return existing VIDs so entity writes never overwrite shared vertices."""
    if not vids:
        return set()
    values = ",".join(ngql_literal(vid) for vid in sorted(set(vids)))
    query = f"MATCH (v:{ngql_identifier(tag)}) WHERE id(v) IN [{values}] RETURN id(v) AS vid;"
    return {
        vid
        for record in graph.execute_read(query).records
        if (vid := clean_text(record.get("vid"))) is not None
    }


def existing_vertex_properties(
    graph: TRSGraphClient,
    tag: str,
    vids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    if not vids:
        return {}
    values = ",".join(ngql_literal(vid) for vid in sorted(set(vids)))
    query = (
        f"MATCH (v:{ngql_identifier(tag)}) WHERE id(v) IN [{values}] "
        "RETURN id(v) AS vid,properties(v) AS props;"
    )
    result: dict[str, dict[str, Any]] = {}
    for record in graph.execute_read(query).records:
        vid = clean_text(record.get("vid"))
        props = record.get("props")
        if vid is not None:
            result[vid] = dict(props) if isinstance(props, Mapping) else {}
    return result


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raw = clean_text(value)
    if raw is None:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"legacy_text": raw}
    return dict(parsed) if isinstance(parsed, Mapping) else {"legacy_value": parsed}


def merge_existing_properties(
    existing: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve existing canonical values and merge every source row into extra_json."""
    updates: dict[str, Any] = {}
    for name, value in incoming.items():
        if name == "extra_json" or value is None:
            continue
        current = existing.get(name)
        if name == "confidence":
            try:
                if current is None or float(value) > float(current):
                    updates[name] = value
            except (TypeError, ValueError):
                updates[name] = value
            continue
        if current is None or (isinstance(current, str) and not current.strip()):
            updates[name] = value

    incoming_payload = _json_object(incoming.get("extra_json"))
    if incoming_payload:
        existing_payload = _json_object(existing.get("extra_json"))
        if "source_records" in existing_payload and isinstance(
            existing_payload["source_records"], Mapping
        ):
            source_records = dict(existing_payload["source_records"])
            envelope = {
                key: value for key, value in existing_payload.items() if key != "source_records"
            }
        else:
            source_records = {}
            envelope = {}
            # A previous bounded audit summary is superseded once the complete
            # source row can be stored under the larger extra_json limit.
            if existing_payload and existing_payload.get("truncated") is not True:
                envelope["existing_payload"] = existing_payload
        source_key = ":".join(
            (
                clean_text(incoming.get("source_table")) or "unknown_table",
                clean_text(incoming.get("source_record_id")) or "unknown_record",
            )
        )
        source_records[source_key] = incoming_payload
        envelope["source_records"] = source_records
        merged_extra = bounded_json(envelope)
        if merged_extra != clean_text(existing.get("extra_json")):
            updates["extra_json"] = merged_extra
    return updates


def _write_vertex_batches(
    records: Sequence[VertexRecord],
    *,
    graph: TRSGraphClient | None,
    batch_size: int,
    dry_run: bool,
    stats: EntityStats,
) -> None:
    def write_group(records_to_write: Sequence[VertexRecord], counter: str) -> None:
        if not records_to_write:
            return
        statement = render_vertex_insert(records_to_write)
        if len(stats.examples) < 3:
            stats.examples.append(statement[:1_000])
        try:
            if graph is None:
                raise RuntimeError("graph client is required in write mode")
            graph.execute_write(statement)
            setattr(stats, counter, getattr(stats, counter) + len(records_to_write))
        except Exception:
            if len(records_to_write) > 1:
                midpoint = len(records_to_write) // 2
                logger.warning(
                    "split failed vertex batch tag=%s size=%s statement_chars=%s",
                    records_to_write[0].tag,
                    len(records_to_write),
                    len(statement),
                )
                write_group(records_to_write[:midpoint], counter)
                write_group(records_to_write[midpoint:], counter)
                return
            stats.failed += 1
            logger.exception(
                "organization vertex write failed tag=%s vid=%s statement=%s",
                records_to_write[0].tag,
                records_to_write[0].vid,
                statement[:500],
            )

    grouped: dict[tuple[str, tuple[str, ...]], list[VertexRecord]] = defaultdict(list)
    for record in records:
        allowed = TAG_PROPERTIES[record.tag]
        signature = tuple(name for name in allowed if name in record.properties)
        grouped[(record.tag, signature)].append(record)
    for group in grouped.values():
        for batch in chunks(group, batch_size):
            stats.batches += 1
            if dry_run:
                statement = render_vertex_insert(batch)
                if len(stats.examples) < 3:
                    stats.examples.append(statement[:1_000])
                continue
            if graph is None:
                raise RuntimeError("graph client is required in write mode")
            existing = existing_vertex_properties(
                graph,
                batch[0].tag,
                [record.vid for record in batch],
            )
            existing_records = [record for record in batch if record.vid in existing]
            stats.existing += len(existing_records)
            pending = [record for record in batch if record.vid not in existing]
            updates: list[VertexRecord] = []
            for record in batch:
                if record.vid not in existing:
                    continue
                current = existing[record.vid]
                changes = merge_existing_properties(current, record.properties)
                if not changes:
                    continue
                # Nebula INSERT VERTEX replaces the complete tag value. Include
                # every existing owned property so sparse enrichment updates do
                # not reset confidence, provenance, or canonical fields to NULL.
                complete = {
                    name: current[name]
                    for name in TAG_PROPERTIES[record.tag]
                    if current.get(name) is not None
                }
                complete.update(changes)
                updates.append(VertexRecord(record.tag, record.vid, complete))
            stats.skipped += len(existing_records) - len(updates)

            for records_to_write, counter in ((pending, "written"), (updates, "updated")):
                if not records_to_write:
                    continue
                update_groups: dict[tuple[str, ...], list[VertexRecord]] = defaultdict(list)
                for record in records_to_write:
                    signature = tuple(
                        name for name in TAG_PROPERTIES[record.tag] if name in record.properties
                    )
                    update_groups[signature].append(record)
                for update_group in update_groups.values():
                    write_group(update_group, counter)


def run_etl(
    *,
    table: str = "all",
    full: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_records: int | None = None,
    dry_run: bool = True,
    domestic_only: bool = False,
    foreign_only: bool = False,
    ingest_batch: str | None = None,
    graph: TRSGraphClient | None = None,
    session: Session | None = None,
    mode: str = "full",
) -> dict[str, EntityStats]:
    """Load only Organization and DataSource vertices; never create an edge."""
    if domestic_only and foreign_only:
        raise ValueError("domestic_only and foreign_only are mutually exclusive")
    if not full:
        raise ValueError("--full must be selected for entity loading")
    if table != "all" and table not in ENTITY_TABLE_BY_NAME:
        raise ValueError(f"unknown entity source table: {table}")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if max_records is not None and max_records <= 0:
        raise ValueError("max_records must be positive")
    now = datetime.now(UTC)
    ingest_time = now.isoformat(timespec="seconds")
    ingest_batch = ingest_batch or f"ORG_ENTITY_{now.strftime('%Y%m%dT%H%M%SZ')}"
    client = graph or (None if dry_run else get_trs_graph_client())
    since: str | None = None
    if mode == "incremental":
        since = Watermark.for_domain("org_entity").read()
        logger.info("incremental: org_entity watermark=%s", since)
    max_ts = ""
    specs = ENTITY_TABLE_SPECS if table == "all" else (ENTITY_TABLE_BY_NAME[table],)
    if domestic_only:
        specs = tuple(spec for spec in specs if spec.scope == "domestic")
    elif foreign_only:
        specs = tuple(spec for spec in specs if spec.scope == "foreign")
    if not specs:
        raise ValueError("no entity source tables selected")

    owns_session = session is None
    session_cm = gkx_element_read_session() if owns_session else None
    if session is None:
        assert session_cm is not None
        session = session_cm.__enter__()

    results: dict[str, EntityStats] = {}
    try:
        datasource_stats = EntityStats(queried=len(TABLE_CN_NAMES), valid=len(TABLE_CN_NAMES))
        _write_vertex_batches(
            datasource_records(),
            graph=client,
            batch_size=batch_size,
            dry_run=dry_run,
            stats=datasource_stats,
        )
        results["DataSource"] = datasource_stats

        for spec in specs:
            stats = EntityStats()
            results[spec.name] = stats
            pending: list[VertexRecord] = []
            for row in iter_source_rows(
                session,
                spec,
                max_records=max_records,
                since=since,
            ):
                stats.queried += 1
                _ts = row.get("updated_time") or row.get("update_time")
                if _ts and str(_ts) > max_ts:
                    max_ts = str(_ts)
                if is_virtual_source_row(row):
                    stats.skipped += 1
                    logger.info("skip synthetic entity source row table=%s", spec.name)
                    continue
                try:
                    records = vertices_from_row(spec, row, ingest_batch, ingest_time)
                except RelationDataError as exc:
                    stats.invalid += 1
                    stats.skipped += 1
                    logger.info("skip invalid entity table=%s reason=%s", spec.name, exc)
                    continue
                except Exception:
                    stats.invalid += 1
                    stats.skipped += 1
                    logger.exception("skip dirty entity row table=%s", spec.name)
                    continue
                if not records:
                    stats.skipped += 1
                    continue
                stats.valid += len(records)
                pending.extend(records)
                if len(pending) >= batch_size:
                    _write_vertex_batches(
                        pending,
                        graph=client,
                        batch_size=batch_size,
                        dry_run=dry_run,
                        stats=stats,
                    )
                    pending = []
            if pending:
                _write_vertex_batches(
                    pending,
                    graph=client,
                    batch_size=batch_size,
                    dry_run=dry_run,
                    stats=stats,
                )
            logger.info("completed entity table=%s stats=%s", spec.name, asdict(stats))
        # 整批成功后前进水位(中途抛异常则不前进→下次重跑这批,rank@0 幂等)
        if mode == "incremental" and not dry_run and max_ts:
            Watermark.for_domain("org_entity").advance_if_higher(max_ts)
            logger.info("org_entity watermark advanced to %s", max_ts)
        return results
    finally:
        if owns_session and session_cm is not None:
            session_cm.__exit__(None, None, None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser("init-schema")
    schema_parser.add_argument("--space", default=DEFAULT_SPACE)

    load_parser = subparsers.add_parser("load")
    load_parser.add_argument(
        "--table",
        choices=("all", *ENTITY_TABLE_BY_NAME),
        default="all",
    )
    load_parser.add_argument("--full", action="store_true", required=True)
    mode = load_parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--write", dest="dry_run", action="store_false")
    load_parser.set_defaults(dry_run=True)
    load_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    load_parser.add_argument("--max-records", type=int)
    load_parser.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default="full",
        help="full=全量;incremental=只灌 updated_time>水位 的行(读 script/.etl_watermark/org_entity.txt)",
    )
    load_parser.add_argument("--ingest-batch")
    scope = load_parser.add_mutually_exclusive_group()
    scope.add_argument("--domestic-only", action="store_true")
    scope.add_argument("--foreign-only", action="store_true")
    load_parser.add_argument("--space", default=DEFAULT_SPACE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    os.environ["TRS_GRAPH_SPACE"] = args.space
    if args.command == "init-schema":
        with exclusive_etl_lock("organization_entity_schema", "schema"):
            initialize_schema()
        return 0

    now = datetime.now(UTC)
    ingest_batch = args.ingest_batch or f"ORG_ENTITY_{now.strftime('%Y%m%dT%H%M%SZ')}"
    with exclusive_etl_lock("organization_entity_etl", ingest_batch):
        results = run_etl(
            table=args.table,
            full=args.full,
            batch_size=args.batch_size,
            max_records=args.max_records,
            dry_run=args.dry_run,
            domestic_only=args.domestic_only,
            foreign_only=args.foreign_only,
            ingest_batch=ingest_batch,
            mode=args.mode,
        )
    summary = {table: asdict(stats) for table, stats in results.items()}
    logger.info("organization entity ETL summary=%s", summary)
    return 1 if any(item.failed for item in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
