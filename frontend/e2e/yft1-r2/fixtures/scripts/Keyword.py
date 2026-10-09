"""keyword_entity 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.entity_extractors_one_entity.keyword_entity`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from kg_sdk import step

logger = logging.getLogger("keyword_entity")


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


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


def clean_text(value: Any) -> str:
    """内部键/VID 用：strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return " ".join(str(value).strip().split())


def first(row: Mapping[str, Any], *fields: str) -> Any:
    """新架构候选链：按 clean_text 判空，返回原始值。"""
    for field_name in fields:
        value = row.get(field_name)
        if clean_text(value):
            return value
    return None


def normalize_key(value: Any) -> str:
    return unicodedata.normalize("NFKC", clean_text(value)).casefold()


def md5_vid(prefix: str, value: Any, *, short: bool = True) -> str:
    digest = hashlib.md5(normalize_key(value).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{prefix}_{digest[:16] if short else digest}"


SOURCE_SYSTEM = "gkx_element"


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


def source_record_id(row: Mapping[str, Any], *fields: str) -> str:
    """新架构候选链稳定键（非机构域口径）。"""
    parts = [
        clean_text(row.get(field_name)) for field_name in fields if clean_text(row.get(field_name))
    ]
    if parts:
        return "|".join(parts)
    payload = json.dumps(json_safe(dict(row)), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _try_parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


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
    return entity_transform(payload, builder=keyword_records)


@step("keyword_entity")
def emit(payload):
    return _transform(payload)
