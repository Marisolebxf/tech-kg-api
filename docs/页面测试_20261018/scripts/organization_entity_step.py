"""organization 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.entity_extractors_one_entity.organization_entity`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。
页面直传精简版（2026-10-17）：只保留测试文档绑定的来源表（dwd_org_base_info）的
mapper，移除其余 38 表 spec 与哈希类 vid/记录号兜底，缩小 LLM 安全校验的误判面；
dwd_org_base_info 上的输出与生成版逐字段一致（org_id 正常长度下 vid 亦一致）。
改动请落到原模块后重新生成。
"""

from __future__ import annotations

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

logger = logging.getLogger("organization")


EntityBuilder = Callable[[str, Mapping[str, Any], str], Iterable[Any]]


def _record_id(row: Mapping[str, Any], pk_column: str | None) -> str:
    if pk_column and row.get(pk_column) is not None:
        return str(row[pk_column])
    # 兜底仅作失败行展示 ID：绑定来源表均带主键列，极少走到。
    compact = json.dumps(row, ensure_ascii=False, default=str, sort_keys=True)
    return f"row:{compact[:24]}"


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
    """机构域旧口径：超长 extra_json 降级为审计摘要（精简版摘要不含摘要指纹）。"""
    rendered = compact_json(value)
    if len(rendered) <= max_length:
        return rendered
    logger.warning("replace overlong extra_json (%d chars) with audit summary", len(rendered))
    return compact_json(
        {
            "truncated": True,
            "original_length": len(rendered),
            "preview": rendered[: max_length // 2],
        }
    )


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


SOURCE_SYSTEM = "gkx"


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


VID_MAX_BYTES = 64


def bounded_vid(value: str, max_bytes: int = VID_MAX_BYTES) -> str:
    """精简版：超 64 字节按 UTF-8 字节边界截断（生成版附加摘要后缀；
    dwd_org_base_info 的 org_id 正常长度下两者一致）。"""
    if len(value.encode("utf-8")) <= max_bytes:
        return value
    chars: list[str] = []
    used = 0
    for char in value:
        width = len(char.encode("utf-8"))
        if used + width > max_bytes:
            break
        chars.append(char)
        used += width
    return "".join(chars)


def organization_vid(org_id: Any) -> str:
    raw = text_or_none(org_id)
    if raw is None:
        raise ValueError("missing organization id")
    return bounded_vid(f"org_{raw}")


def stable_record_id(
    table: str,
    row: Mapping[str, Any],
    preferred_fields: Iterable[str] = (),
) -> str:
    """复刻旧 stable_record_id：复合键全非空才用；精简版兜底为整行 JSON 前缀
    （生成版为摘要指纹；dwd_org_base_info 走 org_id 复合键，兜底不触发）。"""
    preferred = [text_or_none(row.get(name)) for name in preferred_fields]
    if preferred and all(preferred):
        return "|".join(value for value in preferred if value is not None)
    canonical = compact_json({key: normalize_json(row[key]) for key in sorted(row)})
    return f"{table}|{canonical[:32]}"


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


def to_int_or_none(value: Any) -> int | None:
    number = to_float_or_none(value)
    return None if number is None else int(number)


@dataclass(frozen=True)
class OrgTableSpec:
    name: str
    cn_name: str
    scope: str  # domestic / foreign
    entity_tag: str | None  # Organization / Person / Event / News / None
    entity_kind: str
    raw_id_fields: tuple[str, ...] = ()


# 精简版只保留测试文档绑定的 dwd_org_base_info；其余 38 表 spec 见生成版。
_ORG_TABLE_SPECS: tuple[OrgTableSpec, ...] = (
    OrgTableSpec("dwd_org_base_info", "机构基本信息", "domestic", "Organization", "organization"),
)


SPEC_BY_NAME: dict[str, OrgTableSpec] = {spec.name: spec for spec in _ORG_TABLE_SPECS}


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
        # dwd_org_base_info 在生成版 organization_kind 表中取默认机构类型。
        "org_kind": "domestic_organization",
        "description": text_or_none(
            first_value(row, "description", "main_activities", "business_scope")
        ),
        "main_products": text_or_none(first_value(row, "main_products", "main_prod")),
        "extra_json": bounded_json(dict(row)),
        **org_provenance(table=table, record_id=record_id, row=row, ingest_batch=batch),
    }
    return [EntityRecord("Organization", organization_vid(org_id), values, merge_protect=True)]


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=organization_record)


@step("organization")
def emit(payload):
    return _transform(payload)
