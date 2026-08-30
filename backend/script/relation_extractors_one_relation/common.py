"""Shared primitives for the one-relation-per-script edge extractors.

数据内容口径与旧关系脚本严格对齐，写入机制保留两条旧通道：

- **确定性 rank 模式**（机构域/专利域旧口径）：``EdgeRecord.rank`` 由
  ``edge_rank()`` 的 sha256 确定性公式生成，写 nGQL ``INSERT EDGE @rank``，
  同一源记录重跑得到同一 (edge_type, src, dst, rank) 身份，属性覆盖更新。
- **REST merge 模式**（学者/项目域旧口径）：``merge_edge`` 按
  ``identityProps``（默认 ``source_record_id``）upsert。

关系脚本一律不建顶点：端点缺失跳过并计数（``missing_source``/``missing_target``）。
允许悬空端点的边（如 AFFILIATED_WITH 的机构名桩、论文 DOI 桩）将
``validate_endpoints`` 置 False。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logger = logging.getLogger("relation_extractors_one_relation")

DEFAULT_DB = "gkx_element"
DEFAULT_BATCH_SIZE = 500


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


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def common_args_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """从 workflow payload dict 提取通用 ETL 参数（CLI argparse 的 dict 化镜像）。

    供 dual-mode 关系脚本的 ``workflow(payload)`` 入口复用——payload key 用 snake_case，
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


def _sdk_context():
    """任务运行时注入的 kg_sdk 上下文；CLI 独立运行 / 未注入时返回 None。"""
    try:
        from kg_sdk import current_context

        return current_context()
    except ImportError:
        return None


def mysql_engine(database: str = DEFAULT_DB) -> Engine:
    # 任务下发时选择的数据源优先；无上下文（CLI / 本地）回退 MYSQL_* env
    context = _sdk_context()
    params = context.to_dict().get("mysql") if context is not None else None
    if params:
        database = params.get("database") or database
        url = (
            f"mysql+pymysql://{params.get('username', 'root')}:{params.get('password', '')}"
            f"@{params.get('host', '127.0.0.1')}:{params.get('port', 3306)}"
            f"/{database}?charset=utf8mb4"
        )
        return create_engine(url, pool_pre_ping=True)
    user = os.getenv("MYSQL_USERNAME", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True)


def graph_client() -> TRSGraphClient:
    # 任务下发时选择的图空间优先（附带观测式溯源）；无上下文回退 TRS_GRAPH_* env
    context = _sdk_context()
    if context is not None:
        client = context.graph
        if client is not None:
            return client
    settings = TRSGraphSettings.from_env()
    graph = TRSGraphClient(settings)
    graph.connect()
    return graph


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 确定性 rank（机构域/专利域旧公式）
# ---------------------------------------------------------------------------


def stable_rank(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") & (
        (1 << 63) - 1
    )


def edge_rank(edge_type: str, source_vid: str, target_vid: str, source_record_id: str) -> int:
    """旧 edge_rank：唯一支持的确定性图边 rank。"""
    return stable_rank(f"{edge_type}|{source_vid}|{target_vid}|{source_record_id}")


# ---------------------------------------------------------------------------
# 溯源
# ---------------------------------------------------------------------------


def edge_provenance(
    *,
    source_table: str,
    source_record_id: str,
    ingest_batch: str,
) -> dict[str, Any]:
    """REST merge 模式边溯源（学者/项目域旧口径的最小集）。"""
    return {
        "source_table": source_table,
        "source_record_id": source_record_id,
        "ingest_batch": ingest_batch,
        "ingest_time": now_utc(),
    }


# ---------------------------------------------------------------------------
# nGQL 渲染与批量写入（rank 模式）
# ---------------------------------------------------------------------------


def _vid_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _edge_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return format(value, ".15g") if isinstance(value, float) else str(value)
    text = str(value).strip()
    return json.dumps(text if text else "", ensure_ascii=False)


def _ngql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe nGQL identifier: {value!r}")
    return f"`{value}`"


def render_edge_insert(records: list[EdgeRecord]) -> str:
    """按旧 render_edge_insert 口径渲染多值 INSERT EDGE（rank 模式）。"""
    if not records:
        raise ValueError("cannot render an empty edge insert")
    names = tuple(records[0].properties)
    if any(tuple(record.properties) != names for record in records):
        raise ValueError("one INSERT EDGE batch must have one property signature")
    props = ",".join(_ngql_identifier(name) for name in names)
    rows = []
    for record in records:
        values = ",".join(_edge_literal(record.properties.get(name)) for name in names)
        rows.append(
            f"{_vid_literal(record.source_vid)}->{_vid_literal(record.target_vid)}"
            f"@{record.rank}:({values})"
        )
    return (
        f"INSERT EDGE {_ngql_identifier(records[0].edge_type)} ({props}) VALUES "
        + ",".join(rows)
        + ";"
    )


# ---------------------------------------------------------------------------
# 边 schema 幂等补齐（旧 ensure_schema 口径）
# ---------------------------------------------------------------------------


def ensure_edge_schema(
    graph: TRSGraphClient,
    edge_type: str,
    properties: Mapping[str, str],
    *,
    wait_seconds: float = 2.0,
) -> list[str]:
    """DESCRIBE EDGE 后对缺失属性做幂等 ALTER EDGE ADD（merge 接口对 schema 外属性 400）。"""
    try:
        result = graph.execute_read(f"DESCRIBE EDGE {_ngql_identifier(edge_type)};")
    except Exception:
        logger.warning("DESCRIBE EDGE %s failed; skip schema ensure", edge_type)
        return []
    existing = set()
    for record in result.records:
        field = record.get("Field")
        if field is not None:
            existing.add(str(field))
    missing = [(name, prop_type) for name, prop_type in properties.items() if name not in existing]
    if not missing:
        return []
    columns = ",".join(f"{_ngql_identifier(name)} {prop_type}" for name, prop_type in missing)
    graph.execute_write(f"ALTER EDGE {_ngql_identifier(edge_type)} ADD ({columns});")
    if wait_seconds:
        import time

        time.sleep(wait_seconds)
    return [name for name, _ in missing]


