"""datasource_entity 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.entity_extractors_one_entity.datasource_entity`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from kg_sdk import step

logger = logging.getLogger("datasource_entity")


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


VID_MAX_BYTES = 64


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def bounded_vid(value: str, max_bytes: int = VID_MAX_BYTES) -> str:
    """复刻旧 bounded_vid：超 64 字节截断并附加 md5 后缀。"""
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


def datasource_vid(table: str) -> str:
    return bounded_vid(f"ds_{table}")


@dataclass(frozen=True)
class OrgTableSpec:
    name: str
    cn_name: str
    scope: str  # domestic / foreign
    entity_tag: str | None  # Organization / Person / Event / News / None
    entity_kind: str
    raw_id_fields: tuple[str, ...] = ()


ORG_TABLE_SPECS: tuple[OrgTableSpec, ...] = (
    OrgTableSpec("dwd_org_base_info", "机构基本信息", "domestic", "Organization", "organization"),
    OrgTableSpec(
        "dwd_org_shareholder_info", "国内机构股东信息", "domestic", "Person", "shareholder"
    ),
    OrgTableSpec("dwd_org_executive_info", "国内机构高管信息", "domestic", "Person", "executive"),
    OrgTableSpec(
        "dwd_org_org_product_info",
        "国内机构经营信息",
        "domestic",
        "Organization",
        "organization_enrichment",
    ),
    OrgTableSpec(
        "dwd_org_annual_financial_info",
        "年报财务信息",
        "domestic",
        "Event",
        "annual_finance",
        ("org_id", "year"),
    ),
    OrgTableSpec("dwd_org_important_news_info", "重点资讯", "domestic", "News", "news"),
    OrgTableSpec(
        "dwd_org_changerecord_info",
        "工商变更",
        "domestic",
        "Event",
        "change_record",
        ("org_id", "update_date", "update_content"),
    ),
    OrgTableSpec("dwd_org_merger_acquisition_info", "并购事件", "domestic", None, "relation"),
    OrgTableSpec(
        "dwd_org_financing_info",
        "融资事件",
        "domestic",
        "Event",
        "financing",
        ("org_id", "completion_date", "funding_round"),
    ),
    OrgTableSpec("dwd_org_invest_info", "投资事件", "domestic", None, "relation"),
    OrgTableSpec(
        "dwd_org_recruit_info",
        "招聘信息",
        "domestic",
        "Event",
        "recruit",
        ("org_id", "release_date", "job_title"),
    ),
    OrgTableSpec("dwd_org_heis_info", "高校基本信息", "domestic", "Organization", "organization"),
    OrgTableSpec(
        "dwd_org_stock_base",
        "上市企业基本信息",
        "domestic",
        "Organization",
        "organization_enrichment",
    ),
    OrgTableSpec(
        "dwd_org_stock_finance_info",
        "上市企业财务信息",
        "domestic",
        "Event",
        "stock_finance",
        ("org_id", "occur_period"),
    ),
    OrgTableSpec(
        "dwd_org_company_abnormal", "经营异常", "domestic", "Event", "abnormal", ("abnormal_id",)
    ),
    OrgTableSpec(
        "dwd_org_company_punish", "行政处罚", "domestic", "Event", "punish", ("penalty_id",)
    ),
    OrgTableSpec("dwd_org_company_illegal", "严重违法", "domestic", "Event", "illegal", ("sv_id",)),
    OrgTableSpec(
        "dwd_org_risk_tax_punish", "税收违法", "domestic", "Event", "tax_punish", ("tax_vio_id",)
    ),
    OrgTableSpec(
        "dwd_org_opt_judicial_case", "司法案件", "domestic", "Event", "judicial_case", ("case_id",)
    ),
    OrgTableSpec(
        "dwd_org_risk_shixin", "失信被执行人", "domestic", "Event", "shixin", ("dishonest_id",)
    ),
    OrgTableSpec(
        "dwd_org_risk_zhixing", "被执行人", "domestic", "Event", "zhixing", ("exec_person_id",)
    ),
    OrgTableSpec(
        "dwd_org_bankruptcy_public_cases",
        "破产案件",
        "domestic",
        "Event",
        "bankruptcy",
        ("case_no",),
    ),
    OrgTableSpec(
        "dwd_org_bankruptcy_public_cases_list", "破产案件当事人", "domestic", None, "relation"
    ),
    OrgTableSpec(
        "dwd_special_hongkong_company", "香港企业", "domestic", "Organization", "organization"
    ),
    OrgTableSpec(
        "dwd_special_taiwan_company", "台湾企业", "domestic", "Organization", "organization"
    ),
    OrgTableSpec(
        "dwd_special_aomen_company", "澳门企业", "domestic", "Organization", "organization"
    ),
    OrgTableSpec("dwd_bid_base_out", "招投标公告", "domestic", "Event", "bid", ("u_id",)),
    OrgTableSpec("dwd_bid_win_candidate_out", "中标候选人", "domestic", None, "relation"),
    OrgTableSpec("dwd_bid_purchase_agency_out", "采购代理", "domestic", None, "relation"),
    OrgTableSpec(
        "dwd_bid_target_item_out",
        "招投标标的物",
        "domestic",
        "Event",
        "bid_item",
        ("u_id", "target_item_name", "bid_section_number"),
    ),
    OrgTableSpec(
        "dwd_research_institute_base_info",
        "科研机构基本信息",
        "domestic",
        "Organization",
        "organization",
    ),
    OrgTableSpec(
        "dwd_forg_base_info", "海外机构基本信息", "foreign", "Organization", "organization"
    ),
    OrgTableSpec("dwd_forg_shareholder_info", "海外机构股东信息", "foreign", None, "relation"),
    OrgTableSpec("dwd_forg_subsidiary_info", "海外机构子公司", "foreign", None, "relation"),
    OrgTableSpec("dwd_forg_executive_info", "海外机构高管信息", "foreign", "Person", "executive"),
    OrgTableSpec(
        "dwd_forg_product_info",
        "海外机构经营信息",
        "foreign",
        "Organization",
        "organization_enrichment",
    ),
    OrgTableSpec(
        "dwd_forg_beneficiary_info", "海外机构受益人", "foreign", "Person", "beneficial_owner"
    ),
    OrgTableSpec(
        "dwd_forg_act_contro_info", "海外机构实际控制人", "foreign", "Person", "actual_controller"
    ),
    OrgTableSpec(
        "dwd_forg_stock_fin_info",
        "海外上市企业财务信息",
        "foreign",
        "Event",
        "stock_finance",
        ("org_id", "occur_period"),
    ),
)


TABLE_CN_NAMES: dict[str, str] = {spec.name: spec.cn_name for spec in ORG_TABLE_SPECS}


def datasource_records() -> list[EntityRecord]:
    records: list[EntityRecord] = []
    for table, cn_name in sorted(TABLE_CN_NAMES.items()):
        library = (
            "国外机构要素库" if table.startswith(("dwd_forg_", "dwd_en_")) else "国内机构要素库"
        )
        records.append(
            EntityRecord(
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


assert len(TABLE_CN_NAMES) == 39


EntityBuilder = Callable[[str, Mapping[str, Any], str], Iterable[Any]]


def _record_id(row: Mapping[str, Any], pk_column: str | None) -> str:
    if pk_column and row.get(pk_column) is not None:
        return str(row[pk_column])
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"row:{digest[:16]}"


def _split_source(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    source = payload.get("source") or {}
    source_table = str(payload.get("source_table") or source.get("tableName") or "")
    table = source_table.rsplit(".", 1)[-1]
    pk_column = str(source.get("pkColumn") or "id")
    batch = f"se-{str(source.get('id') or 'x')[:8]}"
    return table, pk_column, batch


def _run(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None,
    mapper_by_table: dict[str, EntityBuilder] | None,
    to_json: Callable[[Any], dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    table, pk_column, batch = _split_source(payload)
    if builder is None and mapper_by_table:
        builder = mapper_by_table.get(table)
    if builder is None:
        raise RuntimeError(f"来源表 {table} 没有对应的转换 mapper")
    rows = payload.get("rows") or []
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in rows:
        record_id = _record_id(row, pk_column)
        try:
            mapped = list(builder(table, row, batch) or [])
            records.extend(to_json(r) for r in mapped)
        except Exception as exc:  # noqa: BLE001
            logger.warning("行转换失败 table=%s record=%s: %s", table, record_id, exc)
            failures.append({"recordId": record_id, "error": f"{type(exc).__name__}: {exc}"[:1000]})
    output: dict[str, Any] = {key: records, "failures": failures}
    if table:
        output["stats"] = {
            "table": table,
            "rows": len(rows),
            key: len(records),
            "failed": len(failures),
        }
    return output


def entity_transform(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None = None,
    mapper_by_table: dict[str, EntityBuilder] | None = None,
) -> dict[str, Any]:
    """实体转换：行 → ``{"id": vid, "props": properties}``。"""

    def to_json(record: Any) -> dict[str, Any]:
        return {"id": record.vid, "props": record.properties}

    return _run(
        payload, builder=builder, mapper_by_table=mapper_by_table, to_json=to_json, key="entities"
    )


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：静态目录 → {"entities": [...]}。"""
    return entity_transform(payload, builder=lambda table, row, batch: datasource_records())


@step("datasource_entity")
def emit(payload):
    return _transform(payload)
