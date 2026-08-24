"""Entity mapping functions used by the one-entity extraction scripts.

机构域（Organization/Event/News/Product）映射严格复刻旧
``organization_entity_etl.py`` 的字段候选链、置信度打分、VID 与稳定键算法；
其余实体按各自旧脚本（load_scholar_entities / paper_journal_chain_etl /
load_patent_graph / load_project_graph / load_industry_chain_graph）的口径对齐。
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from script.entity_extractors_one_entity.common import (
    EntityRecord,
    bounded_json,
    date_text,
    datetime_text,
    event_vid,
    extra_json,
    first,
    first_value,
    is_virtual_source_row,
    json_snapshot,
    md5_vid,
    news_vid,
    normalized_language,
    org_provenance,
    organization_vid,
    original_text,
    paper_text,
    person_vid,
    product_vid,
    project_vid,
    provenance,
    source_record_id,
    stable_record_id,
    str_or_empty,
    text_or_empty,
    text_or_none,
    to_float_or_none,
    to_float_or_zero,
    to_int_or_none,
    to_int_or_zero,
)
from script.entity_extractors_one_entity.org_catalog import SPEC_BY_NAME, organization_kind

_PAPER_SUFFIX_RE = re.compile(r"__\d+$")


# ---------------------------------------------------------------------------
# Organization（机构域旧口径）
# ---------------------------------------------------------------------------


def organization_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    spec = SPEC_BY_NAME[table]
    if is_virtual_source_row(row):
        return []
    raw_org_id = first_value(row, "org_id", "company_id", "entity_eid")
    org_id = text_or_none(raw_org_id)
    if org_id is None:
        # 旧行为：缺机构 ID 整行跳过（RelationDataError 计 invalid），不做名称哈希兜底。
        return []
    record_id = stable_record_id(table, row, spec.raw_id_fields or ("org_id",))
    incorporation = first_value(row, "incorporation_year", "est_year", "incorporation_date")
    values: dict[str, Any] = {
        "org_id": org_id,
        "name_cn": text_or_none(
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
        "name_en": text_or_none(first_value(row, "name_en", "en_name")),
        "external_id": text_or_none(
            first_value(row, "external_id", "company_code", "school_code", "credit_no")
        ),
        "province": text_or_none(first_value(row, "province", "project_region_province")),
        "city": text_or_none(first_value(row, "city", "project_region_city")),
        "area": text_or_none(first_value(row, "area", "project_region_district")),
        "country_code": text_or_none(first_value(row, "country_code", "entity_country_code")),
        "country": text_or_none(row.get("country")),
        "address": text_or_none(first_value(row, "address", "company_address", "reg_address")),
        "postal_code": text_or_none(row.get("postal_code")),
        "phone": text_or_none(row.get("phone")),
        "email": text_or_none(row.get("email")),
        "legal_rep": text_or_none(first_value(row, "lerep", "legal_person", "legal_name")),
        "org_type": text_or_none(
            first_value(row, "org_type", "univ_type", "company_type", "industry_type")
        ),
        "org_size": text_or_none(first_value(row, "person_num", "employees_number")),
        "founded_year": to_int_or_none(incorporation),
        "listing_status": text_or_none(first_value(row, "listing_status", "listed_status")),
        "listed_date": text_or_none(first_value(row, "listing_date", "listed_date")),
        "registered_capital": to_float_or_none(
            first_value(row, "registered_capital_value", "capital_num", "capital")
        ),
        "capital_currency": text_or_none(
            first_value(
                row,
                "capital_currency",
                "registered_capital_currency_code",
                "currency_code",
                "currency",
            )
        ),
        "industry_class": text_or_none(
            first_value(row, "industry", "industry_class", "industry_l1_name")
        ),
        "stock_code": text_or_none(row.get("stock_code")),
        "stock_noun": text_or_none(row.get("stock_noun")),
        "stock_type": text_or_none(row.get("stock_type")),
        "org_kind": organization_kind(spec.name),
        "description": text_or_none(
            first_value(row, "description", "main_activities", "business_scope")
        ),
        "main_products": text_or_none(first_value(row, "main_products", "main_prod")),
        "extra_json": bounded_json(dict(row)),
        **org_provenance(table=table, record_id=record_id, row=row, ingest_batch=batch),
    }
    if spec.entity_kind == "organization_enrichment":
        # Enrichment 行只下发非空字段，防止稀疏产品/股票行覆盖基础属性（旧口径）。
        values = {name: value for name, value in values.items() if value is not None}
    return [EntityRecord("Organization", organization_vid(org_id), values, merge_protect=True)]


# ---------------------------------------------------------------------------
# Event（机构域旧口径）
# ---------------------------------------------------------------------------


def event_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    spec = SPEC_BY_NAME[table]
    if is_virtual_source_row(row):
        return []
    record_id = stable_record_id(table, row, spec.raw_id_fields)
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
    props = {
        "event_type": spec.entity_kind,
        "raw_id": record_id,
        "title": text_or_none(title) or spec.cn_name,
        "content": text_or_none(content) or bounded_json(dict(row)),
        "case_no": text_or_none(
            first_value(row, "case_no", "reg_no", "decision_no", "project_number")
        ),
        "case_cause": text_or_none(first_value(row, "case_cause", "case_type", "case_type_tag")),
        "occur_date": text_or_none(occur_date),
        "amount": to_float_or_none(amount),
        "currency": text_or_none(
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
        **org_provenance(table=table, record_id=record_id, row=row, ingest_batch=batch),
    }
    return [EntityRecord("Event", event_vid(table, record_id), props, merge_protect=True)]


# ---------------------------------------------------------------------------
# News（机构资讯 + 产业链新闻，分别复刻两个旧脚本口径）
# ---------------------------------------------------------------------------


def news_org_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    """机构重点资讯：旧 organization_entity_etl 口径，VID 含表名 + 整行哈希稳定键。"""
    if is_virtual_source_row(row):
        return []
    record_id = stable_record_id(table, row)
    props = {
        "title": text_or_none(row.get("news_title")),
        "content": text_or_none(row.get("news_content")),
        "release_date": text_or_none(row.get("news_date")),
        "original_url": text_or_none(row.get("original_textlink")),
        "extra_json": bounded_json(dict(row)),
        **org_provenance(table=table, record_id=record_id, row=row, ingest_batch=batch),
    }
    return [EntityRecord("News", news_vid(f"{table}_{record_id}"), props, merge_protect=True)]


def news_chain_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    """产业链新闻：旧 load_industry_chain_graph 口径，缺 news_id 跳过。"""
    news_id = text_or_none(row.get("news_id"))
    if news_id is None:
        return []
    props = {
        "title": text_or_empty(row.get("news_title") or row.get("title")),
        "content": text_or_empty(row.get("summary")),
        "release_date": text_or_empty(row.get("relaese_date")),
        "original_url": "",
        "source_system": table,
        "source_table": table,
        "source_record_id": news_id,
        "source_url": "",
        "ingest_batch": batch,
        "source_update_time": "",
        "extra_json": extra_json(row),
    }
    return [EntityRecord("News", f"news_{news_id}", props)]


# ---------------------------------------------------------------------------
# Product（机构域旧口径：从全部 Organization 表内联抽取主营产品）
# ---------------------------------------------------------------------------


def product_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    spec = SPEC_BY_NAME[table]
    if is_virtual_source_row(row):
        return []
    raw_org_id = first_value(row, "org_id", "company_id", "entity_eid")
    if text_or_none(raw_org_id) is None:
        # 旧行为：产品行随机构行处理，缺机构 ID 整行跳过、不建 Product。
        return []
    name = text_or_none(first_value(row, "main_prod", "main_products", "tech_product"))
    if name is None:
        return []
    record_id = stable_record_id(table, row, spec.raw_id_fields or ("org_id",))
    props = {
        "name": name,
        "category": text_or_none(first_value(row, "target_item_type", "industry_class")),
        "description": text_or_none(first_value(row, "description", "main_activities")),
        "extra_json": bounded_json(dict(row)),
        **org_provenance(table=table, record_id=record_id, row=row, ingest_batch=batch),
    }
    return [EntityRecord("Product", product_vid(name), props, merge_protect=True)]


# ---------------------------------------------------------------------------
# Person（机构角色人员，机构域旧口径）
# ---------------------------------------------------------------------------

_PERSON_ORG_TYPES = {"organization", "company", "enterprise", "机构", "企业", "公司"}
_PERSON_TYPES = {"person", "individual", "natural person", "自然人", "个人"}


def organization_role_person(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    """旧 person_record：股东/实控人类型过滤 + person_vid 旧公式。"""
    spec = SPEC_BY_NAME[table]
    if is_virtual_source_row(row):
        return []
    name = text_or_none(
        first_value(row, "executives_name", "bo_name", "entity_name", "owners_name")
    )
    if name is None:
        raise ValueError("missing person name")
    if spec.entity_kind == "shareholder":
        owner_type = (text_or_none(row.get("owners_type")) or "").casefold()
        if text_or_none(row.get("inv_org_id")) is not None or owner_type in _PERSON_ORG_TYPES:
            return []
        if owner_type not in _PERSON_TYPES:
            raise ValueError("shareholder endpoint type does not identify a Person")
    if spec.entity_kind == "actual_controller":
        entity_type = (text_or_none(row.get("entity_type")) or "").casefold()
        if entity_type in _PERSON_ORG_TYPES:
            return []
        if entity_type not in _PERSON_TYPES:
            raise ValueError("actual controller entity_type does not identify a Person")
    birth_date = text_or_none(first_value(row, "dm_birthdate", "bo_birthdate", "birth_date"))
    country = text_or_none(first_value(row, "dm_nationalities", "bo_country_code", "country_code"))
    target_identity = first_value(row, "org_id", "external_id")
    record_id = stable_record_id(table, row, spec.raw_id_fields)
    vid = person_vid(spec.entity_kind, target_identity, name, birth_date, country)
    props = {
        "name_cn": name,
        "name_en": name if spec.scope == "foreign" else None,
        "person_kind": spec.entity_kind,
        "country_code": text_or_none(first_value(row, "bo_country_code", "country_code")),
        "country": text_or_none(first_value(row, "dm_nationalities", "country")),
        "birth_date": birth_date,
        "gender": text_or_none(first_value(row, "bo_gender", "gender")),
        "biography": text_or_none(row.get("dm_biography")),
        "extra_json": bounded_json(dict(row)),
        **org_provenance(table=table, record_id=record_id, row=row, ingest_batch=batch),
    }
    return [EntityRecord("Person", vid, props, merge_protect=True)]


def legal_representative_person(
    table: str, row: Mapping[str, Any], batch: str
) -> list[EntityRecord]:
    """旧机构行内联的法定代表人 Person：lerep/legal_person 非空时建点。"""
    spec = SPEC_BY_NAME[table]
    if is_virtual_source_row(row):
        return []
    raw_org_id = first_value(row, "org_id", "company_id", "entity_eid")
    org_id = text_or_none(raw_org_id)
    legal_name = text_or_none(first_value(row, "lerep", "legal_person"))
    if org_id is None or legal_name is None:
        return []
    record_id = stable_record_id(table, row, spec.raw_id_fields or ("org_id",))
    legal_record_id = f"{record_id}|legal_representative|{legal_name}"
    vid = person_vid("legal_representative", org_id, legal_name)
    props = {
        "name_cn": legal_name,
        "person_kind": "legal_representative",
        "extra_json": bounded_json(dict(row)),
        **org_provenance(table=table, record_id=legal_record_id, row=row, ingest_batch=batch),
    }
    return [EntityRecord("Person", vid, props, merge_protect=True)]


# ---------------------------------------------------------------------------
# Project（项目域旧口径）
# ---------------------------------------------------------------------------

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
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    return bool(value)


def project_confidence(row: Mapping[str, Any]) -> float:
    """复刻旧 project_confidence：核心字段完整度，缺 title 封顶 0.6，下限 0.3。"""
    values = {f: row.get(f) for f in PROJECT_CONFIDENCE_FIELDS}
    filled = sum(1 for v in values.values() if _has_value(v))
    ratio = filled / len(PROJECT_CONFIDENCE_FIELDS)
    if not _has_value(values["title"]):
        ratio = min(ratio, 0.6)
    return round(max(0.3, ratio), 4)


def project_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    pid = text_or_empty(row.get("id"))
    if not pid:
        return []
    props = {
        "project_number": text_or_empty(row.get("project_number")),
        "title": text_or_empty(row.get("title")),
        "project_source": text_or_empty(row.get("project_source")),
        "project_level": text_or_empty(row.get("project_level")),
        "funded_amount": to_float_or_zero(row.get("funded_amount")),
        "discipline": text_or_empty(row.get("discipline")),
        "discipline_code": text_or_empty(row.get("discipline_code")),
        "fund_category": text_or_empty(row.get("fund_category")),
        "funded_region": text_or_empty(row.get("funded_province")),
        "approval_year": date_text(row.get("approval_year")),
        "approval_time": date_text(row.get("approval_time")),
        "research_period": text_or_empty(row.get("research_period")),
        "abstract": text_or_empty(row.get("abstract")),
        # 旧 ORM 未给 dwd_en_project 建模 final_report_abstract，英文项目恒为空。
        "final_report_abstract": (
            "" if table == "dwd_en_project" else text_or_empty(row.get("final_report_abstract"))
        ),
        "project_page_url": text_or_empty(row.get("project_page_url")),
        "source": "zh_project" if table == "dwd_zh_project" else "en_project",
        "total_outputs": to_int_or_zero(row.get("total_outputs")),
        "journal_articles_count": to_int_or_zero(row.get("journal_articles_count")),
        "conference_papers_count": to_int_or_zero(row.get("conference_papers_count")),
        "books_count": to_int_or_zero(row.get("books_count")),
        "degree_papers_count": to_int_or_zero(row.get("degree_papers_count")),
        "patents_count": to_int_or_zero(row.get("patents_count")),
        "clinical_trials_count": to_int_or_zero(row.get("clinical_trials_count")),
        "products_count": to_int_or_zero(row.get("products_count")),
        "awards_count": to_int_or_zero(row.get("awards_count")),
        "reports_count": to_int_or_zero(row.get("reports_count")),
        "other_outputs_count": to_int_or_zero(row.get("other_outputs_count")),
        "extra_json": extra_json(row),
        **provenance(
            table=table,
            record_id=pid,
            ingest_batch=batch,
            source_url=row.get("project_page_url"),
            source_update_time=date_text(row.get("updated_time") or row.get("update_time")),
            confidence=project_confidence(row),
        ),
    }
    return [EntityRecord("Project", project_vid(pid), props)]


# ---------------------------------------------------------------------------
# Paper / Journal / Report（论文工作流旧口径）
# ---------------------------------------------------------------------------


def paper_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    pid = text_or_empty(row.get("id"))
    if not pid:
        return []
    vid = f"paper_{pid}"
    props = {
        "doi": paper_text(row.get("doi")),
        "title_zh": paper_text(row.get("zh_name") or row.get("title_zh")),
        "title_en": paper_text(row.get("en_name") or row.get("title_en")),
        "publication_year": text_or_empty(row.get("publication_year")),
        # 旧口径：publication_name 固定写 publication_id 列的值。
        "publication_name": paper_text(row.get("publication_id")),
        "source": "gkx",
        "extra_json": extra_json(row),
        **provenance(
            table=table,
            record_id=vid,
            ingest_batch=batch,
            source_update_time=row.get("updated_time"),
        ),
    }
    return [EntityRecord("Paper", vid, props)]


def journal_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    jid = row.get("journal_id")
    if not jid:
        # 旧口径：journal_id 为空/0 跳过。
        return []
    vid = f"journal_{jid}"
    props = {
        "name_en": paper_text(row.get("journal_en_name") or row.get("name_en")),
        "name_zh": paper_text(row.get("journal_zh_name") or row.get("name_zh")),
        "issn": paper_text(row.get("issn")),
        "country": paper_text(row.get("country")),
        "extra_json": extra_json(row),
        **provenance(table=table, record_id=vid, ingest_batch=batch),
    }
    return [EntityRecord("Journal", vid, props)]


def report_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    rid = row.get("report_id")
    if not rid:
        return []
    vid = f"report_{rid}"
    props = {
        # 旧口径：标题 title_cn 优先 title_en 兜底，摘要仅 abstract_cn。
        "title": paper_text(row.get("title_cn") or row.get("title_en")),
        "abstract": paper_text(row.get("abstract_cn")),
        "extra_json": extra_json(row),
        **provenance(
            table=table,
            record_id=vid,
            ingest_batch=batch,
            source_update_time=row.get("updated_time"),
        ),
    }
    return [EntityRecord("Report", vid, props)]


# ---------------------------------------------------------------------------
# Keyword（专利域旧口径的解析与 VID）
# ---------------------------------------------------------------------------


def _keyword_values(value: Any) -> list[str]:
    parsed = value if not isinstance(value, str) else _try_parse_json(value)
    if not isinstance(parsed, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        if isinstance(item, dict):
            item = item.get("zhName") or item.get("enName") or item.get("name") or ""
        keyword = " ".join(unicodedata.normalize("NFKC", str(item)).strip().split())
        key = keyword.casefold()
        if keyword and key not in seen:
            seen.add(key)
            result.append(keyword)
    return result


def _try_parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def keyword_records(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    raw = first(row, "keywords", "keyword", "main_ipcr", "further_ipcr", "fields")
    if not raw:
        return []
    values = _keyword_values(raw)
    if not values and isinstance(raw, str):
        values = [item.strip() for item in raw.replace("；", ",").split(",") if item.strip()]
    records = []
    for value in values:
        if not value:
            continue
        props = {
            "keyword": value,
            "extra_json": extra_json(row),
            **provenance(
                table=table,
                record_id=source_record_id(row, "id", "patent_id", "scholar_id"),
                ingest_batch=batch,
            ),
        }
        records.append(EntityRecord("Keyword", md5_vid("keyword", value, short=False), props))
    return records


# ---------------------------------------------------------------------------
# Patent / PatentFamily（专利域旧口径）
# ---------------------------------------------------------------------------


def patent_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    pid = str_or_empty(row.get("patent_id")).strip()
    if not pid:
        raise ValueError("patent_id 为空")
    props = {
        "patent_id": pid,
        "publication_number": str_or_empty(row.get("publication_number")),
        "application_number": str_or_empty(row.get("application_number")),
        "application_kind": str_or_empty(row.get("application_kind")),
        "country_code": str_or_empty(row.get("country_code")),
        "country": str_or_empty(row.get("country")),
        "publication_date": to_int_or_zero(row.get("publication_date")),
        "application_date": to_int_or_zero(row.get("application_date")),
        "granted_number": str_or_empty(row.get("granted_number")),
        "grant_date": str_or_empty(row.get("grant_date")),
        "status": str_or_empty(row.get("status")),
        "anticipated_expiration": to_int_or_zero(row.get("anticipated_expiration")),
        "title_original": original_text(row.get("titles")),
        "title_en": str_or_empty(row.get("title_en")),
        "title_zh": str_or_empty(row.get("title_zh")),
        "abstract_zh": str_or_empty(row.get("abstract_zh")),
        "language": normalized_language(row.get("language")),
        "main_ipcr": str_or_empty(row.get("main_ipcr")),
        "further_ipcr": json_snapshot(row.get("further_ipcr")),
        "main_cpc": str_or_empty(row.get("main_cpc")),
        "further_cpc": json_snapshot(row.get("further_cpc")),
        "keywords": json_snapshot(row.get("keywords")),
        "citation_nums": to_int_or_zero(row.get("citation_nums")),
        "cited_by_nums": to_int_or_zero(row.get("cited_by_nums")),
        "patent_value": to_int_or_zero(row.get("patent_value")),
        "simple_family_number": str_or_empty(row.get("simple_family_number")),
        "db_source": str_or_empty(row.get("db_source")),
        "create_time": datetime_text(row.get("create_time")),
        "update_time": datetime_text(row.get("update_time")),
        "organization_base": "dwd_patent",
        "organization_id": pid,
        "extra_json": extra_json(row),
        **provenance(
            table=table,
            record_id=pid,
            ingest_batch=batch,
            source_update_time=datetime_text(row.get("update_time")),
        ),
    }
    return [EntityRecord("Patent", f"patent_{pid}", props)]


def patent_family_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    family = str_or_empty(row.get("simple_family_number")).strip()
    if not family:
        return []
    props = {
        "family_number": family,
        "organization_base": "dwd_patent_family",
        "organization_id": family,
        "extra_json": extra_json(row),
        **provenance(table="dwd_patent_family", record_id=family, ingest_batch=batch),
    }
    return [EntityRecord("PatentFamily", f"patent_family_{family}", props)]


# ---------------------------------------------------------------------------
# IndustryChain / IndustryNode（产业链旧口径）
# ---------------------------------------------------------------------------


def industry_chain_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    code = text_or_empty(row.get("chain_code"))
    if not code:
        return []
    props = {
        "chain_code": code,
        "chain_name": text_or_empty(row.get("chain_name")),
        "extra_json": extra_json(row),
        **provenance(table=table, record_id=code, ingest_batch=batch),
    }
    return [EntityRecord("IndustryChain", f"chain_{code}", props)]


def industry_node_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    nid = text_or_empty(row.get("node_id"))
    if not nid:
        return []
    props = {
        "node_id": nid,
        "node_name": text_or_empty(row.get("node_name")),
        "node_type": text_or_empty(row.get("node_type")),
        "level": text_or_empty(row.get("level")),
        "node_seq": text_or_empty(row.get("node_seq")),
        "node_imp_level": text_or_empty(row.get("node_imp_level")),
        "node_stage": text_or_empty(row.get("node_stage")),
        "node_path": text_or_empty(row.get("node_path")),
        "extra_json": extra_json(row),
        **provenance(table=table, record_id=nid, ingest_batch=batch),
    }
    return [EntityRecord("IndustryNode", f"node_{nid}", props)]
