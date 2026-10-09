"""patent_entity 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.entity_extractors_one_entity.patent_entity`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from kg_sdk import step

logger = logging.getLogger("patent_entity")


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


def datetime_text(value: Any) -> str | None:
    """专利域旧口径（ngql_datetime 的值语义）：None 转 None，其余转 T 分隔文本。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    return str(value).replace(" ", "T")[:19]


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


def normalized_language(value: Any) -> str:
    """专利域旧口径：JSON 数组 join 成逗号串。"""
    value = parse_json(value)
    return ",".join(map(str, value)) if isinstance(value, list) else str(value or "")


def original_text(value: Any) -> str:
    """专利域旧口径：从 JSON 数组取各元素 text/content，以换行连接。"""
    value = parse_json(value)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and (text := item.get("text") or item.get("content")):
                return "\n".join(map(str, text)) if isinstance(text, list) else str(text)
    return str(value or "")


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


def str_or_empty(value: Any) -> str:
    """专利域旧口径（ngql_string）：仅 None 转 ""，其余 str() 保留。"""
    return "" if value is None else str(value)


def to_int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
    return entity_transform(payload, builder=patent_record)


@step("patent_entity")
def emit(payload):
    return _transform(payload)
