"""机构域共享边抽取引擎（spec 驱动，复刻旧 organization_relation_etl.py）。

- 边属性：``_edge_props`` 旧口径（relation_confidence 动态打分 + 组织 ID 链 +
  bounded_json extra_json），属性集与顺序由 spec.edge_properties 决定。
- 端点：绝不建点，端点 VID 全部复用实体侧公式；person 端点用
  ``resolvers.person_vid_for_row``（实体侧统一公式，修复旧分叉）。
- 幂等：确定性 ``edge_rank``，nGQL ``INSERT EDGE @rank`` 覆盖更新。
- 虚拟/合成源行过滤与行级异常计 invalid，均沿用旧口径。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from script.entity_extractors_one_entity.common import (
    bounded_json,
    event_vid,
    is_virtual_source_row,
    news_vid,
    normalize_json,
    organization_id_from_row,
    organization_vid,
    person_vid,
    product_vid,
    relation_confidence,
    stable_record_id,
    text_or_none,
    to_float_or_none,
)
from script.relation_extractors_one_relation.catalog import RelationEdgeSpec
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    edge_rank,
    mysql_engine,
    now_utc,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import (
    ExactOrganizationResolver,
    organization_vid_from_row,
    person_vid_for_row,
)

_ORG_TYPES = {"机构", "企业", "公司", "organization", "company", "enterprise"}
_PERSON_TYPES = {"自然人", "个人", "person", "individual", "natural person"}


def edge_props(
    spec: RelationEdgeSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    business: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """旧 _edge_props：溯源六件套 + extra_json + 业务属性，按 spec 顺序输出。"""
    props: dict[str, Any] = {
        "organization_id": organization_id_from_row(row),
        "confidence": relation_confidence(row, source_table=spec.source_table),
        "source_table": spec.source_table,
        "source_record_id": record_id,
        "ingest_batch": ingest_batch,
        "ingest_time": now_utc(),
    }
    if "extra_json" in spec.edge_properties:
        props["extra_json"] = bounded_json(
            {key: normalize_json(value) for key, value in row.items()}
        )
    if business:
        props.update(business)
    return {name: props.get(name) for name in spec.edge_properties}


def candidate(
    spec: RelationEdgeSpec,
    source_vid: str,
    target_vid: str,
    record_id: str,
    properties: dict[str, Any],
    *,
    source_tag: str | None = None,
    target_tag: str | None = None,
) -> EdgeRecord:
    return EdgeRecord(
        edge_type=spec.edge_type,
        source_vid=source_vid,
        target_vid=target_vid,
        properties=properties,
        rank=edge_rank(spec.edge_type, source_vid, target_vid, record_id),
        source_tag=source_tag or spec.source_tags[0],
        target_tag=target_tag or spec.target_tag,
    )


def _org_endpoint(
    row: Mapping[str, Any],
    resolver: ExactOrganizationResolver,
    *,
    id_fields: Sequence[str],
    name_fields: Sequence[str],
) -> str:
    return organization_vid_from_row(row, resolver, id_fields=id_fields, name_fields=name_fields)


def extract_edge(
    spec: RelationEdgeSpec,
    row: Mapping[str, Any],
    record_id: str,
    ingest_batch: str,
    resolver: ExactOrganizationResolver,
) -> list[EdgeRecord]:
    """旧 extract_candidates（仅活跃 extractor；person 端点用实体侧统一公式）。"""
    extractor = spec.extractor

    if extractor == "legal_representative":
        legal_name = _first(row, "lerep", "legal_person")
        # 实体侧统一公式：机构 ID 链 org_id/company_id/entity_eid 参与哈希。
        org_key = _first(row, "org_id", "company_id", "entity_eid")
        source = person_vid("legal_representative", org_key, legal_name)
        target = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_cn", "company_name")
        )
        return [
            candidate(
                spec,
                source,
                target,
                record_id,
                edge_props(spec, row, record_id, ingest_batch),
                source_tag="Person",
            )
        ]

    if extractor == "domestic_shareholder":
        target = _org_endpoint(row, resolver, id_fields=("org_id",), name_fields=("name_cn",))
        owner_type = (text_or_none(row.get("owners_type")) or "").casefold()
        if text_or_none(row.get("inv_org_id")) is not None or owner_type in _ORG_TYPES:
            source = _org_endpoint(
                row,
                resolver,
                id_fields=("inv_org_id",),
                name_fields=("owners_name", "inv_name"),
            )
            source_tag = "Organization"
        elif owner_type in _PERSON_TYPES:
            # 实体侧统一公式（旧关系侧不带 birth/country 且缺 external_id 回退）。
            source = person_vid_for_row(row, "shareholder", "owners_name")
            source_tag = "Person"
        else:
            raise ValueError("shareholder endpoint type is not explicit")
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {"ownership_percentage": to_float_or_none(row.get("ownership_percentage"))},
        )
        return [candidate(spec, source, target, record_id, props, source_tag=source_tag)]

    if extractor == "foreign_shareholder":
        owner_org_id = resolver.resolve_exact(row.get("owners_name"))
        if owner_org_id is None:
            raise ValueError(
                "foreign shareholder type is unknown and is not an exact unique Organization"
            )
        source = organization_vid(owner_org_id)
        target = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_en", "name_cn")
        )
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {"ownership_percentage": to_float_or_none(row.get("ownership_percentage"))},
        )
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "executive":
        source = person_vid_for_row(row, "executive", "executives_name")
        target = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_cn", "name_en")
        )
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {"position": text_or_none(row.get("executives_position"))},
        )
        return [candidate(spec, source, target, record_id, props, source_tag="Person")]

    if extractor == "beneficial_owner":
        source = person_vid_for_row(row, "beneficial_owner", "bo_name")
        target = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_en", "name_cn")
        )
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {
                "direct_percent": to_float_or_none(row.get("direct_percent")),
                "indirect_percent": to_float_or_none(row.get("indirect_percent")),
                "total_percent": to_float_or_none(row.get("total_percent")),
            },
        )
        return [candidate(spec, source, target, record_id, props, source_tag="Person")]

    if extractor == "actual_controller":
        target = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_en", "name_cn")
        )
        entity_type = (text_or_none(row.get("entity_type")) or "").casefold()
        if entity_type in _ORG_TYPES:
            source = _org_endpoint(
                row,
                resolver,
                id_fields=("entity_eid",),
                name_fields=("entity_name",),
            )
            source_tag = "Organization"
        elif entity_type in _PERSON_TYPES:
            source = person_vid_for_row(row, "actual_controller", "entity_name")
            source_tag = "Person"
        else:
            exact_id = resolver.resolve_exact(row.get("entity_name"))
            if exact_id is None:
                raise ValueError(
                    "actual controller entity_type is unknown and name is not an exact Organization"
                )
            source = organization_vid(exact_id)
            source_tag = "Organization"
        if source == target:
            raise ValueError("actual controller resolves to target Organization itself")
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {
                "direct_pct": to_float_or_none(_first(row, "direct_pct_num", "direct_pct")),
                "total_pct": to_float_or_none(_first(row, "total_pct_num", "total_pct")),
            },
        )
        return [candidate(spec, source, target, record_id, props, source_tag=source_tag)]

    if extractor == "investment":
        source = _org_endpoint(row, resolver, id_fields=("org_id",), name_fields=("name_cn",))
        target = _org_endpoint(row, resolver, id_fields=("inv_org_id",), name_fields=("inv_name",))
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {
                "investment_amount": to_float_or_none(row.get("investment_amount")),
                "investment_ratio": to_float_or_none(row.get("investment_ratio")),
            },
        )
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "acquisition":
        source = _org_endpoint(
            row,
            resolver,
            id_fields=("acquiring_org_id",),
            name_fields=("acquiring_name",),
        )
        target = _org_endpoint(
            row,
            resolver,
            id_fields=("acquired_org_id",),
            name_fields=("acquired_name",),
        )
        props = edge_props(
            spec,
            row,
            record_id,
            ingest_batch,
            {
                "ma_amount": to_float_or_none(row.get("ma_amount")),
                "currency_code": text_or_none(row.get("currency_code")),
            },
        )
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "subsidiary":
        parent = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_en", "name_cn")
        )
        target_id = text_or_none(row.get("affiliate")) or text_or_none(
            row.get("affiliates_company_id")
        )
        if target_id is None:
            target_id = resolver.resolve_exact(row.get("affiliates_name"))
        if target_id is None:
            raise ValueError("subsidiary target has no stable or exact unique Organization id")
        subsidiary = _org_endpoint(
            row,
            resolver,
            id_fields=("affiliate", "affiliates_company_id"),
            name_fields=("affiliates_name",),
        )
        return [
            candidate(
                spec,
                subsidiary,
                parent,
                record_id,
                edge_props(spec, row, record_id, ingest_batch),
            )
        ]

    if extractor == "news":
        source = _org_endpoint(row, resolver, id_fields=("org_id",), name_fields=("name_cn",))
        target = news_vid(f"{spec.source_table}_{record_id}")
        return [
            candidate(
                spec, source, target, record_id, edge_props(spec, row, record_id, ingest_batch)
            )
        ]

    if extractor == "event":
        source = _org_endpoint(
            row,
            resolver,
            id_fields=("org_id",),
            name_fields=("name_cn", "company_name", "taxpayer_name", "exec_person_name"),
        )
        target = event_vid(spec.source_table, record_id)
        role = text_or_none(row.get("case_role") or row.get("exec_person_type")) or "subject"
        props = edge_props(spec, row, record_id, ingest_batch, {"role": role})
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "bankruptcy_party":
        source = _org_endpoint(
            row,
            resolver,
            id_fields=("org_id",),
            name_fields=("related_person_name", "name_cn"),
        )
        case_no = text_or_none(row.get("case_no"))
        if case_no is None:
            raise ValueError("bankruptcy party has no case_no")
        target = event_vid("dwd_org_bankruptcy_public_cases", case_no)
        role = text_or_none(row.get("party_role_type")) or "bankruptcy_party"
        props = edge_props(spec, row, record_id, ingest_batch, {"role": role})
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "bankruptcy_admin":
        source = _org_endpoint(
            row, resolver, id_fields=("admin_org_id",), name_fields=("admin_org",)
        )
        case_no = text_or_none(row.get("case_no"))
        if case_no is None:
            raise ValueError("bankruptcy case has no case_no")
        target = event_vid(spec.source_table, case_no)
        props = edge_props(spec, row, record_id, ingest_batch, {"role": "bankruptcy_administrator"})
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "bid_party":
        source = _org_endpoint(
            row,
            resolver,
            id_fields=("org_id", "company_id"),
            name_fields=("name_cn", "company_name"),
        )
        raw_id = text_or_none(row.get("u_id"))
        if raw_id is None:
            raise ValueError("bid party has no u_id")
        target = event_vid("dwd_bid_base_out", raw_id)
        role = (
            "winner_candidate"
            if spec.source_table == "dwd_bid_win_candidate_out"
            else "purchase_agency"
        )
        props = edge_props(spec, row, record_id, ingest_batch, {"role": role})
        return [candidate(spec, source, target, record_id, props)]

    if extractor == "organization_product":
        source = _org_endpoint(
            row, resolver, id_fields=("org_id",), name_fields=("name_cn", "name_en")
        )
        name = _first(row, "main_prod", "main_products")
        target = product_vid(name)
        return [
            candidate(
                spec, source, target, record_id, edge_props(spec, row, record_id, ingest_batch)
            )
        ]

    raise ValueError(f"unsupported extractor: {extractor}")


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if text_or_none(value) is not None:
            return value
    return None


def make_mapper(spec: RelationEdgeSpec, resolver: ExactOrganizationResolver):
    def mapper(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
        if is_virtual_source_row(row):
            return []
        record_id = stable_record_id(spec.source_table, row, spec.source_record_fields)
        return extract_edge(spec, row, record_id, batch, resolver)

    return mapper


def run_org_relation(
    key: str,
    *,
    database: str,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    ingest_batch: str | None,
    since: str | None,
    table: str | None = None,
) -> dict[str, Any]:
    """按 relation key 跑该组 spec（旧 --relation {key} 口径）。"""
    from script.relation_extractors_one_relation.catalog import SPECS_BY_KEY

    specs = SPECS_BY_KEY[key]
    if table:
        specs = tuple(spec for spec in specs if spec.source_table == table)
    engine = mysql_engine(database)
    resolver = ExactOrganizationResolver.load(engine, database)
    sources = [
        (
            spec.source_table,
            f"SELECT * FROM {spec.source_table} ORDER BY 1",
            make_mapper(spec, resolver),
        )
        for spec in specs
    ]
    return run_relation_extractor(
        database=database,
        batch_size=batch_size,
        limit=limit,
        dry_run=dry_run,
        ingest_batch=ingest_batch,
        since=since,
        sources=sources,
    )


def org_relation_cli(key: str) -> None:
    """机构域边脚本共用 CLI 入口（--table 限定该 key 下的源表）。"""
    from script.relation_extractors_one_relation.catalog import SPECS_BY_KEY
    from script.relation_extractors_one_relation.common import (
        build_parser,
        configure_logging,
        print_json,
    )

    tables = [spec.source_table for spec in SPECS_BY_KEY[key]]
    parser = build_parser(f"One-relation extractor: {key}")
    parser.add_argument("--table", choices=("all", *tables), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    print_json(
        run_org_relation(
            key,
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            table=None if args.table == "all" else args.table,
        )
    )


def org_relation_sources(key: str) -> list[dict[str, Any]]:
    """该 relation key 下全部源表的来源绑定元数据（register_platform_extraction 用）。"""
    from script.relation_extractors_one_relation.catalog import SPECS_BY_KEY

    return [
        {"table": spec.source_table, "pk": "id", "time": "update_time"}
        for spec in SPECS_BY_KEY[key]
    ]


def transform_org_relation(key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：机构域边按 spec 驱动转换，只输出边 JSON。

    resolver 每批从平台注入的 mysql ctx 构建一次（7 张机构表名称索引）；
    端点不验存/不建点（实体侧脚本负责），逐行失败进 failures。
    """
    from script.extract_transform_common import edge_transform
    from script.relation_extractors_one_relation.catalog import SPECS_BY_KEY
    from script.relation_extractors_one_relation.common import mysql_engine
    from script.relation_extractors_one_relation.resolvers import ExactOrganizationResolver

    database = (payload.get("source") or {}).get("databaseName") or "gkx_element"
    engine = mysql_engine(database)
    try:
        resolver = ExactOrganizationResolver.load(engine, database)
    finally:
        engine.dispose()
    specs = {spec.source_table: spec for spec in SPECS_BY_KEY[key]}

    def builder(table: str, row: Mapping[str, Any], batch: str) -> list[Any]:
        spec = specs.get(table)
        if spec is None:
            return []
        if is_virtual_source_row(row):
            return []
        record_id = stable_record_id(spec.source_table, row, spec.source_record_fields)
        return extract_edge(spec, row, record_id, batch, resolver)

    return edge_transform(payload, builder=builder)
