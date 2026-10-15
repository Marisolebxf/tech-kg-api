"""scholar_organization 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

学者任职机构实体：dwd_scholar_work_experience 的 distinct 机构名落图，
vid 与 AFFILIATED_WITH 关系边的机构端点同键（机构名小写 md5 前 16 位），
保证任职边端点实连（不再悬空）。正式机构库（企业/高校/研究所）落地后
经同名消歧（T_LINK）合并，本域顶点保留溯源。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kg_sdk import step

logger = logging.getLogger("scholar_organization")

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


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def org_name_vid(org_name: str) -> str:
    """机构名 → 机构顶点 vid：与 AFFILIATED_WITH 边端点同一 md5 键。"""
    key = org_name.strip().lower()
    return f"org_{hashlib.md5(key.encode('utf-8')).hexdigest()[:16]}"


def scholar_organization(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    org_name_zh = str(row.get("org_name_zh") or "").strip()
    org_name_en = str(row.get("org_name_en") or "").strip()
    org_name = org_name_zh or org_name_en
    if not org_name:
        return []
    return [
        EntityRecord(
            "ScholarOrganization",
            org_name_vid(org_name),
            {
                "name": org_name,
                "name_cn": org_name_zh,
                "name_en": org_name_en,
                "org_kind": "scholar_affiliation",
                "confidence": 0.6,
                "source_table": "dwd_scholar_work_experience",
                "source_record_id": org_name,
                "ingest_batch": batch,
                "ingest_time": now_utc(),
            },
        )
    ]


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → entities JSON。"""
    return entity_transform(payload, builder=scholar_organization)


@step("scholar_organization")
def emit(payload):
    return _transform(payload)
