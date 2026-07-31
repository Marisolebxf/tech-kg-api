"""Load Organization and DataSource vertices from gkx_element into TRSGraph ``dev``.

This is the only organization-domain vertex loader.  It never creates graph
edges or overwrites an existing VID.  Organization relations are owned exclusively by
``script.organization_relation_etl``.

Examples:

    python -m script.organization_entity_etl load --full --dry-run
    python -m script.organization_entity_etl load --table dwd_org_base_info --full --write
    python -m script.organization_entity_etl init-schema
"""

from __future__ import annotations

import argparse
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
from script.organization_etl_common import (
    DEFAULT_SPACE,
    RELATION_SPECS,
    SCHEMA_PATH,
    RelationDataError,
    bounded_json,
    chunks,
    clean_text,
    datasource_vid,
    exclusive_etl_lock,
    ngql_identifier,
    ngql_literal,
    node_provenance,
    organization_vid,
    stable_record_id,
    to_float,
    to_int,
)

logger = logging.getLogger("script.organization_entity_etl")

DEFAULT_BATCH_SIZE = 100

ORGANIZATION_PROPERTIES: tuple[str, ...] = (
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
)
ORGANIZATION_NUMERIC_PROPERTIES = frozenset({"founded_year", "registered_capital"})
DATASOURCE_PROPERTIES: tuple[str, ...] = ("source_table", "table_cn_name", "tier", "library")


@dataclass(frozen=True)
class EntityTableSpec:
    """One source table that can update an Organization vertex."""

    name: str
    cn_name: str
    org_kind: str
    mode: str = "base"


ENTITY_TABLE_SPECS: tuple[EntityTableSpec, ...] = (
    EntityTableSpec("dwd_org_base_info", "机构基本信息", "domestic_organization"),
    EntityTableSpec("dwd_org_heis_info", "高校基本信息", "domestic_university"),
    EntityTableSpec(
        "dwd_research_institute_base_info",
        "科研机构基本信息",
        "domestic_research_institute",
    ),
    EntityTableSpec("dwd_special_hongkong_company", "香港企业", "hong_kong_company"),
    EntityTableSpec("dwd_special_taiwan_company", "台湾企业", "taiwan_company"),
    EntityTableSpec("dwd_special_aomen_company", "澳门企业", "macao_company"),
    EntityTableSpec("dwd_forg_base_info", "海外机构基本信息", "foreign_organization"),
    EntityTableSpec(
        "dwd_org_org_product_info",
        "国内机构经营信息",
        "domestic_organization",
        "enrichment",
    ),
    EntityTableSpec(
        "dwd_org_stock_base",
        "上市企业基本信息",
        "domestic_organization",
        "enrichment",
    ),
    EntityTableSpec(
        "dwd_forg_product_info",
        "海外机构经营信息",
        "foreign_organization",
        "enrichment",
    ),
)
ENTITY_TABLE_BY_NAME = {spec.name: spec for spec in ENTITY_TABLE_SPECS}

TABLE_CN_NAMES: dict[str, str] = {spec.name: spec.cn_name for spec in ENTITY_TABLE_SPECS}
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
        "dwd_zh_project": "国内项目",
        "dwd_en_project": "国外项目",
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
        "dwd_industry_chain_node_org": "产业链机构",
        "dwd_industry_chain_antitypic_org": "产业链典型机构",
    }
)
for _relation_spec in RELATION_SPECS:
    TABLE_CN_NAMES.setdefault(_relation_spec.source_table, _relation_spec.source_table)


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


def organization_properties(
    spec: EntityTableSpec,
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
        "org_kind": spec.org_kind,
        "description": clean_text(
            first_value(row, "description", "main_activities", "business_scope")
        ),
        "main_products": clean_text(first_value(row, "main_products", "main_prod")),
        "extra_json": bounded_json(dict(row)),
        **node_provenance(spec.name, record_id, row, ingest_batch, ingest_time),
    }
    if spec.mode == "enrichment":
        # Enrichment rows update only fields they actually carry.  This prevents
        # a sparse product/stock row from replacing base attributes with NULL.
        return {name: value for name, value in values.items() if value is not None}
    return values


