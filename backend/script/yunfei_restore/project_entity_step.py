"""project_entity 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.entity_extractors_one_entity.project_entity`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from kg_sdk import step

logger = logging.getLogger("project_entity")


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


def date_text(value: Any) -> str:
    """项目域旧口径（to_str_date）：datetime/date 转 ISO 文本，None 转 ""。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


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


def project_vid(project_id: Any) -> str:
    raw = text_or_none(project_id)
    if raw is None:
        raise ValueError("missing project id")
    return bounded_vid(f"project_{raw}")


SOURCE_SYSTEM = "gkx_element"


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


def text_or_empty(value: Any) -> str:
    """学者/论文/项目/专利域旧口径：``value or ""``，保留原文（含内部空白）。"""
    return str(value) if value else ""


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


PROJECT_CONFIDENCE_FIELDS = (
    "title",
    "abstract",
    "funded_amount",
    "discipline",
    "approval_year",
    "fund_category",
)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (int, float)):
        return not math.isclose(float(value), 0.0)
    return bool(value)


def project_confidence(row: Mapping[str, Any]) -> float:
    """复刻旧 project_confidence：核心字段完整度，缺 title 封顶 0.6，下限 0.3。"""
    values = {f: row.get(f) for f in PROJECT_CONFIDENCE_FIELDS}
    filled = sum(1 for v in values.values() if _has_value(v))
    ratio = filled / len(PROJECT_CONFIDENCE_FIELDS)
    if not _has_value(values["title"]):
        ratio = min(ratio, 0.6)
    return round(max(0.3, ratio), 4)


def to_output_awards_json(raw: Any) -> str:
    """把 dwd_*_project_output.output_awards 规范成图属性 string（JSON 数组）。"""
    if raw is None:
        return "[]"
    if isinstance(raw, (list, dict)):
        return json.dumps(raw, ensure_ascii=False)
    text = str(raw).strip()
    if not text:
        return "[]"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps([text], ensure_ascii=False)
    if isinstance(parsed, (list, dict)):
        return json.dumps(parsed, ensure_ascii=False)
    return "[]"


def project_record(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    pid = text_or_empty(row.get("id"))
    if not pid:
        return []
    props = {
        "project_number": text_or_empty(row.get("project_number")),
        "title": text_or_empty(row.get("title")),
        "project_source": text_or_empty(row.get("project_source")),
        "project_level": text_or_empty(row.get("project_level")),
        "funded_amount": to_float_or_zero(row.get("funded_amount")),
        "discipline": text_or_empty(row.get("discipline")),
        "discipline_code": text_or_empty(row.get("discipline_code")),
        "fund_category": text_or_empty(row.get("fund_category")),
        "funded_region": text_or_empty(row.get("funded_province")),
        "approval_year": date_text(row.get("approval_year")),
        "approval_time": date_text(row.get("approval_time")),
        "research_period": text_or_empty(row.get("research_period")),
        "abstract": text_or_empty(row.get("abstract")),
        # 旧 ORM 未给 dwd_en_project 建模 final_report_abstract，英文项目恒为空。
        "final_report_abstract": (
            "" if table == "dwd_en_project" else text_or_empty(row.get("final_report_abstract"))
        ),
        "project_page_url": text_or_empty(row.get("project_page_url")),
        "source": "zh_project" if table == "dwd_zh_project" else "en_project",
        "total_outputs": to_int_or_zero(row.get("total_outputs")),
        "journal_articles_count": to_int_or_zero(row.get("journal_articles_count")),
        "conference_papers_count": to_int_or_zero(row.get("conference_papers_count")),
        "books_count": to_int_or_zero(row.get("books_count")),
        "degree_papers_count": to_int_or_zero(row.get("degree_papers_count")),
        "patents_count": to_int_or_zero(row.get("patents_count")),
        "clinical_trials_count": to_int_or_zero(row.get("clinical_trials_count")),
        "products_count": to_int_or_zero(row.get("products_count")),
        "awards_count": to_int_or_zero(row.get("awards_count")),
        # 奖项明细 JSON（dwd_*_project_output.output_awards），两点合作成果「奖项/评价」读取；
        # 与旧通道 load_project_graph.stage_outputs → build_output_count_props 同一规范函数。
        "output_awards": to_output_awards_json(row.get("output_awards")),
        "reports_count": to_int_or_zero(row.get("reports_count")),
        "other_outputs_count": to_int_or_zero(row.get("other_outputs_count")),
        "extra_json": extra_json(row),
        **provenance(
            table=table,
            record_id=pid,
            ingest_batch=batch,
            source_url=row.get("project_page_url"),
            source_update_time=date_text(row.get("updated_time") or row.get("update_time")),
            confidence=project_confidence(row),
        ),
    }
    return [EntityRecord("Project", project_vid(pid), props)]


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
    return entity_transform(payload, builder=project_record)


@step("project_entity")
def emit(payload):
    return _transform(payload)
