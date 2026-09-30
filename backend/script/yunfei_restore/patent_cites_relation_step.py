"""patent_cites 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.relation_extractors_one_relation.patent_cites_relation`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from kg_sdk import step
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("patent_cites")


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


def _ngql_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe nGQL identifier: {value!r}")
    return f"`{value}`"


def ensure_edge_schema(
    graph: Any,
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


def _sdk_context():
    """任务运行时注入的 kg_sdk 上下文；CLI 独立运行 / 未注入时返回 None。"""
    try:
        from kg_sdk import current_context

        return current_context()
    except ImportError:
        return None


class _LeasedGraphClient:
    """ctx 图客户端的租用视图：属性透传，close/connect 为 no-op。

    老脚本每次 ``graph_client()`` 都新建客户端并在 finally 里 close；平台 ctx
    客户端是任务进程共享的，直接 close 会让本步后续查询全部失败。
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass


def graph_client() -> Any:
    """平台注入版：任务所选图空间的 trs-graph 客户端（租用视图，close 无害）。"""
    from kg_sdk import current_context

    ctx = current_context()
    client = getattr(ctx, "graph", None) if ctx is not None else None
    if client is None:
        raise RuntimeError("本抽取脚本需要平台注入图客户端（任务/Schema 抽取请在触发时选择图空间）")
    return _LeasedGraphClient(client)


DEFAULT_DB = "gkx_element"


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


EDGE_PROPERTY_SCHEMAS: dict[str, dict[str, str]] = {
    "INVENTED_BY": {
        "sequence": "int64",
        "source_name": "string",
        "confidence": "double",
        "subject_type": "string",
        "resolution_status": "string",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
    "APPLIED_BY": {
        "sequence": "int64",
        "role": "string",
        "source_name": "string",
        "confidence": "double",
        "subject_type": "string",
        "resolution_status": "string",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
    "OWNED_BY": {
        "sequence": "int64",
        "role": "string",
        "is_current": "bool",
        "source_name": "string",
        "confidence": "double",
        "subject_type": "string",
        "resolution_status": "string",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
    "CITES": {
        "reference_identifier": "string",
        "sequence": "int64",
        "confidence": "double",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
}


def fetch_all(
    engine: Engine, sql: str, params: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text(sql), dict(params or {})).mappings().all()
        return [dict(row) for row in rows]


def graph_catalog(graph: Any, tag: str, fields: Iterable[str]) -> list[dict[str, Any]]:
    projections = ["id(v) AS vid", *(f"v.{tag}.{field} AS {field}" for field in fields)]
    return list(graph.execute_read(f"MATCH (v:{tag}) RETURN {','.join(projections)}").records)


CN_APPLICATION_RE = re.compile(r"^(?:cn|zl)?(\d{12})(?:[a-z]|\d)?$")


IDENTIFIER_CLEAN_RE = re.compile(r"[^0-9a-z]+")


def normalize_identifier(value: Any) -> str:
    """关系识别时临时规范化编号，不写入Patent属性。"""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return IDENTIFIER_CLEAN_RE.sub("", text)


def application_number_key(value: Any) -> str:
    """关系识别时统一中国申请号的供应商格式。"""
    key = normalize_identifier(value)
    matched = CN_APPLICATION_RE.fullmatch(key)
    return f"cn{matched.group(1)}" if matched else key


def identifier_index(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        for field_name in (
            "patent_id",
            "publication_number",
            "application_number",
            "granted_number",
        ):
            key = (
                application_number_key(row.get(field_name))
                if field_name == "application_number"
                else normalize_identifier(row.get(field_name))
            )
            if key and str(row["vid"]) not in result[key]:
                result[key].append(str(row["vid"]))
    return result


def patent_indexes(graph: Any, engine: Engine) -> tuple[dict[str, str], dict[str, list[str]]]:
    """旧 build_relations 的专利侧索引：图内 Patent 限定在 dwd_patent.patent_id 集合内。"""
    patents = graph_catalog(
        graph, "Patent", ("patent_id", "publication_number", "application_number", "granted_number")
    )
    source_patent_ids = {
        str(row["patent_id"]) for row in fetch_all(engine, "SELECT patent_id FROM dwd_patent")
    }
    patents = [row for row in patents if str(row.get("patent_id") or "") in source_patent_ids]
    vid_by_id = {str(row["patent_id"]): str(row["vid"]) for row in patents}
    return vid_by_id, identifier_index(patents)


def _load_index(database: str, dry_run: bool) -> dict[str, list[str]]:
    """连图连库构建 patent_index；dry_run 时也连图（旧口径如此）。"""
    engine = mysql_engine(database)
    graph = graph_client()
    try:
        _, patent_index = patent_indexes(graph, engine)
        if not dry_run:
            ensure_edge_schema(graph, "CITES", EDGE_PROPERTY_SCHEMAS["CITES"])
    finally:
        graph.close()
    engine.dispose()
    return patent_index


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


def parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def patent_candidates(index: dict[str, list[str]], value: Any) -> list[str]:
    """同时按通用编号和申请号格式查找，并对候选VID去重。"""
    keys = {normalize_identifier(value), application_number_key(value)} - {""}
    return list(dict.fromkeys(vid for key in keys for vid in index.get(key, [])))


def cites_mapper(index: dict[str, list[str]], stats: Counter):
    def mapper(table: str, row: dict, batch: str) -> list[EdgeRecord]:
        current = patent_candidates(index, row.get("patent_id"))
        if len(current) != 1:
            stats["CITES:missing_source"] += 1
            return []
        records: list[EdgeRecord] = []
        for column in ("patent_citations", "cited_by"):
            for sequence, identifier in enumerate(parse_json(row.get(column), []), start=1):
                candidates = patent_candidates(index, identifier)
                if len(candidates) != 1:
                    stats["CITES:unmatched_target"] += 1
                    continue
                source_vid, target_vid = (
                    (current[0], candidates[0])
                    if column == "patent_citations"
                    else (candidates[0], current[0])
                )
                if source_vid == target_vid:
                    continue
                stats["CITES:exact"] += 1
                records.append(
                    EdgeRecord(
                        "CITES",
                        source_vid,
                        target_vid,
                        {
                            "reference_identifier": str(identifier),
                            "sequence": sequence,
                            "confidence": 1.0,
                            "match_method": "exact_patent_identifier",
                            "match_evidence": "引用专利号与现有Patent唯一精确匹配",
                            "source_table": "dwd_patent_cited",
                            "source_record_id": f"{row['id']}:{column}:{sequence}",
                        },
                        rank=0,
                    )
                )
        return records

    return mapper


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON（专利号精确唯一匹配）。"""
    database = (payload.get("source") or {}).get("databaseName") or "gkx_element"
    patent_index = _load_index(database, dry_run=False)
    stats: Counter = Counter()
    result = edge_transform(payload, builder=cites_mapper(patent_index, stats))
    result["stats"] = {**(result.get("stats") or {}), **dict(stats)}
    return result


@step("patent_cites")
def emit(payload):
    return _transform(payload)