def vertex_from_row(
    spec: EntityTableSpec,
    row: Mapping[str, Any],
    ingest_batch: str,
    ingest_time: str,
) -> VertexRecord:
    record_id = stable_record_id(spec.name, row, ("org_id",))
    properties = organization_properties(spec, row, record_id, ingest_batch, ingest_time)
    return VertexRecord("Organization", organization_vid(properties["org_id"]), properties)


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
    allowed = ORGANIZATION_PROPERTIES if tag == "Organization" else DATASOURCE_PROPERTIES
    properties = tuple(name for name in allowed if name in records[0].properties)
    if any(
        tuple(name for name in allowed if name in record.properties) != properties
        for record in records
    ):
        raise ValueError("one INSERT VERTEX batch must have one property signature")
    numeric = ORGANIZATION_NUMERIC_PROPERTIES if tag == "Organization" else frozenset()
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
    spec: EntityTableSpec,
    *,
    max_records: int | None,
) -> Iterator[dict[str, Any]]:
    columns = source_columns(session, spec.name)
    if not columns:
        raise RuntimeError(f"source table does not exist: {spec.name}")
    query = f"SELECT * FROM `{spec.name}`"
    params: dict[str, Any] = {}
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


def initialize_schema(graph: TRSGraphClient | None = None) -> None:
    client = graph or get_trs_graph_client()
    for statement in split_schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
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


def _write_vertex_batches(
    records: Sequence[VertexRecord],
    *,
    graph: TRSGraphClient | None,
    batch_size: int,
    dry_run: bool,
    stats: EntityStats,
) -> None:
    grouped: dict[tuple[str, tuple[str, ...]], list[VertexRecord]] = defaultdict(list)
    for record in records:
        allowed = ORGANIZATION_PROPERTIES if record.tag == "Organization" else DATASOURCE_PROPERTIES
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
            existing = existing_vids(
                graph,
                batch[0].tag,
                [record.vid for record in batch],
            )
            stats.existing += len(existing)
            stats.skipped += len(existing)
            pending = [record for record in batch if record.vid not in existing]
            if not pending:
                continue
            statement = render_vertex_insert(pending)
            if len(stats.examples) < 3:
                stats.examples.append(statement[:1_000])
            try:
                graph.execute_write(statement)
                stats.written += len(pending)
            except Exception:
                stats.failed += len(pending)
                logger.exception("organization vertex batch failed statement=%s", statement[:500])


def run_etl(
    *,
    table: str = "all",
    full: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_records: int | None = None,
    dry_run: bool = True,
    ingest_batch: str | None = None,
    graph: TRSGraphClient | None = None,
    session: Session | None = None,
) -> dict[str, EntityStats]:
    """Load only Organization and DataSource vertices; never create an edge."""
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
    specs = ENTITY_TABLE_SPECS if table == "all" else (ENTITY_TABLE_BY_NAME[table],)

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
            ):
                stats.queried += 1
                try:
                    record = vertex_from_row(spec, row, ingest_batch, ingest_time)
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
                stats.valid += 1
                pending.append(record)
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
        return results
    finally:
        if owns_session and session_cm is not None:
            session_cm.__exit__(None, None, None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser("init-schema")
    schema_parser.add_argument("--space", choices=(DEFAULT_SPACE,), default=DEFAULT_SPACE)

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
    load_parser.add_argument("--ingest-batch")
    load_parser.add_argument("--space", choices=(DEFAULT_SPACE,), default=DEFAULT_SPACE)
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
            ingest_batch=ingest_batch,
        )
    summary = {table: asdict(stats) for table, stats in results.items()}
    logger.info("organization entity ETL summary=%s", summary)
    return 1 if any(item.failed for item in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
