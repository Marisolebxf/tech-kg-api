"""executive_of 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.relation_extractors_one_relation.executive_of_relation`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from kg_sdk import step
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("executive_of")


VIRTUAL_SOURCE_FIELDS: tuple[str, ...] = ("data_source", "source_system")


VIRTUAL_SOURCE_MARKERS: tuple[str, ...] = ("mock", "stub", "virtual", "placeholder", "test")


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


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


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


def edge_transform(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None = None,
    mapper_by_table: dict[str, EntityBuilder] | None = None,
) -> dict[str, Any]:
    """关系转换：行 → ``{"fromId", "toId", "props"}``。"""

    def to_json(record: Any) -> dict[str, Any]:
        return {
            "fromId": record.source_vid,
            "toId": record.target_vid,
            "props": record.properties,
        }

    return _run(
        payload, builder=builder, mapper_by_table=mapper_by_table, to_json=to_json, key="edges"
    )


@dataclass(frozen=True)
class RelationEdgeSpec:
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
    source_tags: tuple[str, ...] = ("Organization",)


SPECS_BY_KEY: dict[str, tuple[RelationEdgeSpec, ...]] = {}


DEFAULT_DB = "gkx_element"


def _sdk_context():
    """任务运行时注入的 kg_sdk 上下文；CLI 独立运行 / 未注入时返回 None。"""
    try:
        from kg_sdk import current_context

        return current_context()
    except ImportError:
        return None


def mysql_engine(database: str = "") -> Any:
    """平台注入版：任务所选数据源的 engine（database 形参保留以兼容旧签名）。"""
    from kg_sdk import current_context

    ctx = current_context()
    client = getattr(ctx, "mysql", None) if ctx is not None else None
    if client is None:
        raise RuntimeError(
            "本抽取脚本需要平台注入 MySQL 数据源（任务/Schema 抽取请在触发时选择数据源配置）"
        )
    return client.engine


VID_MAX_BYTES = 64


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


def news_vid(record_id: str) -> str:
    raw = text_or_none(record_id)
    if raw is None:
        raise ValueError("missing news record id")
    return bounded_vid(f"news_{raw}")


def organization_vid(org_id: Any) -> str:
    raw = text_or_none(org_id)
    if raw is None:
        raise ValueError("missing organization id")
    return bounded_vid(f"org_{raw}")


def person_vid(person_kind: str, *identity_values: Any) -> str:
    """复刻旧 person_vid：kind|org_id|name|birth_date|country 各分量 NFKC+casefold。"""
    normalized = [
        unicodedata.normalize("NFKC", value).casefold()
        for raw in identity_values
        if (value := text_or_none(raw)) is not None
    ]
    if not normalized:
        raise ValueError("missing stable person identity")
    identity = "|".join((person_kind, *normalized))
    return bounded_vid(f"person_{md5_hex(identity)}")


def product_vid(name: Any) -> str:
    """复刻旧 product_vid：规范化产品名完整 32 位 md5。"""
    raw = text_or_none(name)
    if raw is None:
        raise ValueError("missing product name")
    normalized = unicodedata.normalize("NFKC", raw).casefold()
    return bounded_vid(f"product_{md5_hex(normalized)}")


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
class EdgeRecord:
    edge_type: str
    source_vid: str
    target_vid: str
    properties: dict[str, Any]
    # nGQL 确定性 rank 模式；None 走 REST merge 模式。
    rank: int | None = None
    # REST merge 的 identityProps；缺省取 properties["source_record_id"]。
    identity: dict[str, Any] | None = field(default=None, compare=False)
    # 端点验存用的 tag；None 表示该端点不验存。
    source_tag: str | None = None
    target_tag: str | None = None
    # False 表示允许悬空端点（机构名桩 / DOI 桩等旧口径）。
    validate_endpoints: bool = True


_ORG_TYPES = {"机构", "企业", "公司", "organization", "company", "enterprise"}


_PERSON_TYPES = {"自然人", "个人", "person", "individual", "natural person"}


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if text_or_none(value) is not None:
            return value
    return None


class ExactOrganizationResolver:
    """名称仅在精确匹配且唯一时解析为机构 ID（旧口径）。"""

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
    def load(cls, engine: Engine, database: str = "gkx_element") -> ExactOrganizationResolver:
        by_name: dict[str, set[str]] = defaultdict(set)
        with engine.connect() as conn:
            for table, id_column, name_columns in cls._SOURCES:
                columns = (id_column, *name_columns)
                select = ",".join(f"`{name}`" for name in columns)
                rows = conn.execute(text(f"SELECT {select} FROM `{table}`")).mappings()
                for row in rows:
                    org_id = text_or_none(row.get(id_column))
                    if org_id is None:
                        continue
                    for name_column in name_columns:
                        name = text_or_none(row.get(name_column))
                        if name is not None:
                            by_name[name].add(org_id)
        return cls(by_name)

    def resolve_exact(self, name: Any) -> str | None:
        key = text_or_none(name)
        if key is None:
            return None
        candidates = self._by_name.get(key, set())
        if len(candidates) != 1:
            return None
        return next(iter(candidates))

    resolve = resolve_exact


def first_value(row: Mapping[str, Any], *names: str) -> Any:
    """机构域旧口径的候选链：返回首个非空白原始值。"""
    for name in names:
        value = row.get(name)
        if text_or_none(value) is not None:
            return value
    return None


def resolved_organization_vid(
    raw_id_or_name: Any,
    resolver: ExactOrganizationResolver,
    *,
    fallback_name: Any = None,
) -> str:
    """优先精确唯一名解析，否则视值为机构 ID（旧 resolved_organization_vid）。"""
    raw = text_or_none(raw_id_or_name)
    exact_id = resolver.resolve_exact(raw) if raw is not None else None
    exact_id = exact_id or resolver.resolve_exact(fallback_name)
    if exact_id is not None:
        return organization_vid(exact_id)
    if raw is None:
        raise ValueError("organization has no stable or exact unique identifier")
    return organization_vid(raw)


def organization_vid_from_row(
    row: Mapping[str, Any],
    resolver: ExactOrganizationResolver,
    *,
    id_fields: Sequence[str],
    name_fields: Sequence[str],
) -> str:
    """旧 _organization_vid_from_row 的 exact 模式：ID 优先，缺 ID 走精确名解析。"""
    raw_id = first_value(row, *id_fields)
    if text_or_none(raw_id) is not None:
        exact_id = resolver.resolve_exact(raw_id)
        return organization_vid(exact_id if exact_id is not None else raw_id)
    name = first_value(row, *name_fields)
    return resolved_organization_vid(name, resolver)


def _org_endpoint(
    row: Mapping[str, Any],
    resolver: ExactOrganizationResolver,
    *,
    id_fields: Sequence[str],
    name_fields: Sequence[str],
) -> str:
    return organization_vid_from_row(row, resolver, id_fields=id_fields, name_fields=name_fields)


def stable_rank(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") & (
        (1 << 63) - 1
    )


def edge_rank(edge_type: str, source_vid: str, target_vid: str, source_record_id: str) -> int:
    """旧 edge_rank：唯一支持的确定性图边 rank。"""
    return stable_rank(f"{edge_type}|{source_vid}|{target_vid}|{source_record_id}")


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


MAX_EXTRA_JSON_LENGTH = 64_000


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


def relation_confidence(row: Mapping[str, Any], *, source_table: str) -> float:
    """复刻旧 relation_confidence：源可靠性 + 显式端点证据。"""
    score = 0.55 if source_table.startswith("dwd_") else 0.45
    id_fields = (
        "organization_id",
        "org_id",
        "company_id",
        "entity_eid",
        "inv_org_id",
        "acquiring_org_id",
        "acquired_org_id",
        "affiliate",
        "affiliates_company_id",
        "admin_org_id",
        "antitypic",
    )
    explicit_ids = sum(text_or_none(row.get(name)) is not None for name in id_fields)
    if explicit_ids >= 1:
        score += 0.25
    if explicit_ids >= 2:
        score += 0.10
    if sum(text_or_none(value) is not None for value in row.values()) >= 3:
        score += 0.05
    if any(text_or_none(row.get(name)) is not None for name in ("external_id", "credit_no")):
        score += 0.05
    return round(min(max(score, 0.0), 1.0), 4)


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def person_vid_for_row(
    row: Mapping[str, Any],
    person_kind: str,
    name_field: str,
) -> str:
    """实体侧统一公式：kind|first(org_id, external_id)|name|birth_date|country。"""
    name = text_or_none(row.get(name_field))
    if name is None:
        raise ValueError("missing person name")
    target_identity = first_value(row, "org_id", "external_id")
    birth_date = first_value(row, "dm_birthdate", "bo_birthdate", "birth_date")
    country = first_value(row, "dm_nationalities", "bo_country_code", "country_code")
    return person_vid(person_kind, target_identity, name, birth_date, country)


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


def transform_org_relation(key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：机构域边按 spec 驱动转换，只输出边 JSON。

    resolver 每批从平台注入的 mysql ctx 构建一次（7 张机构表名称索引）；
    端点不验存/不建点（实体侧脚本负责），逐行失败进 failures。
    """

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


