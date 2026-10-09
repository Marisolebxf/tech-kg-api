"""affiliated_with 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.relation_extractors_one_relation.affiliated_with_relation`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kg_sdk import step

logger = logging.getLogger("affiliated_with")


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


def _org_vid(scholar_org_id: str | None, org_name: str | None) -> str | None:
    """旧 org_vid：优先机构 ID，否则机构名小写 md5 前 16 位桩。"""
    if scholar_org_id and scholar_org_id.strip():
        return f"org_{scholar_org_id.strip()}"
    if org_name and org_name.strip():
        key = org_name.strip().lower()
        return f"org_{hashlib.md5(key.encode('utf-8')).hexdigest()[:16]}"
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


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def affiliated_with(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    sid = str(row.get("scholar_id") or "").strip()
    org_name = str(row.get("scholar_org_name_zh") or row.get("scholar_org_name_en") or "")
    dst = _org_vid(str(row.get("scholar_org_id")) if row.get("scholar_org_id") else None, org_name)
    if not sid or not dst:
        return []
    has_org_id = bool(row.get("scholar_org_id") and str(row.get("scholar_org_id")).strip())
    if has_org_id:
        confidence = 1.0
        method = "source_org_id"
        evidence = "dwd_scholar.scholar_org_id 直接指向机构，无需名称推断"
    else:
        confidence = 0.6
        method = "org_name_md5_placeholder"
        evidence = (
            "源表无 scholar_org_id，机构顶点按机构名 md5 生成桩 VID，待正式 Organization 落地后对齐"
        )
    props = {
        "affiliation_name": org_name,
        "work_experience_date": row.get("work_experience_date") or "",
        "work_experience_department_zh": row.get("work_experience_department_zh") or "",
        "work_experience_position_zh": row.get("work_experience_position_zh") or "",
        "source": "scholar",
        "source_table": "dwd_scholar",
        "source_record_id": sid,
        "ingest_batch": batch,
        "ingest_time": now_utc(),
        "organization_base": "dwd_scholar" if has_org_id else "",
        "organization_id": str(row.get("scholar_org_id") or "").strip(),
        "confidence": confidence,
        "match_method": method,
        "match_evidence": evidence,
    }
    return [
        EdgeRecord(
            "AFFILIATED_WITH",
            f"person_{sid}",
            dst,
            props,
            identity={"source_record_id": sid},
            # 桩端点允许悬空（旧口径不做端点验存）。
            validate_endpoints=False,
        )
    ]


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON。"""
    return edge_transform(payload, builder=affiliated_with)


@step("affiliated_with")
def emit(payload):
    return _transform(payload)
