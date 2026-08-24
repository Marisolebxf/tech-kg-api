"""Shared primitives for refactored one-entity extraction scripts.

This module is intentionally independent from the legacy ETL scripts under
``backend/script``. Entity scripts define source SQL and mapping functions here,
then this module handles paging, provenance and graph writes.

数据内容口径与旧脚本严格对齐：

- 机构域（organization_entity_etl.py 系）文本/数值/置信度/VID/稳定键算法按旧
  ``organization_etl_common.py`` 复刻：空白值写 NULL（写图时省略该属性）、文本
  20000 字符截断、``entity_confidence`` 动态打分、``person_vid``/``product_vid``/
  ``stable_record_id``/``bounded_vid`` 旧公式。
- 学者/论文/项目/专利域保留旧脚本 ``value or ""`` 的原文口径（``text_or_empty``）。
- 写图保留新架构（逐条 ``merge_node`` upsert），机构域实体通过 ``merge_protect``
  复刻旧"已有节点属性合并保护"（保留已有非空标准属性、confidence 只升不降、
  ``extra_json.source_records`` 多源合并）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logger = logging.getLogger("entity_extractors_one_entity")

DEFAULT_DB = "gkx_element"
DEFAULT_BATCH_SIZE = 500

SOURCE_SYSTEM = "gkx_element"
MAX_TEXT_LENGTH = 20_000
MAX_EXTRA_JSON_LENGTH = 64_000
VID_MAX_BYTES = 64


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def common_args_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """从 workflow payload dict 提取通用 ETL 参数（CLI argparse 的 dict 化镜像）。

    供 dual-mode 脚本的 ``workflow(payload)`` 入口复用——payload key 用 snake_case，
    跟 argparse 转换后的 ``vars(args)`` 同形态，便于 ``build_sources(payload)`` 这类
    脚本专属函数在 CLI 和 workflow 两条路径下共享。
    """
    return {
        "log_level": payload.get("log_level", "INFO"),
        "database": payload.get("database", DEFAULT_DB),
        "batch_size": int(payload.get("batch_size") or DEFAULT_BATCH_SIZE),
        "limit": payload.get("limit"),
        "since": payload.get("since"),
        "dry_run": bool(payload.get("dry_run", False)),
        "ingest_batch": payload.get("ingest_batch"),
    }


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--database", default=DEFAULT_DB)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since", help="增量水位：只抽取 updated_time > since 的行")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ingest-batch")
    return parser


def mysql_engine(database: str = DEFAULT_DB) -> Engine:
    user = os.getenv("MYSQL_USERNAME", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True)


def graph_client() -> TRSGraphClient:
    settings = TRSGraphSettings.from_env()
    graph = TRSGraphClient(settings)
    graph.connect()
    return graph


# ---------------------------------------------------------------------------
# 文本语义（两套口径，均复刻旧脚本）
# ---------------------------------------------------------------------------


def text_or_empty(value: Any) -> str:
    """学者/论文/项目/专利域旧口径：``value or ""``，保留原文（含内部空白）。"""
    return str(value) if value else ""


def str_or_empty(value: Any) -> str:
    """专利域旧口径（ngql_string）：仅 None 转 ""，其余 str() 保留。"""
    return "" if value is None else str(value)


def date_text(value: Any) -> str:
    """项目域旧口径（to_str_date）：datetime/date 转 ISO 文本，None 转 ""。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def datetime_text(value: Any) -> str | None:
    """专利域旧口径（ngql_datetime 的值语义）：None 转 None，其余转 T 分隔文本。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    return str(value).replace(" ", "T")[:19]


def parse_json(value: Any) -> Any:
    """专利域旧口径：字符串尝试 JSON 解析，失败原样返回。"""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def json_snapshot(value: Any) -> str:
    """专利域旧口径：JSON 字段紧凑快照，None 转 ""。"""
    value = parse_json(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else ""


def original_text(value: Any) -> str:
    """专利域旧口径：从 JSON 数组取各元素 text/content，以换行连接。"""
    value = parse_json(value)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and (text := item.get("text") or item.get("content")):
                return "\n".join(map(str, text)) if isinstance(text, list) else str(text)
    return str(value or "")


def normalized_language(value: Any) -> str:
    """专利域旧口径：JSON 数组 join 成逗号串。"""
    value = parse_json(value)
    return ",".join(map(str, value)) if isinstance(value, list) else str(value or "")


def paper_text(value: Any) -> str:
    """论文工作流旧口径：仅把换行替换为空格，其余保留原文。"""
    return text_or_empty(value).replace("\n", " ").replace("\r", " ")


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


def clean_text(value: Any) -> str:
    """内部键/VID 用：strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return " ".join(str(value).strip().split())