EDGE_PROVENANCE: tuple[str, ...] = (
    "organization_id",
    "confidence",
    "source_table",
    "source_record_id",
    "ingest_batch",
    "ingest_time",
)


RELATION_EDGE_SPECS: tuple[RelationEdgeSpec, ...] = (
    # --- LEGAL_REP_OF（3 表） ---
    RelationEdgeSpec(
        "legal_representative",
        "dwd_org_base_info",
        "LEGAL_REP_OF",
        "Organization",
        "domestic",
        "legal_representative",
        ("org_id", "lerep"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "lerep"),
        source_tags=("Person",),
    ),
    RelationEdgeSpec(
        "legal_representative",
        "dwd_research_institute_base_info",
        "LEGAL_REP_OF",
        "Organization",
        "domestic",
        "legal_representative",
        ("org_id", "lerep"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "lerep"),
        source_tags=("Person",),
    ),
    RelationEdgeSpec(
        "legal_representative",
        "dwd_special_taiwan_company",
        "LEGAL_REP_OF",
        "Organization",
        "domestic",
        "legal_representative",
        ("org_id", "legal_person"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "legal_person"),
        source_tags=("Person",),
    ),
    # --- SHAREHOLDER_OF（2 表） ---
    RelationEdgeSpec(
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
        ("Person", "Organization"),
    ),
    RelationEdgeSpec(
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
        ("Person", "Organization"),
    ),
    # --- EXECUTIVE_OF（2 表） ---
    RelationEdgeSpec(
        "executive",
        "dwd_org_executive_info",
        "EXECUTIVE_OF",
        "Organization",
        "domestic",
        "executive",
        ("org_id", "executives_name", "executives_position"),
        ("position", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "executives_name", "executives_position"),
        source_tags=("Person",),
    ),
    RelationEdgeSpec(
        "executive",
        "dwd_forg_executive_info",
        "EXECUTIVE_OF",
        "Organization",
        "foreign",
        "executive",
        ("org_id", "executives_name", "executives_position"),
        ("position", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "executives_name", "dm_birthdate"),
        source_tags=("Person",),
    ),
    # --- BENEFICIAL_OWNER_OF ---
    RelationEdgeSpec(
        "beneficial_owner",
        "dwd_forg_beneficiary_info",
        "BENEFICIAL_OWNER_OF",
        "Organization",
        "foreign",
        "beneficial_owner",
        ("org_id", "bo_name", "direct_percent", "indirect_percent", "total_percent"),
        (
            "direct_percent",
            "indirect_percent",
            "total_percent",
            "extra_json",
            *EDGE_PROVENANCE,
        ),
        frozenset({"direct_percent", "indirect_percent", "total_percent"}),
        ("org_id", "bo_name", "bo_birthdate"),
        ("Person",),
    ),
    # --- ACTUAL_CONTROLLER_OF ---
    RelationEdgeSpec(
        "actual_controller",
        "dwd_forg_act_contro_info",
        "ACTUAL_CONTROLLER_OF",
        "Organization",
        "foreign",
        "actual_controller",
        ("org_id", "entity_name", "entity_type", "direct_pct", "total_pct"),
        ("direct_pct", "total_pct", "extra_json", *EDGE_PROVENANCE),
        frozenset({"direct_pct", "total_pct"}),
        ("org_id", "entity_eid", "entity_name"),
        ("Person", "Organization"),
    ),
    # --- INVESTS_IN ---
    RelationEdgeSpec(
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
    # --- ACQUIRES ---
    RelationEdgeSpec(
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
    # --- SUBSIDIARY_OF ---
    RelationEdgeSpec(
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
    # --- HAS_NEWS ---
    RelationEdgeSpec(
        "news",
        "dwd_org_important_news_info",
        "HAS_NEWS",
        "News",
        "domestic",
        "news",
        ("org_id", "news_title", "news_date", "news_content"),
        ("extra_json", *EDGE_PROVENANCE),
    ),
    # --- INVOLVED_IN（17 表，4 种 extractor） ---
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    RelationEdgeSpec(
        "event",
        "dwd_org_bankruptcy_public_cases",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bankruptcy_admin",
        ("case_no", "admin_org"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("case_no", "admin_org_id", "admin_org"),
    ),
    RelationEdgeSpec(
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
    RelationEdgeSpec(
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
    # --- PRODUCES（活跃 2 条，经营信息表） ---
    RelationEdgeSpec(
        "product",
        "dwd_org_org_product_info",
        "PRODUCES",
        "Product",
        "domestic",
        "organization_product",
        ("org_id", "main_prod"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "main_prod"),
    ),
    RelationEdgeSpec(
        "product",
        "dwd_forg_product_info",
        "PRODUCES",
        "Product",
        "foreign",
        "organization_product",
        ("org_id", "main_products"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "main_products"),
    ),
)


for _spec in RELATION_EDGE_SPECS:
    SPECS_BY_KEY[_spec.key] = SPECS_BY_KEY.get(_spec.key, ()) + (_spec,)


assert len(RELATION_EDGE_SPECS) == 32


RELATION_KEY = "executive"


def _transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return transform_org_relation(RELATION_KEY, payload)


@step("executive_of")
def emit(payload):
    return _transform(payload)
