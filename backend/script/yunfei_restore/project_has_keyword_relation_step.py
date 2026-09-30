"""project_has_keyword 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.relation_extractors_one_relation.project_has_keyword_relation`` 及其依赖闭包自动生成；
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_sdk import step

logger = logging.getLogger("project_has_keyword")


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


EDGE_SCHEMA = {
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
}


def _ensure_schema(dry_run: bool) -> None:
    if dry_run:
        return
    graph = graph_client()
    try:
        ensure_edge_schema(graph, "HAS_KEYWORD", EDGE_SCHEMA)
    finally:
        graph.close()


def _resolve_report_dir(payload: dict[str, Any], batch: str) -> Path:
    configured = payload.get("report_dir")
    return Path(configured) if configured else private_state_dir("project-ingest-reports", batch)


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


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip())


def parse_list(raw: Any) -> list[str]:
    """解析 JSON 数组 / 逗号分隔 / 单字符串 → 非空字符串列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [normalize_name(str(x)) for x in raw if normalize_name(str(x))]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [normalize_name(str(x)) for x in data if normalize_name(str(x))]
        except json.JSONDecodeError:
            pass
    if "," in text:
        return [normalize_name(p) for p in text.split(",") if normalize_name(p)]
    # 中文分隔符（全角逗号/分号、顿号、半角分号）串起的多个值同样切分，
    # 否则整串被当成一个名字必然 not_found（participants/机构/关键词常见此形态）。
    if any(sep in text for sep in ("，", "；", "、", ";")):
        return [p for p in (normalize_name(part) for part in re.split(r"[，；、;]", text)) if p]
    return [normalize_name(text)]


class ProjectIngestReport:
    FILES = {
        "organization_not_found": "unmatched_organizations.jsonl",
        "organization_ambiguous": "ambiguous_organizations.jsonl",
        "person_not_found": "unmatched_persons.jsonl",
        "person_ambiguous": "ambiguous_persons.jsonl",
        "output_not_found": "unmatched_outputs.jsonl",
        "output_ambiguous": "ambiguous_outputs.jsonl",
        "cross_domain": "cross_domain_candidates.jsonl",
    }

    def __init__(self, report_dir: Path, *, ingest_batch: str, dry_run: bool) -> None:
        self.report_dir = report_dir
        self.ingest_batch = ingest_batch
        self.dry_run = dry_run
        self.stats: Counter[str] = Counter()
        self.records: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def increment(self, key: str, amount: int = 1) -> None:
        self.stats[key] += amount

    def add(self, category: str, record: dict[str, Any]) -> None:
        self.records[category].append(record)
        self.stats[category] += 1

    def write(self) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        for category, filename in self.FILES.items():
            path = self.report_dir / filename
            with path.open("w", encoding="utf-8") as handle:
                for record in self.records.get(category, []):
                    handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        summary = {
            "ingest_batch": self.ingest_batch,
            "dry_run": self.dry_run,
            "stats": dict(sorted(self.stats.items())),
        }
        (self.report_dir / "etl_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary


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


def keyword_vid(keyword: str) -> str:
    """三域统一：NFKC + 空白折叠 + casefold 后的完整 md5（专利域旧公式）。"""
    normalized = " ".join(unicodedata.normalize("NFKC", str(keyword)).strip().split())
    digest = hashlib.md5(normalized.casefold().encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"keyword_{digest}"


def make_project_has_keyword_mapper(
    report: ProjectIngestReport,
) -> Callable[[str, dict[str, Any], str], list[EdgeRecord]]:
    def project_has_keyword(table: str, row: dict[str, Any], batch: str) -> list[EdgeRecord]:
        project_id = str(row.get("id") or "")
        if not project_id:
            return []
        keywords = {normalize_text(value) for value in parse_list(row.get("keywords"))}
        records: list[EdgeRecord] = []
        for keyword in sorted(value for value in keywords if value):
            report.increment("keyword_candidates")
            report.increment("edges_HAS_KEYWORD")
            records.append(
                EdgeRecord(
                    "HAS_KEYWORD",
                    f"project_{project_id}",
                    keyword_vid(keyword),
                    edge_provenance(
                        source_table=table, source_record_id=project_id, ingest_batch=batch
                    ),
                    source_tag="Project",
                )
            )
        return records

    return project_has_keyword


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON。"""
    source = payload.get("source") or {}
    batch = f"se-{str(source.get('id') or 'x')[:8]}"
    _ensure_schema(False)
    report = ProjectIngestReport(
        _resolve_report_dir(payload, batch), ingest_batch=batch, dry_run=False
    )
    result = edge_transform(payload, builder=make_project_has_keyword_mapper(report))
    result["report_dir"] = str(report.report_dir)
    result["report"] = report.write()
    return result


def private_state_dir(*parts: str) -> Path:
    """平台注入版：报告落盘用临时目录（老 var/ 私有目录在容器外无意义）。"""
    import tempfile

    return Path(tempfile.gettempdir()).joinpath(*parts)


@step("project_has_keyword")
def emit(payload):
    return _transform(payload)