def first_value(row: Mapping[str, Any], *names: str) -> Any:
    """机构域旧口径的候选链：返回首个非空白原始值。"""
    for name in names:
        value = row.get(name)
        if text_or_none(value) is not None:
            return value
    return None


def first(row: Mapping[str, Any], *fields: str) -> Any:
    """新架构候选链：按 clean_text 判空，返回原始值。"""
    for field_name in fields:
        value = row.get(field_name)
        if clean_text(value):
            return value
    return None


# ---------------------------------------------------------------------------
# 数值转换（两套口径）
# ---------------------------------------------------------------------------


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


def to_float_or_zero(value: Any) -> float:
    """项目域旧口径（project_graph_utils.to_float）：非法值返回 0.0。"""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def to_int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# JSON 序列化（机构域旧口径 + 新架构整行保留）
# ---------------------------------------------------------------------------


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


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def extra_json(row: Mapping[str, Any]) -> str:
    """新架构：完整源行进 extra_json。"""
    return json.dumps(json_safe(dict(row)), ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# 虚拟/合成源行过滤（机构域旧口径）
# ---------------------------------------------------------------------------

VIRTUAL_SOURCE_MARKERS: tuple[str, ...] = ("mock", "stub", "virtual", "placeholder", "test")
VIRTUAL_SOURCE_FIELDS: tuple[str, ...] = ("data_source", "source_system")


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


# ---------------------------------------------------------------------------
# 机构 ID / 置信度（机构域旧口径）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# VID / 稳定键（机构域旧公式）
# ---------------------------------------------------------------------------


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def normalize_key(value: Any) -> str:
    return unicodedata.normalize("NFKC", clean_text(value)).casefold()


def md5_vid(prefix: str, value: Any, *, short: bool = True) -> str:
    digest = hashlib.md5(normalize_key(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16] if short else digest}"


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


def project_vid(project_id: Any) -> str:
    raw = text_or_none(project_id)
    if raw is None:
        raise ValueError("missing project id")
    return bounded_vid(f"project_{raw}")


def event_vid(table: str, record_id: str) -> str:
    return bounded_vid(f"event_{table}_{record_id}")


def news_vid(record_id: str) -> str:
    raw = text_or_none(record_id)
    if raw is None:
        raise ValueError("missing news record id")
    return bounded_vid(f"news_{raw}")


def product_vid(name: Any) -> str:
    """复刻旧 product_vid：规范化产品名完整 32 位 md5。"""
    raw = text_or_none(name)
    if raw is None:
        raise ValueError("missing product name")
    normalized = unicodedata.normalize("NFKC", raw).casefold()
    return bounded_vid(f"product_{md5_hex(normalized)}")


def datasource_vid(table: str) -> str:
    return bounded_vid(f"ds_{table}")


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


def source_record_id(row: Mapping[str, Any], *fields: str) -> str:
    """新架构候选链稳定键（非机构域口径）。"""
    parts = [
        clean_text(row.get(field_name)) for field_name in fields if clean_text(row.get(field_name))
    ]
    if parts:
        return "|".join(parts)
    payload = json.dumps(json_safe(dict(row)), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# 溯源
# ---------------------------------------------------------------------------


def provenance(
    *,
    table: str,
    record_id: str,
    ingest_batch: str,
    source_url: Any = None,
    source_update_time: Any = None,
    confidence: float = 1.0,
    source_system: str = SOURCE_SYSTEM,
) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "source_table": table,
        "source_record_id": record_id,
        "source_url": text_or_none(source_url),
        "ingest_batch": ingest_batch,
        "ingest_time": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_update_time": text_or_none(source_update_time),
        "confidence": confidence,
        "match_method": "source_primary_key",
        "match_evidence": f"{table}.{record_id} 主键/稳定键直接抽取",
    }


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


# ---------------------------------------------------------------------------
# 增量 / 分页
# ---------------------------------------------------------------------------


def apply_since(sql: str, since: str | None, col: str = "updated_time") -> str:
    """复刻旧 _since 的增量条件注入（兼容带 ORDER BY 的 SQL）。"""
    if not since:
        return sql
    condition = f"{col} > :since"
    lowered = sql.lower()
    order_by = lowered.find(" order by ")
    if order_by >= 0:
        return f"{sql[:order_by]} WHERE {condition}{sql[order_by:]}"
    if " where " in lowered:
        return f"{sql} AND {condition}"
    return f"{sql} WHERE {condition}"


def iter_rows(
    engine: Engine,
    sql: str,
    *,
    batch_size: int,
    limit: int | None = None,
    cursor_column: str | None = None,
    params: dict[str, Any] | None = None,
) -> Iterable[dict[str, Any]]:
    """分页读取。默认 LIMIT/OFFSET；指定 cursor_column 时走 keyset 游标分页。

    keyset 模式要求 SQL 含 ``:cursor`` 绑定参数并按该列唯一排序（如专利的
    ``CAST(p.id AS UNSIGNED) > :cursor ORDER BY CAST(p.id AS UNSIGNED)``）。
    """
    bind_params = dict(params or {})
    if cursor_column is not None:
        cursor: Any = 0
        yielded = 0
        while True:
            page_limit = batch_size
            if limit is not None:
                remaining = limit - yielded
                if remaining <= 0:
                    return
                page_limit = min(page_limit, remaining)
            page_params = dict(bind_params)
            page_params["cursor"] = cursor
            page_params["limit"] = page_limit
            with engine.connect() as conn:
                rows = conn.execute(text(sql), page_params).mappings().all()
            if not rows:
                return
            for row in rows:
                yield dict(row)
                yielded += 1
            if len(rows) < page_limit:
                return
            cursor = rows[-1][cursor_column]
        return
    offset = 0
    yielded = 0
    while True:
        page_limit = batch_size
        if limit is not None:
            remaining = limit - yielded
            if remaining <= 0:
                return
            page_limit = min(page_limit, remaining)
        page_sql = f"{sql} LIMIT :limit OFFSET :offset"
        page_params = dict(bind_params)
        page_params["limit"] = page_limit
        page_params["offset"] = offset
        with engine.connect() as conn:
            rows = conn.execute(text(page_sql), page_params).mappings().all()
        if not rows:
            return
        for row in rows:
            yield dict(row)
            yielded += 1
        offset += len(rows)
        if len(rows) < page_limit:
            return


# ---------------------------------------------------------------------------
# 已有节点属性合并保护（机构域旧口径）
# ---------------------------------------------------------------------------


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raw = text_or_none(value)
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
    """复刻旧合并保护：保留已有非空标准属性、confidence 只升不降、多源 extra_json。"""
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
                text_or_none(incoming.get("source_table")) or "unknown_table",
                text_or_none(incoming.get("source_record_id")) or "unknown_record",
            )
        )
        source_records[source_key] = incoming_payload
        envelope["source_records"] = source_records
        merged_extra = bounded_json(envelope)
        if merged_extra != text_or_none(existing.get("extra_json")):
            updates["extra_json"] = merged_extra
    return updates


