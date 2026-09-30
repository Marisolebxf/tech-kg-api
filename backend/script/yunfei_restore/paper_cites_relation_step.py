"""paper_cites 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.relation_extractors_one_relation.paper_cites_relation`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from kg_sdk import step

logger = logging.getLogger("paper_cites")


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


CONFIGS = (
    ("dwd_zh_paper_reference", "CITES", "paper_ref", "reference_identifier", 0.5),
    ("dwd_en_paper_reference", "CITES", "paper_ref", "reference_identifier", 0.5),
    ("dwd_zh_paper_citation", "CITED_BY", "paper_cit", "citation_identifier", 0.5),
    ("dwd_en_paper_citation", "CITED_BY", "paper_cit", "citation_identifier", 0.5),
    ("dwd_zh_paper_related", "RELATED_TO", "paper_rel", None, 0.7),
    ("dwd_en_paper_related", "RELATED_TO", "paper_rel", None, 0.7),
)


CONFIG_BY_TABLE = {config[0]: config for config in CONFIGS}


_PAPER_SUFFIX_RE = re.compile(r"__\d+$")


def paper_source_id(raw_id: Any) -> str:
    """论文端点旧口径：去掉 ``__数字`` 后缀（仅用于关系端点）。"""
    raw = str(raw_id or "")
    return _PAPER_SUFFIX_RE.sub("", raw) if raw else ""


def paper_stub_vid(prefix: str, key: str) -> str:
    """论文工作流旧口径的 md5 桩：``{prefix}_{md5(key)[:16]}``（key 不做归一）。"""
    digest = hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{prefix}_{digest[:16]}"


def paper_cites(table: str, row: Mapping[str, Any], batch: str) -> list[EdgeRecord]:
    _, edge_type, stub_prefix, id_field, confidence = CONFIG_BY_TABLE[table]
    pid = paper_source_id(row.get("id"))
    doi = str(row.get("doi") or "").strip()
    if not pid or not doi:
        return []
    props: dict[str, Any] = {"confidence": confidence}
    if id_field:
        props[id_field] = doi
    return [
        EdgeRecord(
            edge_type,
            f"paper_{pid}",
            paper_stub_vid(stub_prefix, doi),
            props,
            rank=0,
            validate_endpoints=False,
        )
    ]


def _transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return edge_transform(payload, builder=paper_cites)


@step("paper_cites")
def emit(payload):
    return _transform(payload)
