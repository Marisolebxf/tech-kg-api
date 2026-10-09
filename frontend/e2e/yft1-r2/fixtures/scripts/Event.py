"""event_entity 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.entity_extractors_one_entity.event_entity`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from kg_sdk import step

logger = logging.getLogger("event_entity")


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


MAX_EXTRA_JSON_LENGTH = 64_000


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


def bounded_json(value: Any, *, max_length: int = MAX_EXTRA_JSON_LENGTH) -> str:
    """机构域旧口径：超长 extra_json 降级为审计摘要。"""
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


def event_vid(table: str, record_id: str) -> str:
    return bounded_vid(f"event_{table}_{record_id}")


MAX_TEXT_LENGTH = 20_000


def text_or_none(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    """机构域旧口径（organization_etl_common.clean_text）：strip + 截断，空白返回 None。"""
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


def first_value(row: Mapping[str, Any], *names: str) -> Any:
    """机构域旧口径的候选链：返回首个非空白原始值。"""
    for name in names:
        value = row.get(name)
        if text_or_none(value) is not None:
            return value
    return None


VIRTUAL_SOURCE_FIELDS: tuple[str, ...] = ("data_source", "source_system")


VIRTUAL_SOURCE_MARKERS: tuple[str, ...] = ("mock", "stub", "virtual", "placeholder", "test")


def is_virtual_source_row(row: Mapping[str, Any]) -> bool:
    """复刻旧 is_virtual_source_row：显式标注的合成源行不建点。"""
    for field_name in VIRTUAL_SOURCE_FIELDS:
        value = text_or_none(row.get(field_name))
        if value is None:
            continue
        normalized = value.casefold().replace("-", "_")
        for marker in VIRTUAL_SOURCE_MARKERS:
            if (
                normalized == marker
                or normalized.startswith(marker + "_")
                or normalized.endswith("_" + marker)
                or ("_" + marker + "_") in normalized
            ):
                return True
    return False


SOURCE_SYSTEM = "gkx_element"


ORGANIZATION_ID_FIELDS: tuple[str, ...] = (
    "organization_id",
    "org_id",
    "company_id",
    "entity_eid",
    "acquiring_org_id",
    "admin_org_id",
    "antitypic",
)


def organization_id_from_row(row: Mapping[str, Any]) -> str | None:
    for field_name in ORGANIZATION_ID_FIELDS:
        value = text_or_none(row.get(field_name))
        if value is not None:
            return value
    return None


def entity_confidence(row: Mapping[str, Any], *, source_table: str) -> float:
    """复刻旧 entity_confidence：DWD 溯源 0.40 + 稳定 ID + 展示身份 + 业务属性。"""
    score = 0.40 if source_table.startswith("dwd_") else 0.30
    if organization_id_from_row(row) is not None:
        score += 0.20
    if any(text_or_none(row.get(name)) is not None for name in ("external_id", "credit_no")):
        score += 0.10
    if any(
        text_or_none(row.get(name)) is not None
        for name in (
            "name_cn",
            "name_en",
            "company_name",
            "org_loc_name",
            "executives_name",
            "bo_name",
            "entity_name",
            "news_title",
            "title",
            "job_title",
            "target_item_name",
            "main_prod",
            "main_products",
        )
    ):
        score += 0.20
    if any(
        text_or_none(row.get(name)) is not None
        for name in ("country_code", "country", "province", "city", "address", "updated_time")
    ):
        score += 0.10
    return round(min(max(score, 0.0), 1.0), 4)


def org_provenance(
    *,
    table: str,
    record_id: str,
    row: Mapping[str, Any],
    ingest_batch: str,
) -> dict[str, Any]:
    """机构域旧口径溯源（node_provenance）：动态置信度 + 多候选 URL/更新时间。"""
    return {
        "organization_id": organization_id_from_row(row),
        "confidence": entity_confidence(row, source_table=table),
        "source_system": SOURCE_SYSTEM,
        "source_table": table,
        "source_record_id": record_id,
        "source_url": text_or_none(
            row.get("source_url")
            or row.get("original_link")
            or row.get("original_textlink")
            or row.get("web_link")
        ),
        "ingest_batch": ingest_batch,
        "ingest_time": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_update_time": text_or_none(row.get("updated_time") or row.get("update_time")),
    }


def stable_record_id(
    table: str,
    row: Mapping[str, Any],
    preferred_fields: Iterable[str] = (),
) -> str:
    """复刻旧 stable_record_id：复合键全非空才用，否则整行 JSON md5 兜底。"""
    preferred = [text_or_none(row.get(name)) for name in preferred_fields]
    if preferred and all(preferred):
        return "|".join(value for value in preferred if value is not None)
    canonical = compact_json({key: normalize_json(row[key]) for key in sorted(row)})
    return md5_hex(f"{table}|{canonical}")


def to_float_or_none(value: Any) -> float | None:
    """机构域旧口径（organization_etl_common.to_float）：非法值返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if isinstance(value, (int, float, Decimal)):
            return float(value)
        raw = text_or_none(value)
        if raw is None or raw.casefold() in {"-", "n/a", "n.a.", "null", "none"}:
            return None
        normalized = re.sub(r"[^0-9eE.+-]", "", raw.replace(",", "").replace("%", ""))
        return float(Decimal(normalized)) if normalized else None
    except (InvalidOperation, TypeError, ValueError):
        return None


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


SPEC_BY_NAME: dict[str, OrgTableSpec] = {spec.name: spec for spec in ORG_TABLE_SPECS}


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


TABLE_CN_NAMES: dict[str, str] = {spec.name: spec.cn_name for spec in ORG_TABLE_SPECS}


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
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=event_record)


@step("event_entity")
def emit(payload):
    return _transform(payload)