def _ngql_string_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def existing_vertex_properties(
    graph: TRSGraphClient,
    tag: str,
    vids: list[str],
) -> dict[str, dict[str, Any]]:
    """复刻旧批量读点：一次 MATCH 查询取回已有节点属性。"""
    if not vids:
        return {}
    values = ",".join(_ngql_string_literal(vid) for vid in sorted(set(vids)))
    query = (
        f"MATCH (v:`{tag}`) WHERE id(v) IN [{values}] RETURN id(v) AS vid,properties(v) AS props;"
    )
    result: dict[str, dict[str, Any]] = {}
    for record in graph.execute_read(query).records:
        vid = text_or_none(record.get("vid"))
        props = record.get("props")
        if vid is not None:
            result[vid] = dict(props) if isinstance(props, Mapping) else {}
    return result


# ---------------------------------------------------------------------------
# 图写入
# ---------------------------------------------------------------------------


def _drop_null_props(properties: Mapping[str, Any]) -> dict[str, Any]:
    """None 值属性不上报；其余值字符串化以匹配 trs-graph REST 的 string-typed 列。

    NebulaGraph 对 string 列做严格类型校验——传 float/int 会被 400
    `Storage Error: data type does not meet the requirements`。旧 nGQL INSERT
    VERTEX 用字符串字面量本就隐式转字符串，REST 路径需要显式 stringify。
    """
    return {
        name: value if isinstance(value, str) else str(value)
        for name, value in properties.items()
        if value is not None
    }


