"""gkx_element 国内/国外机构领域 → TRSGraph dev 图空间 ETL。

特点：
- MySQL 只读；不依赖与实际表结构不一致的旧 ORM。
- 节点与边全部走 TRSGraphClient.execute_write(nGQL)，不调用已知不可靠的 Node REST。
- 39 张表、确定性 VID/edge rank、批次 manifest、dry-run、详细字段映射文档。

示例：
  python -m script.organization_graph_etl init-schema --space dev
  python -m script.organization_graph_etl load --space dev --source-batch MOCK_ORG_20260721_01
  python -m script.organization_graph_etl load --space dev --full
  python -m script.organization_graph_etl generate-mapping
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import time
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from infra.gkx_element import gkx_element_read_session
from infra.graph_db.client import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logger = logging.getLogger("script.organization_graph_etl")

DEFAULT_SPACE = "dev"
DEFAULT_BATCH_SIZE = 100
SOURCE_SYSTEM = "gkx_element"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "dev_organization_graph.ngql"
MAPPING_PATH = Path(__file__).resolve().parents[1] / "schemas" / "organization_mapping.md"
OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "output" / "organization_graph"


@dataclass(frozen=True)
class TableSpec:
    name: str
    cn_name: str
    kind: str
    graph_target: str
    event_type: str = ""
    raw_id_fields: tuple[str, ...] = ()


TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec("dwd_org_base_info", "机构基本信息", "org_base", "Organization"),
    TableSpec("dwd_org_heis_info", "高校基本信息", "org_base", "Organization"),
    TableSpec("dwd_research_institute_base_info", "科研机构基本信息", "org_base", "Organization"),
    TableSpec("dwd_special_hongkong_company", "香港企业", "org_base", "Organization"),
    TableSpec("dwd_special_taiwan_company", "台湾企业", "org_base", "Organization"),
    TableSpec("dwd_special_aomen_company", "澳门企业", "org_base", "Organization"),
    TableSpec("dwd_forg_base_info", "海外机构基本信息", "org_base", "Organization"),
    TableSpec("dwd_org_org_product_info", "国内机构经营信息", "org_enrich", "Organization"),
    TableSpec("dwd_org_stock_base", "上市企业基本信息", "org_enrich", "Organization"),
    TableSpec("dwd_forg_product_info", "海外机构经营信息", "org_enrich", "Organization"),
    TableSpec("dwd_org_shareholder_info", "国内机构股东信息", "relation", "SHAREHOLDER_OF"),
    TableSpec("dwd_forg_shareholder_info", "海外机构股东信息", "relation", "SHAREHOLDER_OF"),
    TableSpec("dwd_org_executive_info", "国内机构高管信息", "relation", "EXECUTIVE_OF"),
    TableSpec("dwd_forg_executive_info", "海外机构高管信息", "relation", "EXECUTIVE_OF"),
    TableSpec("dwd_org_invest_info", "投资事件", "relation", "INVESTS_IN"),
    TableSpec("dwd_org_merger_acquisition_info", "并购事件", "relation", "ACQUIRES"),
    TableSpec("dwd_forg_subsidiary_info", "海外机构子公司", "relation", "SUBSIDIARY_OF"),
    TableSpec("dwd_forg_beneficiary_info", "海外机构受益人", "relation", "BENEFICIAL_OWNER_OF"),
    TableSpec("dwd_forg_act_contro_info", "海外机构实际控制人", "relation", "ACTUAL_CONTROLLER_OF"),
    TableSpec("dwd_org_important_news_info", "重点资讯", "news", "News + HAS_NEWS"),
    TableSpec(
        "dwd_org_annual_financial_info",
        "年报财务信息",
        "event",
        "Event + INVOLVED_IN",
        "annual_finance",
        ("org_id", "year"),
    ),
    TableSpec(
        "dwd_org_stock_finance_info",
        "上市企业财务信息",
        "event",
        "Event + INVOLVED_IN",
        "stock_finance",
        ("org_id", "occur_period"),
    ),
    TableSpec(
        "dwd_forg_stock_fin_info",
        "海外上市企业财务信息",
        "event",
        "Event + INVOLVED_IN",
        "stock_finance",
        ("org_id", "occur_period"),
    ),
    TableSpec(
        "dwd_org_changerecord_info",
        "工商变更",
        "event",
        "Event + INVOLVED_IN",
        "change_record",
        ("org_id", "update_date", "update_content"),
    ),
    TableSpec(
        "dwd_org_financing_info",
        "融资事件",
        "event",
        "Event + INVOLVED_IN",
        "financing",
        ("org_id", "completion_date", "funding_round"),
    ),
    TableSpec(
        "dwd_org_recruit_info",
        "招聘信息",
        "event",
        "Event + INVOLVED_IN",
        "recruit",
        ("org_id", "release_date", "job_title"),
    ),
    TableSpec(
        "dwd_org_company_abnormal",
        "经营异常",
        "event",
        "Event + INVOLVED_IN",
        "abnormal",
        ("abnormal_id",),
    ),
    TableSpec(
        "dwd_org_company_punish",
        "行政处罚",
        "event",
        "Event + INVOLVED_IN",
        "punish",
        ("penalty_id",),
    ),
    TableSpec(
        "dwd_org_company_illegal",
        "严重违法",
        "event",
        "Event + INVOLVED_IN",
        "illegal",
        ("sv_id",),
    ),
    TableSpec(
        "dwd_org_risk_tax_punish",
        "税收违法",
        "event",
        "Event + INVOLVED_IN",
        "tax_punish",
        ("tax_vio_id",),
    ),
    TableSpec(
        "dwd_org_opt_judicial_case",
        "司法案件",
        "event",
        "Event + INVOLVED_IN",
        "judicial_case",
        ("case_id",),
    ),
    TableSpec(
        "dwd_org_risk_shixin",
        "失信被执行人",
        "event",
        "Event + INVOLVED_IN",
        "shixin",
        ("dishonest_id",),
    ),
    TableSpec(
        "dwd_org_risk_zhixing",
        "被执行人",
        "event",
        "Event + INVOLVED_IN",
        "zhixing",
        ("exec_person_id",),
    ),
    TableSpec(
        "dwd_org_bankruptcy_public_cases",
        "破产案件",
        "bankruptcy_base",
        "Event + INVOLVED_IN",
        "bankruptcy",
        ("case_no",),
    ),
    TableSpec(
        "dwd_org_bankruptcy_public_cases_list",
        "破产案件当事人",
        "bankruptcy_party",
        "INVOLVED_IN",
        "bankruptcy",
        ("bankruptcy_party_id",),
    ),
    TableSpec("dwd_bid_base_out", "招投标公告", "bid_base", "Event", "bid", ("u_id",)),
    TableSpec("dwd_bid_win_candidate_out", "中标候选人", "bid_party", "INVOLVED_IN", "bid"),
    TableSpec("dwd_bid_purchase_agency_out", "采购代理", "bid_party", "INVOLVED_IN", "bid"),
    TableSpec("dwd_bid_target_item_out", "招投标标的物", "bid_content", "Event.content", "bid"),
)

TABLE_BY_NAME = {spec.name: spec for spec in TABLE_SPECS}
assert len(TABLE_SPECS) == 39 and len(TABLE_BY_NAME) == 39

TAG_PROPERTIES: dict[str, tuple[str, ...]] = {
    "Organization": (
        "org_id",
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
}

EDGE_PROPERTIES: dict[str, tuple[str, ...]] = {
    "LEGAL_REP_OF": (
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "SHAREHOLDER_OF": (
        "ownership_percentage",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "EXECUTIVE_OF": (
        "position",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "INVESTS_IN": (
        "investment_amount",
        "investment_ratio",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "ACQUIRES": (
        "ma_amount",
        "currency_code",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "SUBSIDIARY_OF": (
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "BENEFICIAL_OWNER_OF": (
        "direct_percent",
        "indirect_percent",
        "total_percent",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "ACTUAL_CONTROLLER_OF": (
        "direct_pct",
        "total_pct",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "HAS_NEWS": ("extra_json", "source_table", "source_record_id", "ingest_batch", "ingest_time"),
    "INVOLVED_IN": (
        "role",
        "extra_json",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
    "SOURCED_FROM": ("source_table", "source_record_id", "ingest_batch", "ingest_time"),
    "DERIVED_FROM": (
        "transform",
        "source_table",
        "source_record_id",
        "ingest_batch",
        "ingest_time",
    ),
}

NUMERIC_TAG_PROPERTIES = {"founded_year", "registered_capital", "amount"}
NUMERIC_EDGE_PROPERTIES = {
    "ownership_percentage",
    "investment_amount",
    "investment_ratio",
    "ma_amount",
    "direct_percent",
    "indirect_percent",
    "total_percent",
    "direct_pct",
    "total_pct",
}


@dataclass
class NodeRecord:
    tag: str
    vid: str
    props: dict[str, Any]


@dataclass
class EdgeRecord:
    edge_type: str
    source: str
    target: str
    rank: int
    props: dict[str, Any]


@dataclass
class GraphBuffer:
    ingest_batch: str
    ingest_time: str
    nodes: dict[tuple[str, str], NodeRecord] = field(default_factory=dict)
    edges: dict[tuple[str, str, str, int], EdgeRecord] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    table_comments: dict[str, str] = field(default_factory=dict)

    def add_node(
        self,
        tag: str,
        vid: str,
        props: dict[str, Any],
        *,
        overwrite_fields: Iterable[str] = (),
    ) -> NodeRecord:
        vid = bounded_vid(vid)
        key = (tag, vid)
        allowed = set(TAG_PROPERTIES[tag])
        clean = {name: normalize_value(value) for name, value in props.items() if name in allowed}
        overwrite = set(overwrite_fields)
        existing = self.nodes.get(key)
        if existing is None:
            full = {
                name: default_property(name, numeric=name in NUMERIC_TAG_PROPERTIES)
                for name in TAG_PROPERTIES[tag]
            }
            full.update(clean)
            existing = NodeRecord(tag=tag, vid=vid, props=full)
            self.nodes[key] = existing
            return existing
        for name, value in clean.items():
            if name in overwrite or is_empty(existing.props.get(name)):
                existing.props[name] = value
        return existing

    def add_edge(
        self,
        edge_type: str,
        source: str,
        target: str,
        source_record_id: str,
        props: dict[str, Any] | None = None,
    ) -> EdgeRecord:
        source = bounded_vid(source)
        target = bounded_vid(target)
        rank = stable_rank(f"{edge_type}|{source}|{target}|{source_record_id}")
        allowed = set(EDGE_PROPERTIES[edge_type])
        full = {
            name: default_property(name, numeric=name in NUMERIC_EDGE_PROPERTIES)
            for name in EDGE_PROPERTIES[edge_type]
        }
        if props:
            full.update(
                {name: normalize_value(value) for name, value in props.items() if name in allowed}
            )
        key = (edge_type, source, target, rank)
        edge = EdgeRecord(edge_type=edge_type, source=source, target=target, rank=rank, props=full)
        self.edges[key] = edge
        return edge


def is_empty(value: Any) -> bool:
    return value is None or value == ""


def normalize_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return 0.0
    return value


def default_property(name: str, *, numeric: bool) -> Any:
    if numeric:
        return 0.0 if name not in {"founded_year"} else 0
    return ""


def text_value(value: Any) -> str:
    value = normalize_value(value)
    return "" if value is None else str(value).strip()


def int_value(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(str(value)))
    except (TypeError, ValueError):
        match = re.search(r"(?:19|20)\d{2}", str(value))
        return int(match.group(0)) if match else 0


def float_value(value: Any) -> float:
    try:
        if value in (None, "", "-", "n.a.", "N/A"):
            return 0.0
        cleaned = re.sub(r"[^0-9.+-]", "", str(value).replace(",", ""))
        return float(Decimal(cleaned)) if cleaned else 0.0
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def first_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return ""


def normalized_name(value: Any) -> str:
    return unicodedata.normalize("NFKC", text_value(value)).casefold()


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def bounded_vid(value: str, max_bytes: int = 64) -> str:
    value = text_value(value)
    if len(value.encode("utf-8")) <= max_bytes:
        return value
    suffix = "_" + md5_hex(value)
    budget = max_bytes - len(suffix.encode("utf-8"))
    chars: list[str] = []
    size = 0
    for char in value:
        width = len(char.encode("utf-8"))
        if size + width > budget:
            break
        chars.append(char)
        size += width
    return "".join(chars) + suffix


def organization_vid(org_id: Any) -> str:
    raw = text_value(org_id) or "missing_" + md5_hex(str(org_id))
    return bounded_vid(f"org_{raw}")


def person_vid(name: Any) -> str:
    return f"person_{md5_hex(normalized_name(name))}"


def event_vid(table: str, raw_id: Any) -> str:
    return bounded_vid(f"event_{table}_{text_value(raw_id)}")


def datasource_vid(table: str, *, raw: bool = False) -> str:
    prefix = "ds_raw_" if raw else "ds_"
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", table).strip("_")
    safe = safe or md5_hex(table)
    return bounded_vid(prefix + safe)


def stable_rank(value: str) -> int:
    # Nebula edge rank 为有符号 int64；保留 63 位正数。
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") & (
        (1 << 63) - 1
    )


def stable_record_id(table: str, row: dict[str, Any], preferred: Iterable[str] = ()) -> str:
    pieces = [text_value(row.get(name)) for name in preferred]
    if pieces and all(pieces):
        return "|".join(pieces)
    canonical = json.dumps(
        {key: normalize_value(row[key]) for key in sorted(row)},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return md5_hex(f"{table}|{canonical}")


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def provenance_props(
    table: str, record_id: str, row: dict[str, Any], ingest_batch: str, ingest_time: str
) -> dict[str, Any]:
    return {
        "source_system": SOURCE_SYSTEM,
        "source_table": table,
        "source_record_id": record_id,
        "source_url": text_value(
            first_value(
                row,
                "source_url",
                "original_textlink",
                "original_link",
                "link",
                "url",
            )
        ),
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
        "source_update_time": text_value(first_value(row, "updated_time", "update_time")),
    }


def edge_provenance(
    table: str, record_id: str, ingest_batch: str, ingest_time: str
) -> dict[str, Any]:
    return {
        "source_table": table,
        "source_record_id": record_id,
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
    }


def ngql_literal(value: Any, *, numeric: bool = False) -> str:
    if numeric:
        if value in (None, ""):
            return "0"
        number = float_value(value)
        if number.is_integer():
            return str(int(number))
        return format(number, ".12g")
    return json.dumps(text_value(value), ensure_ascii=False)


def chunked(items: list[Any], size: int) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def get_table_metadata(session: Session) -> dict[str, dict[str, Any]]:
    """Return live column metadata for the 39 tables in deterministic order."""
    names = list(TABLE_BY_NAME)
    bind_names = ",".join(f":t{i}" for i in range(len(names)))
    params = {f"t{i}": name for i, name in enumerate(names)}
    sql = text(
        "SELECT c.TABLE_NAME,c.COLUMN_NAME,c.ORDINAL_POSITION,c.COLUMN_TYPE,"
        "c.IS_NULLABLE,c.COLUMN_COMMENT,COALESCE(t.TABLE_COMMENT,'') AS TABLE_COMMENT "
        "FROM information_schema.COLUMNS c "
        "JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA "
        "AND t.TABLE_NAME=c.TABLE_NAME "
        "WHERE c.TABLE_SCHEMA=DATABASE() AND c.TABLE_NAME IN (" + bind_names + ") "
        "ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION"
    )
    result: dict[str, dict[str, Any]] = {name: {"comment": "", "columns": []} for name in names}
    for row in session.execute(sql, params).mappings():
        item = dict(row)
        table = item.pop("TABLE_NAME")
        result[table]["comment"] = item.pop("TABLE_COMMENT") or ""
        result[table]["columns"].append(item)
    missing = [name for name, item in result.items() if not item["columns"]]
    if missing:
        raise RuntimeError(f"源数据库缺少映射表: {', '.join(missing)}")
    return result


def iter_table_rows(
    session: Session,
    table: str,
    columns: list[str],
    *,
    source_batch: str | None,
    fetch_size: int,
) -> Iterator[dict[str, Any]]:
    """Stream rows without ever mutating the source database."""
    sql = f"SELECT * FROM `{table}`"
    params: dict[str, Any] = {}
    if source_batch:
        if "data_source" in columns:
            sql += " WHERE `data_source`=:source_batch"
            params["source_batch"] = source_batch
        elif "org_id" in columns:
            date_token = next(iter(re.findall(r"\d{8}", source_batch)), "")
            prefix = f"MOCK_FORG_{date_token}_%" if date_token else "MOCK_FORG_%"
            sql += " WHERE `org_id` LIKE :foreign_prefix"
            params["foreign_prefix"] = prefix
        else:
            raise RuntimeError(f"{table} 无法按 source_batch 安全筛选")
    sql += " ORDER BY 1"
    result = session.execute(text(sql), params).mappings().yield_per(fetch_size)
    for row in result:
        yield dict(row)


def org_kind_for(table: str) -> str:
    return {
        "dwd_org_heis_info": "domestic_university",
        "dwd_research_institute_base_info": "domestic_research_institute",
        "dwd_special_hongkong_company": "hong_kong_company",
        "dwd_special_taiwan_company": "taiwan_company",
        "dwd_special_aomen_company": "macao_company",
        "dwd_forg_base_info": "foreign_organization",
    }.get(table, "domestic_organization")


def organization_props(
    table: str,
    row: dict[str, Any],
    record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> dict[str, Any]:
    incorporation = text_value(
        first_value(row, "incorporation_year", "est_year", "incorporation_date")
    )
    return {
        "org_id": text_value(first_value(row, "org_id", "company_id", "entity_eid")),
        "name_cn": text_value(
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
        "name_en": text_value(first_value(row, "name_en", "en_name")),
        "external_id": text_value(
            first_value(row, "external_id", "company_code", "school_code", "credit_no")
        ),
        "province": text_value(first_value(row, "province", "project_region_province")),
        "city": text_value(first_value(row, "city", "project_region_city")),
        "area": text_value(first_value(row, "area", "project_region_district")),
        "country_code": text_value(first_value(row, "country_code", "entity_country_code")),
        "country": text_value(first_value(row, "country")),
        "address": text_value(first_value(row, "address", "company_address", "reg_address")),
        "postal_code": text_value(first_value(row, "postal_code")),
        "phone": text_value(first_value(row, "phone")),
        "email": text_value(first_value(row, "email")),
        "legal_rep": text_value(first_value(row, "lerep", "legal_person", "legal_name")),
        "org_type": text_value(
            first_value(row, "org_type", "univ_type", "company_type", "industry_type")
        ),
        "org_size": text_value(first_value(row, "person_num", "employees_number")),
        "founded_year": int_value(incorporation),
        "listing_status": text_value(first_value(row, "listing_status", "listed_status")),
        "listed_date": text_value(first_value(row, "listing_date", "listed_date")),
        "registered_capital": float_value(
            first_value(row, "registered_capital_value", "capital_num", "capital")
        ),
        "capital_currency": text_value(
            first_value(
                row,
                "capital_currency",
                "registered_capital_currency_code",
                "currency_code",
                "currency",
            )
        ),
        "industry_class": text_value(
            first_value(row, "industry", "industry_class", "industry_l1_name")
        ),
        "stock_code": text_value(first_value(row, "stock_code")),
        "stock_noun": text_value(first_value(row, "stock_noun")),
        "stock_type": text_value(first_value(row, "stock_type")),
        "org_kind": org_kind_for(table),
        "description": text_value(
            first_value(row, "description", "main_activities", "business_scope")
        ),
        "main_products": text_value(first_value(row, "main_products", "main_prod")),
        "extra_json": json_text({key: normalize_value(value) for key, value in row.items()}),
        **provenance_props(table, record_id, row, ingest_batch, ingest_time),
    }


def add_datasource_links(
    buffer: GraphBuffer,
    spec: TableSpec,
    row: dict[str, Any],
    record_id: str,
    business_vids: Iterable[str],
) -> None:
    ds_vid = datasource_vid(spec.name)
    buffer.add_node(
        "DataSource",
        ds_vid,
        {
            "source_table": spec.name,
            "table_cn_name": spec.cn_name,
            "tier": "DWD",
            "library": "国内机构要素库"
            if not spec.name.startswith("dwd_forg_")
            else "国外机构要素库",
        },
    )
    edge_props = edge_provenance(spec.name, record_id, buffer.ingest_batch, buffer.ingest_time)
    for vid in business_vids:
        buffer.add_edge("SOURCED_FROM", vid, ds_vid, record_id, edge_props)

    raw_table = text_value(row.get("data_source"))
    if raw_table and not raw_table.startswith("MOCK_"):
        raw_vid = datasource_vid(raw_table, raw=True)
        buffer.add_node(
            "DataSource",
            raw_vid,
            {
                "source_table": raw_table,
                "table_cn_name": "原始来源表",
                "tier": "RAW/ODS",
                "library": SOURCE_SYSTEM,
            },
        )
        buffer.add_edge(
            "DERIVED_FROM",
            raw_vid,
            ds_vid,
            record_id,
            {
                **edge_props,
                "transform": f"{raw_table} -> {spec.name}",
            },
        )


def ensure_org(
    buffer: GraphBuffer,
    org_id: Any,
    name: Any,
    table: str,
    record_id: str,
    row: dict[str, Any],
) -> str:
    raw_id = text_value(org_id)
    if not raw_id:
        raw_id = "name_" + md5_hex(normalized_name(name) or record_id)
    vid = organization_vid(raw_id)
    buffer.add_node(
        "Organization",
        vid,
        {
            "org_id": raw_id,
            "name_cn": text_value(name),
            "org_kind": org_kind_for(table),
            **provenance_props(table, record_id, row, buffer.ingest_batch, buffer.ingest_time),
        },
    )
    return vid


def ensure_person(
    buffer: GraphBuffer,
    name: Any,
    table: str,
    record_id: str,
    row: dict[str, Any],
    *,
    person_kind: str,
) -> str:
    display_name = text_value(name) or "未知人员"
    vid = person_vid(display_name)
    buffer.add_node(
        "Person",
        vid,
        {
            "name_cn": display_name,
            "name_en": display_name if table.startswith("dwd_forg_") else "",
            "person_kind": person_kind,
            "country_code": text_value(first_value(row, "bo_country_code", "owners_country_code")),
            "country": text_value(first_value(row, "owners_country", "dm_nationalities")),
            "birth_date": text_value(first_value(row, "bo_birthdate", "dm_birthdate")),
            "gender": text_value(first_value(row, "bo_gender", "gender")),
            "biography": text_value(first_value(row, "dm_biography")),
            "extra_json": json_text({key: normalize_value(value) for key, value in row.items()}),
            **provenance_props(table, record_id, row, buffer.ingest_batch, buffer.ingest_time),
        },
    )
    return vid


def relation_endpoints(
    spec: TableSpec, row: dict[str, Any], record_id: str, buffer: GraphBuffer
) -> tuple[str, str, dict[str, Any]]:
    table = spec.name
    target = ensure_org(
        buffer,
        row.get("org_id"),
        first_value(row, "name_cn", "company_name", "taxpayer_name"),
        table,
        record_id,
        row,
    )
    props: dict[str, Any] = {}
    if table == "dwd_org_shareholder_info":
        owner_name = first_value(row, "owners_name", "inv_name")
        if text_value(row.get("inv_org_id")) or text_value(row.get("owners_type")) in {
            "机构",
            "企业",
            "organization",
            "company",
        }:
            source = ensure_org(buffer, row.get("inv_org_id"), owner_name, table, record_id, row)
        else:
            source = ensure_person(
                buffer, owner_name, table, record_id, row, person_kind="shareholder"
            )
        props["ownership_percentage"] = float_value(row.get("ownership_percentage"))
        return source, target, props
    if table == "dwd_forg_shareholder_info":
        owner_name = row.get("owners_name")
        looks_org = bool(
            re.search(
                r"\b(?:ltd|inc|corp|company|plc|llc|group|fund)\b", text_value(owner_name), re.I
            )
        )
        source = (
            ensure_org(
                buffer,
                "name_" + md5_hex(normalized_name(owner_name)),
                owner_name,
                table,
                record_id,
                row,
            )
            if looks_org
            else ensure_person(buffer, owner_name, table, record_id, row, person_kind="shareholder")
        )
        props["ownership_percentage"] = float_value(row.get("ownership_percentage"))
        return source, target, props
    if table in {"dwd_org_executive_info", "dwd_forg_executive_info"}:
        source = ensure_person(
            buffer, row.get("executives_name"), table, record_id, row, person_kind="executive"
        )
        props["position"] = text_value(row.get("executives_position"))
        return source, target, props
    if table == "dwd_org_invest_info":
        source = target
        target = ensure_org(
            buffer, row.get("inv_org_id"), row.get("inv_name"), table, record_id, row
        )
        props.update(
            investment_amount=float_value(row.get("investment_amount")),
            investment_ratio=float_value(row.get("investment_ratio")),
        )
        return source, target, props
    if table == "dwd_org_merger_acquisition_info":
        source = ensure_org(
            buffer, row.get("acquiring_org_id"), row.get("acquiring_name"), table, record_id, row
        )
        target = ensure_org(
            buffer, row.get("acquired_org_id"), row.get("acquired_name"), table, record_id, row
        )
        props.update(
            ma_amount=float_value(row.get("ma_amount")),
            currency_code=text_value(row.get("currency_code")),
        )
        return source, target, props
    if table == "dwd_forg_subsidiary_info":
        source = target
        target = ensure_org(
            buffer,
            first_value(row, "affiliate", "affiliates_company_id"),
            row.get("affiliates_name"),
            table,
            record_id,
            row,
        )
        return source, target, props
    if table == "dwd_forg_beneficiary_info":
        source = ensure_person(
            buffer, row.get("bo_name"), table, record_id, row, person_kind="beneficial_owner"
        )
        props.update(
            direct_percent=float_value(row.get("direct_percent")),
            indirect_percent=float_value(row.get("indirect_percent")),
            total_percent=float_value(row.get("total_percent")),
        )
        return source, target, props
    if table == "dwd_forg_act_contro_info":
        entity_name = row.get("entity_name")
        if text_value(row.get("entity_type")).lower() in {
            "company",
            "organization",
            "机构",
            "企业",
        }:
            source = ensure_org(buffer, row.get("entity_eid"), entity_name, table, record_id, row)
        else:
            source = ensure_person(
                buffer, entity_name, table, record_id, row, person_kind="actual_controller"
            )
        props.update(
            direct_pct=float_value(first_value(row, "direct_pct_num", "direct_pct")),
            total_pct=float_value(first_value(row, "total_pct_num", "total_pct")),
        )
        return source, target, props
    raise ValueError(f"未实现关系表: {table}")


def event_raw_id(spec: TableSpec, row: dict[str, Any]) -> str:
    return stable_record_id(spec.name, row, spec.raw_id_fields)


def event_props(
    spec: TableSpec,
    row: dict[str, Any],
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
    )
    content = first_value(
        row,
        "content",
        "project_content",
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
    )
    currency = first_value(
        row,
        "currency",
        "currency_code",
        "funding_currency_code",
        "amount_unit",
        "total_amount_unit",
        "project_budget_amount_unit",
    )
    raw_id = event_raw_id(spec, row)
    return {
        "event_type": spec.event_type,
        "raw_id": raw_id,
        "title": text_value(title) or spec.cn_name,
        "content": text_value(content)
        or json_text({key: normalize_value(value) for key, value in row.items()}),
        "case_no": text_value(
            first_value(row, "case_no", "reg_no", "decision_no", "project_number")
        ),
        "case_cause": text_value(first_value(row, "case_cause", "case_type", "case_type_tag")),
        "occur_date": text_value(occur_date),
        "amount": float_value(amount),
        "currency": text_value(currency),
        "extra_json": json_text({key: normalize_value(value) for key, value in row.items()}),
        **provenance_props(spec.name, record_id, row, ingest_batch, ingest_time),
    }


def transform_row(spec: TableSpec, row: dict[str, Any], buffer: GraphBuffer) -> None:
    record_id = stable_record_id(spec.name, row, spec.raw_id_fields)
    buffer.source_counts[spec.name] += 1
    linked_vids: list[str] = []

    if spec.kind in {"org_base", "org_enrich"}:
        org_id = first_value(row, "org_id", "company_id")
        vid = ensure_org(
            buffer,
            org_id,
            first_value(row, "name_cn", "name_en", "org_loc_name", "company_name"),
            spec.name,
            record_id,
            row,
        )
        buffer.add_node(
            "Organization",
            vid,
            organization_props(spec.name, row, record_id, buffer.ingest_batch, buffer.ingest_time),
            overwrite_fields=(
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
                "description",
                "main_products",
            ),
        )
        linked_vids.append(vid)
        legal_rep = first_value(row, "lerep", "legal_person")
        if legal_rep:
            pvid = ensure_person(
                buffer, legal_rep, spec.name, record_id, row, person_kind="legal_representative"
            )
            buffer.add_edge(
                "LEGAL_REP_OF",
                pvid,
                vid,
                record_id,
                edge_provenance(spec.name, record_id, buffer.ingest_batch, buffer.ingest_time),
            )
            linked_vids.append(pvid)

    elif spec.kind == "relation":
        source, target, business_props = relation_endpoints(spec, row, record_id, buffer)
        business_props.update(
            edge_provenance(spec.name, record_id, buffer.ingest_batch, buffer.ingest_time)
        )
        business_props["extra_json"] = json_text(
            {key: normalize_value(value) for key, value in row.items()}
        )
        buffer.add_edge(spec.graph_target, source, target, record_id, business_props)
        linked_vids.extend((source, target))

    elif spec.kind == "news":
        org = ensure_org(buffer, row.get("org_id"), row.get("name_cn"), spec.name, record_id, row)
        news_id = bounded_vid(f"news_{spec.name}_{record_id}")
        buffer.add_node(
            "News",
            news_id,
            {
                "title": text_value(row.get("news_title")),
                "content": text_value(row.get("news_content")),
                "release_date": text_value(row.get("news_date")),
                "original_url": text_value(row.get("original_textlink")),
                "extra_json": json_text(
                    {key: normalize_value(value) for key, value in row.items()}
                ),
                **provenance_props(
                    spec.name, record_id, row, buffer.ingest_batch, buffer.ingest_time
                ),
            },
        )
        buffer.add_edge(
            "HAS_NEWS",
            org,
            news_id,
            record_id,
            edge_provenance(spec.name, record_id, buffer.ingest_batch, buffer.ingest_time),
        )
        linked_vids.extend((org, news_id))

    elif spec.kind in {"event", "bankruptcy_base", "bid_base"}:
        raw_id = event_raw_id(spec, row)
        evid = event_vid(spec.name, raw_id)
        buffer.add_node(
            "Event",
            evid,
            event_props(spec, row, record_id, buffer.ingest_batch, buffer.ingest_time),
        )
        linked_vids.append(evid)
        if spec.kind == "bankruptcy_base":
            if first_value(row, "admin_org_id", "admin_org"):
                org = ensure_org(
                    buffer, row.get("admin_org_id"), row.get("admin_org"), spec.name, record_id, row
                )
                buffer.add_edge(
                    "INVOLVED_IN",
                    org,
                    evid,
                    record_id,
                    {
                        **edge_provenance(
                            spec.name, record_id, buffer.ingest_batch, buffer.ingest_time
                        ),
                        "role": "bankruptcy_administrator",
                    },
                )
                linked_vids.append(org)
        elif spec.kind == "event":
            org = ensure_org(
                buffer,
                row.get("org_id"),
                first_value(row, "name_cn", "company_name", "taxpayer_name", "exec_person_name"),
                spec.name,
                record_id,
                row,
            )
            buffer.add_edge(
                "INVOLVED_IN",
                org,
                evid,
                record_id,
                {
                    **edge_provenance(
                        spec.name, record_id, buffer.ingest_batch, buffer.ingest_time
                    ),
                    "role": text_value(first_value(row, "case_role", "exec_person_type"))
                    or "subject",
                },
            )
            linked_vids.append(org)

    elif spec.kind == "bankruptcy_party":
        evid = event_vid("dwd_org_bankruptcy_public_cases", row.get("case_no"))
        org = ensure_org(buffer, row.get("org_id"), row.get("name_cn"), spec.name, record_id, row)
        buffer.add_edge(
            "INVOLVED_IN",
            org,
            evid,
            record_id,
            {
                **edge_provenance(spec.name, record_id, buffer.ingest_batch, buffer.ingest_time),
                "role": text_value(row.get("party_role_type")) or "bankruptcy_party",
                "extra_json": json_text(row),
            },
        )
        linked_vids.extend((org, evid))

    elif spec.kind == "bid_party":
        evid = event_vid("dwd_bid_base_out", row.get("u_id"))
        org = ensure_org(
            buffer,
            first_value(row, "org_id", "company_id"),
            first_value(row, "name_cn", "company_name"),
            spec.name,
            record_id,
            row,
        )
        role = "winner_candidate" if spec.name == "dwd_bid_win_candidate_out" else "purchase_agency"
        buffer.add_edge(
            "INVOLVED_IN",
            org,
            evid,
            record_id,
            {
                **edge_provenance(spec.name, record_id, buffer.ingest_batch, buffer.ingest_time),
                "role": role,
                "extra_json": json_text(row),
            },
        )
        linked_vids.extend((org, evid))

    elif spec.kind == "bid_content":
        evid = event_vid("dwd_bid_base_out", row.get("u_id"))
        buffer.add_node(
            "Event",
            evid,
            {
                "event_type": "bid",
                "raw_id": text_value(row.get("u_id")),
                "title": text_value(
                    first_value(row, "project_name", "target_item_name", "bid_item_name")
                ),
                "content": json_text({key: normalize_value(value) for key, value in row.items()}),
                **provenance_props(
                    spec.name, record_id, row, buffer.ingest_batch, buffer.ingest_time
                ),
            },
            overwrite_fields=("content",),
        )
        linked_vids.append(evid)
    else:
        raise ValueError(f"未实现表类型: {spec.kind}")

    add_datasource_links(buffer, spec, row, record_id, linked_vids)


def render_node_insert(tag: str, records: list[NodeRecord]) -> str:
    props = TAG_PROPERTIES[tag]
    values = []
    for record in records:
        literals = [
            ngql_literal(record.props.get(name), numeric=name in NUMERIC_TAG_PROPERTIES)
            for name in props
        ]
        values.append(f"{ngql_literal(record.vid)}:({','.join(literals)})")
    return (
        f"INSERT VERTEX `{tag}` ({','.join(f'`{name}`' for name in props)}) VALUES "
        + ",".join(values)
        + ";"
    )


def render_edge_insert(edge_type: str, records: list[EdgeRecord]) -> str:
    props = EDGE_PROPERTIES[edge_type]
    values = []
    for record in records:
        literals = [
            ngql_literal(record.props.get(name), numeric=name in NUMERIC_EDGE_PROPERTIES)
            for name in props
        ]
        values.append(
            f"{ngql_literal(record.source)}->{ngql_literal(record.target)}@{record.rank}:({','.join(literals)})"
        )
    return (
        f"INSERT EDGE `{edge_type}` ({','.join(f'`{name}`' for name in props)}) VALUES "
        + ",".join(values)
        + ";"
    )


def split_schema_statements(schema: str) -> list[str]:
    lines = [line for line in schema.splitlines() if not line.lstrip().startswith("--")]
    return [
        statement.strip() + ";" for statement in "\n".join(lines).split(";") if statement.strip()
    ]


def graph_client(space: str) -> TRSGraphClient:
    settings = TRSGraphSettings.from_env()
    settings.space = space
    return TRSGraphClient(settings)


def execute_with_retry(client: TRSGraphClient, statement: str, attempts: int = 4) -> None:
    for attempt in range(1, attempts + 1):
        try:
            client.execute_write(statement)
            return
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(attempt * 2)


def initialize_schema(space: str, *, propagation_wait: int = 8) -> None:
    if space != DEFAULT_SPACE:
        raise ValueError("安全限制：本 ETL 仅允许初始化 dev 图空间")
    client = graph_client(space)
    client.connect()
    try:
        for statement in split_schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
            execute_with_retry(client, statement)
        time.sleep(propagation_wait)
    finally:
        client.close()


def build_buffer(
    metadata: dict[str, dict[str, Any]],
    *,
    source_batch: str | None,
    ingest_batch: str,
    fetch_size: int,
) -> GraphBuffer:
    buffer = GraphBuffer(
        ingest_batch=ingest_batch,
        ingest_time=datetime.now().isoformat(timespec="seconds"),
    )
    with gkx_element_read_session() as session:
        for spec in TABLE_SPECS:
            columns = [item["COLUMN_NAME"] for item in metadata[spec.name]["columns"]]
            buffer.table_comments[spec.name] = metadata[spec.name]["comment"]
            for row in iter_table_rows(
                session,
                spec.name,
                columns,
                source_batch=source_batch,
                fetch_size=fetch_size,
            ):
                transform_row(spec, row, buffer)
    return buffer


def manifest_dict(buffer: GraphBuffer) -> dict[str, Any]:
    return {
        "source_system": SOURCE_SYSTEM,
        "ingest_batch": buffer.ingest_batch,
        "ingest_time": buffer.ingest_time,
        "source_counts": dict(sorted(buffer.source_counts.items())),
        "node_counts": {
            tag: sum(1 for key in buffer.nodes if key[0] == tag) for tag in TAG_PROPERTIES
        },
        "edge_counts": {
            edge_type: sum(1 for key in buffer.edges if key[0] == edge_type)
            for edge_type in EDGE_PROPERTIES
        },
        "nodes": [
            {"tag": record.tag, "vid": record.vid}
            for record in sorted(buffer.nodes.values(), key=lambda item: (item.tag, item.vid))
        ],
        "edges": [
            {
                "type": record.edge_type,
                "source": record.source,
                "target": record.target,
                "rank": record.rank,
            }
            for record in sorted(
                buffer.edges.values(),
                key=lambda item: (item.edge_type, item.source, item.target, item.rank),
            )
        ],
    }


def render_rollback(buffer: GraphBuffer, batch_size: int) -> str:
    statements: list[str] = [
        "-- 仅删除本 manifest 精确记录的边和节点；先边后点。",
        f"-- ingest_batch: {buffer.ingest_batch}",
    ]
    by_edge: dict[str, list[EdgeRecord]] = defaultdict(list)
    for edge in buffer.edges.values():
        by_edge[edge.edge_type].append(edge)
    for edge_type, records in sorted(by_edge.items()):
        for batch in chunked(records, batch_size):
            refs = ",".join(
                f"{ngql_literal(item.source)}->{ngql_literal(item.target)}@{item.rank}"
                for item in batch
            )
            statements.append(f"DELETE EDGE `{edge_type}` {refs};")
    vids = sorted({record.vid for record in buffer.nodes.values()})
    for batch in chunked(vids, batch_size):
        statements.append(
            "DELETE VERTEX " + ",".join(ngql_literal(vid) for vid in batch) + " WITH EDGE;"
        )
    return "\n".join(statements) + "\n"


def write_artifacts(buffer: GraphBuffer, output_dir: Path, batch_size: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_dict(buffer), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "rollback.ngql").write_text(render_rollback(buffer, batch_size), encoding="utf-8")
    inserts: list[str] = []
    for tag in TAG_PROPERTIES:
        records = sorted(
            (record for record in buffer.nodes.values() if record.tag == tag),
            key=lambda item: item.vid,
        )
        for batch in chunked(records, batch_size):
            inserts.append(render_node_insert(tag, batch))
    for edge_type in EDGE_PROPERTIES:
        records = sorted(
            (record for record in buffer.edges.values() if record.edge_type == edge_type),
            key=lambda item: (item.source, item.target, item.rank),
        )
        for batch in chunked(records, batch_size):
            inserts.append(render_edge_insert(edge_type, batch))
    (output_dir / "load.ngql").write_text("\n".join(inserts) + "\n", encoding="utf-8")


def load_buffer(buffer: GraphBuffer, space: str, batch_size: int) -> None:
    if space != DEFAULT_SPACE:
        raise ValueError("安全限制：本 ETL 仅允许写入 dev 图空间")
    client = graph_client(space)
    client.connect()
    try:
        for tag in TAG_PROPERTIES:
            records = [record for record in buffer.nodes.values() if record.tag == tag]
            for batch in chunked(records, batch_size):
                execute_with_retry(client, render_node_insert(tag, batch))
        for edge_type in EDGE_PROPERTIES:
            records = [record for record in buffer.edges.values() if record.edge_type == edge_type]
            for batch in chunked(records, batch_size):
                execute_with_retry(client, render_edge_insert(edge_type, batch))
    finally:
        client.close()


def graph_stats(space: str) -> dict[str, Any]:
    client = graph_client(space)
    client.connect()
    result: dict[str, Any] = {"space": space, "tags": {}, "edges": {}}
    try:
        for tag in TAG_PROPERTIES:
            response = client.execute_read(f"MATCH (v:`{tag}`) RETURN count(v) AS count;")
            result["tags"][tag] = (
                int(response.records[0].get("count", 0)) if response.records else 0
            )
        for edge_type in EDGE_PROPERTIES:
            response = client.execute_read(
                f"MATCH ()-[e:`{edge_type}`]->() RETURN count(e) AS count;"
            )
            result["edges"][edge_type] = (
                int(response.records[0].get("count", 0)) if response.records else 0
            )
    finally:
        client.close()
    return result


ORG_FIELD_MAP = {
    "org_id": "Organization.org_id（同时用于 VID：org_{org_id}）",
    "name_cn": "Organization.name_cn",
    "org_loc_name": "Organization.name_cn",
    "company_name": "Organization.name_cn",
    "n_company_name": "Organization.name_cn（name_cn 缺失时）",
    "traditional_name": "Organization.name_cn（name_cn 缺失时）",
    "name_alias": "Organization.name_cn（本地名称缺失时）",
    "name_en": "Organization.name_en",
    "en_name": "Organization.name_en",
    "external_id": "Organization.external_id",
    "company_code": "Organization.external_id",
    "school_code": "Organization.external_id（同时保留在 extra_json）",
    "province": "Organization.province",
    "city": "Organization.city",
    "area": "Organization.area",
    "country_code": "Organization.country_code",
    "country": "Organization.country",
    "address": "Organization.address",
    "company_address": "Organization.address",
    "postal_code": "Organization.postal_code",
    "phone": "Organization.phone",
    "email": "Organization.email",
    "lerep": "Organization.legal_rep；并创建 Person -[LEGAL_REP_OF]-> Organization",
    "legal_person": "Organization.legal_rep；并创建 Person -[LEGAL_REP_OF]-> Organization",
    "org_type": "Organization.org_type",
    "univ_type": "Organization.org_type",
    "company_type": "Organization.org_type",
    "person_num": "Organization.org_size",
    "incorporation_year": "Organization.founded_year（转 int）",
    "est_year": "Organization.founded_year（转 int）",
    "listing_status": "Organization.listing_status",
    "listed_status": "Organization.listing_status",
    "listing_date": "Organization.listed_date",
    "listed_date": "Organization.listed_date",
    "registered_capital_value": "Organization.registered_capital（去除单位后转 double）",
    "capital_num": "Organization.registered_capital（转 double）",
    "capital": "Organization.registered_capital（转 double）",
    "capital_currency": "Organization.capital_currency",
    "registered_capital_currency_code": "Organization.capital_currency",
    "currency_code": "Organization.capital_currency",
    "currency": "Organization.capital_currency",
    "industry": "Organization.industry_class",
    "industry_class": "Organization.industry_class",
    "stock_code": "Organization.stock_code",
    "stock_noun": "Organization.stock_noun",
    "stock_type": "Organization.stock_type",
    "main_activities": "Organization.description",
    "description": "Organization.description",
    "business_scope": "Organization.description",
    "main_products": "Organization.main_products",
    "main_prod": "Organization.main_products",
}

EVENT_FIELD_MAP = {
    "case_no": "Event.case_no；破产表中也作为跨表事件连接键",
    "case_cause": "Event.case_cause",
    "case_title": "Event.title",
    "title": "Event.title",
    "project_name": "Event.title",
    "job_title": "Event.title",
    "funding_round": "Event.title；同时保留在 Event.extra_json",
    "news_title": "News.title",
    "news_content": "News.content",
    "news_date": "News.release_date",
    "original_textlink": "News.original_url、News.source_url",
    "project_content": "Event.content",
    "job_description": "Event.content",
    "penalty_content": "Event.content",
    "violation_fact": "Event.content",
    "illegal_fact": "Event.content",
    "legal_obligation": "Event.content",
    "update_content": "Event.content",
    "publish_time": "Event.occur_date",
    "public_date": "Event.occur_date",
    "publish_date": "Event.occur_date",
    "penalty_date": "Event.occur_date",
    "procedure_date": "Event.occur_date",
    "completion_date": "Event.occur_date",
    "release_date": "Event.occur_date",
    "update_date": "Event.occur_date",
    "abn_date": "Event.occur_date",
    "filing_date": "Event.occur_date",
    "occur_period": "Event.occur_date",
    "year": "Event.occur_date",
    "amount": "Event.amount（转 double）",
    "funding_amount": "Event.amount（转 double）",
    "fine_amount": "Event.amount（转 double）",
    "total_amount": "Event.amount（转 double）",
    "project_budget_amount": "Event.amount（转 double）",
    "funding_currency_code": "Event.currency",
    "amount_unit": "Event.currency",
    "total_amount_unit": "Event.currency",
    "project_budget_amount_unit": "Event.currency",
}

RELATION_FIELD_MAP: dict[tuple[str, str], str] = {
    ("dwd_org_shareholder_info", "inv_org_id"): "SHAREHOLDER_OF 起点 Organization.org_id",
    (
        "dwd_org_shareholder_info",
        "owners_name",
    ): "SHAREHOLDER_OF 起点 Person.name_cn 或 Organization.name_cn",
    ("dwd_org_shareholder_info", "owners_type"): "判定股东节点为 Person 或 Organization",
    (
        "dwd_org_shareholder_info",
        "ownership_percentage",
    ): "SHAREHOLDER_OF.ownership_percentage（转 double）",
    (
        "dwd_forg_shareholder_info",
        "owners_name",
    ): "SHAREHOLDER_OF 起点名称；按企业后缀判定 Person/Organization",
    (
        "dwd_forg_shareholder_info",
        "ownership_percentage",
    ): "SHAREHOLDER_OF.ownership_percentage（转 double）",
    ("dwd_org_executive_info", "executives_name"): "EXECUTIVE_OF 起点 Person.name_cn",
    ("dwd_forg_executive_info", "executives_name"): "EXECUTIVE_OF 起点 Person.name_en/name_cn",
    ("dwd_org_executive_info", "executives_position"): "EXECUTIVE_OF.position",
    ("dwd_forg_executive_info", "executives_position"): "EXECUTIVE_OF.position",
    ("dwd_org_invest_info", "inv_org_id"): "INVESTS_IN 终点 Organization.org_id",
    ("dwd_org_invest_info", "inv_name"): "INVESTS_IN 终点 Organization.name_cn",
    ("dwd_org_invest_info", "investment_amount"): "INVESTS_IN.investment_amount（转 double）",
    ("dwd_org_invest_info", "investment_ratio"): "INVESTS_IN.investment_ratio（转 double）",
    ("dwd_org_merger_acquisition_info", "acquiring_org_id"): "ACQUIRES 起点 Organization.org_id",
    ("dwd_org_merger_acquisition_info", "acquiring_name"): "ACQUIRES 起点 Organization.name_cn",
    ("dwd_org_merger_acquisition_info", "acquired_org_id"): "ACQUIRES 终点 Organization.org_id",
    ("dwd_org_merger_acquisition_info", "acquired_name"): "ACQUIRES 终点 Organization.name_cn",
    ("dwd_org_merger_acquisition_info", "ma_amount"): "ACQUIRES.ma_amount（转 double）",
    ("dwd_org_merger_acquisition_info", "currency_code"): "ACQUIRES.currency_code",
    ("dwd_forg_subsidiary_info", "affiliate"): "SUBSIDIARY_OF 终点 Organization.org_id",
    (
        "dwd_forg_subsidiary_info",
        "affiliates_company_id",
    ): "SUBSIDIARY_OF 终点 Organization.external_id/备用标识",
    (
        "dwd_forg_subsidiary_info",
        "affiliates_name",
    ): "SUBSIDIARY_OF 终点 Organization.name_en/name_cn",
    ("dwd_forg_beneficiary_info", "bo_name"): "BENEFICIAL_OWNER_OF 起点 Person.name_en/name_cn",
    (
        "dwd_forg_beneficiary_info",
        "direct_percent",
    ): "BENEFICIAL_OWNER_OF.direct_percent（转 double）",
    (
        "dwd_forg_beneficiary_info",
        "indirect_percent",
    ): "BENEFICIAL_OWNER_OF.indirect_percent（转 double）",
    (
        "dwd_forg_beneficiary_info",
        "total_percent",
    ): "BENEFICIAL_OWNER_OF.total_percent（转 double）",
    ("dwd_forg_act_contro_info", "entity_eid"): "ACTUAL_CONTROLLER_OF 起点标识",
    (
        "dwd_forg_act_contro_info",
        "entity_name",
    ): "ACTUAL_CONTROLLER_OF 起点 Person/Organization 名称",
    ("dwd_forg_act_contro_info", "entity_type"): "判定控制人节点为 Person 或 Organization",
    ("dwd_forg_act_contro_info", "direct_pct"): "ACTUAL_CONTROLLER_OF.direct_pct（转 double）",
    (
        "dwd_forg_act_contro_info",
        "direct_pct_num",
    ): "ACTUAL_CONTROLLER_OF.direct_pct（数值字段优先）",
    ("dwd_forg_act_contro_info", "total_pct"): "ACTUAL_CONTROLLER_OF.total_pct（转 double）",
    ("dwd_forg_act_contro_info", "total_pct_num"): "ACTUAL_CONTROLLER_OF.total_pct（数值字段优先）",
}


def describe_field(spec: TableSpec, column: str) -> tuple[str, str]:
    if column == "data_source":
        return (
            "DataSource.source_table + DERIVED_FROM",
            "非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表",
        )
    if column in {"updated_time", "update_time"}:
        return (
            f"{spec.graph_target.split(' + ')[0]}.source_update_time / 边 extra_json",
            "统一转 ISO 字符串；关系表保留在 edge.extra_json",
        )
    if column in {"created_time", "create_time"}:
        return "目标节点/边 extra_json", "保留源值，不作为图写入时间；ingest_time 由 ETL 生成"
    relation = RELATION_FIELD_MAP.get((spec.name, column))
    if relation:
        return relation, "按字段语义写入端点或关系属性，同时保留在 extra_json"
    if spec.kind in {"org_base", "org_enrich"} and column in ORG_FIELD_MAP:
        return ORG_FIELD_MAP[column], "空值不覆盖已有非空属性；数值字段做容错转换"
    if spec.kind == "news" and column in EVENT_FIELD_MAP:
        return EVENT_FIELD_MAP[column], "资讯 VID 由表名和稳定记录键生成"
    if (
        spec.kind in {"event", "bankruptcy_base", "bid_base", "bid_content"}
        and column in EVENT_FIELD_MAP
    ):
        return EVENT_FIELD_MAP[column], "同时完整保留在 Event.extra_json/content JSON"
    if spec.kind == "bankruptcy_party":
        special = {
            "case_no": "Event.raw_id（连接 dwd_org_bankruptcy_public_cases）",
            "org_id": "INVOLVED_IN 起点 Organization.org_id",
            "name_cn": "INVOLVED_IN 起点 Organization.name_cn",
            "party_role_type": "INVOLVED_IN.role",
            "bankruptcy_party_id": "INVOLVED_IN.source_record_id / edge rank 输入",
        }
        if column in special:
            return special[column], "按破产案件号跨表关联"
    if spec.kind == "bid_party":
        special = {
            "u_id": "Event.raw_id（连接 dwd_bid_base_out）",
            "org_id": "INVOLVED_IN 起点 Organization.org_id",
            "company_id": "INVOLVED_IN 起点 Organization.org_id",
            "name_cn": "INVOLVED_IN 起点 Organization.name_cn",
            "company_name": "INVOLVED_IN 起点 Organization.name_cn",
            "ranking": "INVOLVED_IN.extra_json.ranking",
            "relate_type": "INVOLVED_IN.extra_json.relate_type",
        }
        if column in special:
            return special[column], "按 u_id 连接招投标 Event"
    if spec.kind == "bid_content" and column == "u_id":
        return (
            "Event.raw_id（连接 dwd_bid_base_out）",
            "同一事件 VID，标的物字段整体并入 Event.content JSON",
        )
    if spec.kind == "relation" and column == "org_id":
        return f"{spec.graph_target} 终点 Organization.org_id", "生成 org_{org_id}"
    if spec.kind in {"event", "news"} and column == "org_id":
        return "INVOLVED_IN/HAS_NEWS 起点 Organization.org_id", "生成 org_{org_id}"
    if spec.kind in {"event", "news"} and column in {"name_cn", "company_name", "taxpayer_name"}:
        return "关联 Organization.name_cn", "仅补全空属性，不覆盖已有机构主数据"
    if spec.kind in {"org_base", "org_enrich"}:
        return f"Organization.extra_json.{column}", "本体无独立属性，原样保留以避免信息丢失"
    if spec.kind == "news":
        return f"News.extra_json.{column}", "本体无独立属性，原样保留"
    if spec.kind in {"event", "bankruptcy_base", "bid_base", "bid_content"}:
        return (
            f"Event.extra_json.{column}",
            "本体无独立属性，原样保留；事件内容类表也进入 content JSON",
        )
    return f"{spec.graph_target}.extra_json.{column}", "本体无独立属性，原样保留在关系/节点 JSON"


def generate_mapping_markdown(metadata: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# 国内机构、国外机构要素库 → TRSGraph 图谱详细映射",
        "",
        f"> 本文档由 `{SOURCE_SYSTEM}` 当前数据库 `information_schema` 自动生成，覆盖 {len(TABLE_SPECS)} 张表及其每一个物理字段。",
        "",
        "## 一、统一建模约定",
        "",
        "- 国内与国外机构统一为 `Organization`，通过 `org_kind` 区分国内机构、高校、科研院所、港澳台企业和海外机构。",
        "- `Organization` VID 优先为 `org_{org_id}`；超过 dev 空间 `FIXED_STRING(64)` 限制时截断并附加 MD5。Person 按规范化姓名 MD5，Event 按表名与稳定业务键生成。",
        "- 全部节点写入 `source_system/source_table/source_record_id/ingest_batch/ingest_time/source_update_time`；源表全部字段还会进入 `extra_json`，因此未升格为本体属性的字段也不会丢失。",
        "- 物理 DWD 表建为 `DataSource`，业务节点通过 `SOURCED_FROM` 指向它；`data_source` 是真实上游表名时，创建 `原始 DataSource -[DERIVED_FROM]-> DWD DataSource`。",
        "- 关系方向：`Person/Organization -[LEGAL_REP_OF|SHAREHOLDER_OF|EXECUTIVE_OF|BENEFICIAL_OWNER_OF|ACTUAL_CONTROLLER_OF]-> Organization`；`Organization -[INVESTS_IN|ACQUIRES|SUBSIDIARY_OF]-> Organization`；`Organization -[HAS_NEWS]-> News`；`Organization -[INVOLVED_IN]-> Event`。",
        "- 幂等规则：节点 VID、边 rank 均确定性生成；同一源数据重复执行覆盖同一节点/同一条边，不产生重复结构。",
        "",
        "## 二、与旧 mapping.md 的名称校正",
        "",
        "- `dwd_org_reg_info` 以当前库实际表 `dwd_org_base_info` 为准。",
        "- `dwd_org_hels_info` 以当前库实际表 `dwd_org_heis_info` 为准。",
        "- 旧 `dwd_org_bid_info` 拆分为 `dwd_bid_base_out`、`dwd_bid_win_candidate_out`、`dwd_bid_purchase_agency_out`、`dwd_bid_target_item_out`。",
        "- `DERIVED_FROM` 方向以 ontology.md 为准：原始数据源指向加工后的要素数据源。",
        "",
        "## 三、逐表逐字段映射",
        "",
    ]
    for index, spec in enumerate(TABLE_SPECS, 1):
        item = metadata[spec.name]
        table_comment = item["comment"] or spec.cn_name
        library = "国外机构要素库" if spec.name.startswith("dwd_forg_") else "国内机构要素库"
        lines.extend(
            [
                f"### {index}. `{spec.name}` — {spec.cn_name}",
                "",
                f"- 所属领域：{library}",
                f"- 数据库表注释：{table_comment}",
                f"- 主图目标：`{spec.graph_target}`",
                "",
                "| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for column_item in item["columns"]:
            column = column_item["COLUMN_NAME"]
            target, rule = describe_field(spec, column)
            comment = text_value(column_item["COLUMN_COMMENT"]).replace("|", "\\|") or "—"
            lines.append(
                f"| `{column}` | `{column_item['COLUMN_TYPE']}` | {column_item['IS_NULLABLE']} | {comment} | {target} | {rule} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 四、运行与审计产物",
            "",
            "- `manifest.json`：源表行数、各类节点/边数量以及精确 VID/edge rank 清单。",
            "- `load.ngql`：本次批次完整 nGQL，可用于审阅和重放。",
            "- `rollback.ngql`：只删除 manifest 中列出的边和节点，按先边后点生成。",
            "- MySQL 连接在事务级设置为只读；图写入被代码限制为 `dev` 空间。",
            "",
        ]
    )
    return "\n".join(lines)


def load_metadata() -> dict[str, dict[str, Any]]:
    with gkx_element_read_session() as session:
        return get_table_metadata(session)


def default_ingest_batch(source_batch: str | None) -> str:
    if source_batch:
        return f"graph_{source_batch.lower()}"
    return "graph_full_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def output_dir_for(batch: str) -> Path:
    return OUTPUT_ROOT / re.sub(r"[^0-9A-Za-z_.-]+", "_", batch)


def command_init_schema(args: argparse.Namespace) -> None:
    initialize_schema(args.space)
    print(
        json.dumps(
            {"status": "ok", "space": args.space, "schema": str(SCHEMA_PATH)}, ensure_ascii=False
        )
    )


def command_generate_mapping(args: argparse.Namespace) -> None:
    metadata = load_metadata()
    content = generate_mapping_markdown(metadata)
    target = Path(args.output) if args.output else MAPPING_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    field_count = sum(len(item["columns"]) for item in metadata.values())
    print(
        json.dumps(
            {"status": "ok", "path": str(target), "tables": len(metadata), "fields": field_count},
            ensure_ascii=False,
        )
    )


def command_load(args: argparse.Namespace) -> None:
    if bool(args.source_batch) == bool(args.full):
        raise ValueError("必须且只能指定 --source-batch 或 --full")
    metadata = load_metadata()
    ingest_batch = args.ingest_batch or default_ingest_batch(args.source_batch)
    output_dir = Path(args.output_dir) if args.output_dir else output_dir_for(ingest_batch)
    buffer = build_buffer(
        metadata,
        source_batch=args.source_batch,
        ingest_batch=ingest_batch,
        fetch_size=args.fetch_size,
    )
    write_artifacts(buffer, output_dir, args.batch_size)
    if not args.dry_run:
        load_buffer(buffer, args.space, args.batch_size)
    summary = manifest_dict(buffer)
    summary.pop("nodes")
    summary.pop("edges")
    summary.update(
        status="dry-run" if args.dry_run else "loaded", space=args.space, output_dir=str(output_dir)
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_stats(args: argparse.Namespace) -> None:
    print(json.dumps(graph_stats(args.space), ensure_ascii=False, indent=2))


def command_rollback(args: argparse.Namespace) -> None:
    if args.space != DEFAULT_SPACE:
        raise ValueError("安全限制：仅允许回滚 dev 图空间")
    script = Path(args.script)
    if not script.is_file():
        raise FileNotFoundError(script)
    client = graph_client(args.space)
    client.connect()
    try:
        for statement in split_schema_statements(script.read_text(encoding="utf-8")):
            execute_with_retry(client, statement)
    finally:
        client.close()
    print(
        json.dumps(
            {"status": "rolled-back", "space": args.space, "script": str(script)},
            ensure_ascii=False,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser("init-schema", help="在 dev 创建本体 schema 与索引")
    schema_parser.add_argument("--space", default=DEFAULT_SPACE)
    schema_parser.set_defaults(func=command_init_schema)

    mapping_parser = subparsers.add_parser(
        "generate-mapping", help="从 live schema 生成逐字段映射文档"
    )
    mapping_parser.add_argument("--output")
    mapping_parser.set_defaults(func=command_generate_mapping)

    load_parser = subparsers.add_parser("load", help="读取 gkx_element 并批量写入 dev")
    load_parser.add_argument("--space", default=DEFAULT_SPACE)
    load_parser.add_argument("--source-batch")
    load_parser.add_argument("--full", action="store_true")
    load_parser.add_argument("--ingest-batch")
    load_parser.add_argument("--dry-run", action="store_true")
    load_parser.add_argument("--fetch-size", type=int, default=500)
    load_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    load_parser.add_argument("--output-dir")
    load_parser.set_defaults(func=command_load)

    stats_parser = subparsers.add_parser("stats", help="统计 dev 中本 ETL 的节点和边")
    stats_parser.add_argument("--space", default=DEFAULT_SPACE)
    stats_parser.set_defaults(func=command_stats)

    rollback_parser = subparsers.add_parser("rollback", help="执行指定批次生成的精确回滚脚本")
    rollback_parser.add_argument("--space", default=DEFAULT_SPACE)
    rollback_parser.add_argument("--script", required=True)
    rollback_parser.set_defaults(func=command_rollback)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