# ---------------------------------------------------------------------------
# 端点验存
# ---------------------------------------------------------------------------


def existing_vids(graph: TRSGraphClient, tag: str, vids: Iterable[str]) -> set[str]:
    """批量验存：返回图中已存在的 vid 集合（旧端点验存口径）。"""
    values = ",".join(_vid_literal(v) for v in sorted(set(vids)))
    if not values:
        return set()
    query = f"MATCH (v:{_ngql_identifier(tag)}) WHERE id(v) IN [{values}] RETURN id(v) AS vid;"
    result: set[str] = set()
    for record in graph.execute_read(query).records:
        vid = record.get("vid")
        if vid is not None:
            result.add(str(vid))
    return result


# ---------------------------------------------------------------------------
# 增量 / 分页（与实体包同口径）
# ---------------------------------------------------------------------------


def apply_since(sql: str, since: str | None, col: str = "updated_time") -> str:
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
# 写入层
# ---------------------------------------------------------------------------


def write_edges(records: list[EdgeRecord], *, dry_run: bool) -> dict[str, int]:
    if dry_run:
        return {"scanned": len(records), "written": 0, "dry_run": 1}
    graph = graph_client()
    written = 0
    missing_source = 0
    missing_target = 0
    try:
        # 端点验存：按 tag 分组批量查已有 vid。
        known: dict[str, set[str]] = {}
        tags = {
            tag
            for record in records
            if record.validate_endpoints
            for tag in (record.source_tag, record.target_tag)
            if tag
        }
        for tag in tags:
            known[tag] = existing_vids(
                graph,
                tag,
                [
                    vid
                    for record in records
                    if record.validate_endpoints
                    for vid in (record.source_vid, record.target_vid)
                ],
            )
        writable: list[EdgeRecord] = []
        for record in records:
            if record.validate_endpoints:
                if record.source_tag and record.source_vid not in known.get(
                    record.source_tag, set()
                ):
                    missing_source += 1
                    continue
                if record.target_tag and record.target_vid not in known.get(
                    record.target_tag, set()
                ):
                    missing_target += 1
                    continue
            writable.append(record)
        # rank 模式：按 (edge_type, 属性签名) 分组渲染多值 INSERT EDGE。
        rank_records = [record for record in writable if record.rank is not None]
        groups: dict[tuple[str, tuple[str, ...]], list[EdgeRecord]] = {}
        for record in rank_records:
            groups.setdefault((record.edge_type, tuple(record.properties)), []).append(record)
        for group in groups.values():
            graph.execute_write(render_edge_insert(group))
            written += len(group)
        # REST merge 模式：逐条 merge_edge，按 identityProps upsert。
        for record in writable:
            if record.rank is not None:
                continue
            identity = record.identity or {
                "source_record_id": record.properties["source_record_id"]
            }
            graph.merge_edge(
                record.source_vid, record.target_vid, record.edge_type, identity, record.properties
            )
            written += 1
    finally:
        graph.close()
    return {
        "scanned": len(records),
        "written": written,
        "missing_source": missing_source,
        "missing_target": missing_target,
        "dry_run": 0,
    }


# ---------------------------------------------------------------------------
# 抽取主流程
# ---------------------------------------------------------------------------


def run_relation_extractor(
    *,
    database: str,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    ingest_batch: str | None,
    sources: list[tuple[str, str, Callable[[str, Mapping[str, Any], str], list[EdgeRecord]]]],
    since: str | None = None,
    dedupe: str | None = None,
    cursor_column: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """逐源抽取写边。行级异常计 invalid 并继续（旧口径）。"""
    batch_id = ingest_batch or f"RELATION_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    engine = mysql_engine(database)
    summary: dict[str, Any] = {"ingest_batch": batch_id, "sources": {}}
    try:
        for table, sql, mapper in sources:
            pending: list[EdgeRecord] = []
            stats = {
                "scanned": 0,
                "valid": 0,
                "written": 0,
                "invalid": 0,
                "missing_source": 0,
                "missing_target": 0,
            }
            effective_sql = apply_since(sql, since)
            params: dict[str, Any] = dict(extra_params or {})
            if since:
                params["since"] = since
            seen: set[tuple[str, str, str]] = set()
            for row in iter_rows(
                engine,
                effective_sql,
                batch_size=batch_size,
                limit=limit,
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
                    mapped = [
                        rec
                        for rec in mapped
                        if (rec.edge_type, rec.source_vid, rec.target_vid) not in seen
                    ]
                    seen.update((rec.edge_type, rec.source_vid, rec.target_vid) for rec in mapped)
                stats["valid"] += len(mapped)
                pending.extend(mapped)
                if len(pending) >= batch_size:
                    result = write_edges(pending, dry_run=dry_run)
                    stats["written"] += result["written"]
                    stats["missing_source"] += result.get("missing_source", 0)
                    stats["missing_target"] += result.get("missing_target", 0)
                    pending = []
            if pending:
                result = write_edges(pending, dry_run=dry_run)
                stats["written"] += result["written"]
                stats["missing_source"] += result.get("missing_source", 0)
                stats["missing_target"] += result.get("missing_target", 0)
            summary["sources"][table] = stats
    finally:
        engine.dispose()
    return summary


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