def write_records(records: list[EntityRecord], *, dry_run: bool) -> dict[str, int]:
    if dry_run:
        return {"scanned": len(records), "written": 0, "dry_run": 1}
    graph = graph_client()
    written = updated = 0
    try:
        protected_tags = {record.tag for record in records if record.merge_protect}
        existing_by_tag: dict[str, dict[str, dict[str, Any]]] = {}
        for tag in protected_tags:
            vids = [record.vid for record in records if record.merge_protect and record.tag == tag]
            existing_by_tag[tag] = existing_vertex_properties(graph, tag, vids)
        for record in records:
            props = dict(record.properties)
            props["vid"] = record.vid
            identity = dict(record.identity) if record.identity else {"vid": record.vid}
            if record.merge_protect:
                current = existing_by_tag.get(record.tag, {}).get(record.vid)
                if current is not None:
                    changes = merge_existing_properties(current, props)
                    if not changes:
                        continue
                    # 与旧逻辑一致：更新时携带全部已有非空属性，避免稀疏行
                    # 把 canonical 字段冲掉。
                    complete = {name: value for name, value in current.items() if value is not None}
                    complete.update(changes)
                    complete["vid"] = record.vid
                    graph.merge_node([record.tag], identity, _drop_null_props(complete))
                    updated += 1
                    continue
            graph.merge_node([record.tag], identity, _drop_null_props(props))
            written += 1
    finally:
        graph.close()
    return {"scanned": len(records), "written": written, "updated": updated, "dry_run": 0}


# ---------------------------------------------------------------------------
# 抽取主流程
# ---------------------------------------------------------------------------


def run_entity_extractor(
    *,
    database: str,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    ingest_batch: str | None,
    sources: list[tuple[str, str, Callable[[str, Mapping[str, Any], str], list[EntityRecord]]]],
    since: str | None = None,
    global_limit: bool = False,
    dedupe: str | None = None,
    cursor_column: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """逐源抽取写图。

    - ``since``：对每个源 SQL 注入 ``updated_time > :since`` 增量条件。
    - ``global_limit``：True 时 ``limit`` 跨所有源全局生效（旧项目脚本口径）。
    - ``dedupe="first"``：同一 VID 首条记录胜出（旧产业链 setdefault 口径）。
    - ``cursor_column``：keyset 游标分页列（旧专利脚本口径）。
    - 行级异常计 invalid 并继续（旧机构域脚本口径）。
    """
    batch_id = ingest_batch or f"ENTITY_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    engine = mysql_engine(database)
    summary: dict[str, Any] = {"ingest_batch": batch_id, "sources": {}}
    remaining_global = limit if (global_limit and limit is not None) else None
    try:
        for table, sql, mapper in sources:
            pending: list[EntityRecord] = []
            stats = {"scanned": 0, "valid": 0, "written": 0, "updated": 0, "invalid": 0}
            source_limit = None if global_limit else limit
            if remaining_global is not None and remaining_global <= 0:
                summary["sources"][table] = stats
                continue
            if global_limit:
                source_limit = remaining_global
            seen_vids: set[str] = set()
            effective_sql = apply_since(sql, since)
            params: dict[str, Any] = dict(extra_params or {})
            if since:
                params["since"] = since
            for row in iter_rows(
                engine,
                effective_sql,
                batch_size=batch_size,
                limit=source_limit,
                cursor_column=cursor_column,
                params=params,
            ):
                stats["scanned"] += 1
                try:
                    mapped = mapper(table, row, batch_id)
                except Exception:
                    stats["invalid"] += 1
                    logger.warning(
                        "mapper failed table=%s row keys=%s",
                        table,
                        sorted(row)[:8],
                        exc_info=True,
                    )
                    continue
                if dedupe == "first":
                    mapped = [rec for rec in mapped if rec.vid not in seen_vids]
                    seen_vids.update(rec.vid for rec in mapped)
                stats["valid"] += len(mapped)
                pending.extend(mapped)
                if len(pending) >= batch_size:
                    result = write_records(pending, dry_run=dry_run)
                    stats["written"] += result["written"]
                    stats["updated"] += result.get("updated", 0)
                    pending = []
            if pending:
                result = write_records(pending, dry_run=dry_run)
                stats["written"] += result["written"]
                stats["updated"] += result.get("updated", 0)
            summary["sources"][table] = stats
            if global_limit:
                remaining_global = (
                    None if remaining_global is None else remaining_global - stats["scanned"]
                )
    finally:
        engine.dispose()
    return summary


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
