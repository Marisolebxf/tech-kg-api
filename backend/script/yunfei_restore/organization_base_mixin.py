"""organization_base 溯源 mixin 抽取步（@step，yunfei_test 空间还原专用）。

复刻 ``script/paper_journal_relation/attach_provenance.py`` 的「真实实体」通道：
八张论文域源表 → 同名 vid 挂 organization_base mixin（confidence=1.0 + 溯源列，
organization_id 留空——论文表无 org_id 外键）：

  - dwd_zh_paper / dwd_en_paper               → ``paper_{id}``
  - dwd_zh_author / dwd_en_author             → ``person_{author_id}``
  - dwd_zh_journal / dwd_en_journal           → ``journal_{publication_id}``
  - dwd_zh_report / dwd_en_report             → ``report_{report_id}``
  - Keyword 域六源（与老一对一 keyword_entity 同源同 vid 公式 ``keyword_{md5}``，
    source_record_id 用 vid 本身，同 attach_provenance）

未复刻部分（见还原报告）：attach_provenance 的桩 vid（paper_ref_/cit_/rel_/rp_，
confidence=0.3，按图内前缀 MATCH）依赖 backfill_stub_journals 等脚本维护的桩点，
新空间无桩点可挂。mixin 无 name 键 → 平台同名消歧天然跳过，同一 vid 重复行由
INSERT VERTEX 幂等覆盖。
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from kg_sdk import step

logger = logging.getLogger("organization_base_mixin")


def clean_text(value: Any) -> str:
    """内部键/VID 用：strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return " ".join(str(value).strip().split())


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


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]
    # 机构域实体置 True：写前读取已有节点并复刻旧的属性合并保护。
    merge_protect: bool = False
    # merge_node 的 identity 匹配键；缺省 {"vid": vid}。
    identity: dict[str, Any] | None = field(default=None, compare=False)


def extra_json(row: Mapping[str, Any]) -> str:
    """新架构：完整源行进 extra_json。"""
    return json.dumps(json_safe(dict(row)), ensure_ascii=False, sort_keys=True)


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


_VID_RULES: dict[str, tuple[str, str]] = {
    "dwd_zh_paper": ("paper_{}", "id"),
    "dwd_en_paper": ("paper_{}", "id"),
    "dwd_zh_author": ("person_{}", "author_id"),
    "dwd_en_author": ("person_{}", "author_id"),
    "dwd_zh_journal": ("journal_{}", "publication_id"),
    "dwd_en_journal": ("journal_{}", "publication_id"),
    "dwd_zh_report": ("report_{}", "report_id"),
    "dwd_en_report": ("report_{}", "report_id"),
}


_KEYWORD_TABLES = (
    "dwd_scholar_research_direction",
    "dwd_zh_paper_classification",
    "dwd_en_paper_classification",
    "dwd_zh_project",
    "dwd_en_project",
    "dwd_patent",  # query_sql 绑定（tableName 仍为 dwd_patent）
)


_INGEST_BATCH = "yunfei_restore_org_base"


def _mixin_props(source_table: str, source_record_id: str) -> dict[str, Any]:
    return {
        "organization_id": "",
        "confidence": 1.0,
        "source_system": "gkx_element",
        "source_table": source_table,
        "source_record_id": source_record_id,
        "source_url": "",
        "ingest_batch": _INGEST_BATCH,
        "ingest_time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_update_time": "",
        "extra_json": "",
    }


@step("organization_base_mixin")
def emit(payload: Mapping[str, Any]) -> dict[str, Any]:
    source = payload.get("source") or {}
    table = str(payload.get("source_table") or source.get("tableName") or "")
    table = table.rsplit(".", 1)[-1]
    entities: list[dict[str, Any]] = []
    if table in _KEYWORD_TABLES:
        for row in payload.get("rows") or []:
            for record in keyword_records(table, row, _INGEST_BATCH):
                entities.append({"id": record.vid, "props": _mixin_props(table, record.vid)})
        return {"entities": entities}
    rule = _VID_RULES.get(table)
    if rule is None:
        raise RuntimeError(f"来源表 {table} 没有对应的 organization_base mixin 规则")
    template, id_column = rule
    for row in payload.get("rows") or []:
        raw_id = row.get(id_column)
        if raw_id is None or not str(raw_id).strip():
            continue
        record_id = str(raw_id).strip()
        entities.append({"id": template.format(record_id), "props": _mixin_props(table, record_id)})
    return {"entities": entities}
