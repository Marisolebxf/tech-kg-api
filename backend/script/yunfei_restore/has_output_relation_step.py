"""has_output 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

由 script/tools/build_portable_steps.py 从 ``script.relation_extractors_one_relation.has_output_relation`` 及其依赖闭包自动生成；
抽取口径与老脚本逐行一致，MySQL/图客户端改经平台 ctx 注入。请勿手改，
改动请落到原模块后重新生成。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_sdk import step

logger = logging.getLogger("has_output")


@dataclass(frozen=True)
class MatchResult:
    status: str
    vid: str | None = None
    method: str = ""
    evidence: str = ""


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


class ExactIndex:
    def __init__(self) -> None:
        self._values: dict[str, set[str]] = {}

    def add(self, value: Any, vid: str, *, normalizer=normalize_text) -> None:
        key = normalizer(value)
        if key:
            self._values.setdefault(key, set()).add(vid)

    def match(self, value: Any, *, method: str, normalizer=normalize_text) -> MatchResult:
        key = normalizer(value)
        vids = self._values.get(key, set()) if key else set()
        if len(vids) == 1:
            return MatchResult("matched", next(iter(vids)), method, key)
        return MatchResult("ambiguous" if len(vids) > 1 else "not_found", evidence=key)


_TRANSIENT_GRAPH_ERROR_TOKENS = ("watermark", "use space failed", "no extra session")


def retry_transient(fn: Any, *, tries: int = 10, wait_seconds: float = 30.0) -> Any:
    """通用瞬态重试：仅用于幂等调用（读 / merge / update）。

    共享宿主内存贴近 0.80 高水位时，trs-graph 的 nGQL 或 schema REST 调用会在
    USE space 准入阶段被整批拒绝（400/500），会话池也可能被其它租户瞬时占满；
    这类失败过一会儿自然恢复，直接抛出会把长 ETL 在写入前整体打死。
    """
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as exc:
            text = f"{exc} {getattr(exc, 'body', '')}"
            if attempt < tries and any(token in text for token in _TRANSIENT_GRAPH_ERROR_TOKENS):
                logger.warning(
                    "共享图库水位/会话池瞬时不足（第 %d/%d 次），%.0fs 后重试: %s",
                    attempt,
                    tries - 1,
                    wait_seconds,
                    str(exc)[:200],
                )
                time.sleep(wait_seconds)
                continue
            raise


def _read_with_transient_retry(
    graph: Any,
    query: str,
    *,
    tries: int = 10,
    wait_seconds: float = 30.0,
) -> Any:
    """池加载查询的水位退避重试。"""
    return retry_transient(
        lambda: graph.execute_read(query), tries=tries, wait_seconds=wait_seconds
    )


def _scan_candidate_rows(
    graph: Any,
    label: str,
    return_properties: tuple[str, ...],
    filters: dict[str, set[str]],
    *,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    """Fallback for shared Tags whose match properties do not have indexes."""
    projection = ", ".join(f"n.{label}.{prop} AS {prop}" for prop in return_properties)
    normalized_filters = {
        prop: {normalize_text(value) for value in values if normalize_text(value)}
        for prop, values in filters.items()
    }
    rows: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        query = (
            f"MATCH (n:{label}) RETURN id(n) AS vid, {projection} SKIP {offset} LIMIT {page_size};"
        )
        page = _read_with_transient_retry(graph, query).records
        for row in page:
            if any(
                normalize_text(row.get(prop)) in wanted
                for prop, wanted in normalized_filters.items()
            ):
                rows[str(row["vid"])] = row
        if len(page) < page_size:
            break
        offset += page_size
    return list(rows.values())


def _candidate_rows(
    graph: Any,
    label: str,
    return_properties: tuple[str, ...],
    filters: dict[str, set[str]],
    *,
    chunk_size: int = 5000,
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    projection = ", ".join(f"n.{label}.{prop} AS {prop}" for prop in return_properties)
    for filter_property, values in filters.items():
        clean_values = sorted({str(value).strip() for value in values if str(value).strip()})
        for offset in range(0, len(clean_values), chunk_size):
            literals = json.dumps(clean_values[offset : offset + chunk_size], ensure_ascii=False)
            query = (
                f"MATCH (n:{label}) WHERE n.{label}.{filter_property} IN {literals} "
                f"RETURN id(n) AS vid, {projection};"
            )
            try:
                result = _read_with_transient_retry(graph, query)
            except Exception as exc:
                if "IndexNotFound" not in getattr(exc, "body", ""):
                    raise
                return _scan_candidate_rows(graph, label, return_properties, filters)
            for row in result.records:
                rows[str(row["vid"])] = row
    return list(rows.values())


def normalize_doi(value: Any) -> str:
    value = normalize_text(value)
    value = re.sub(r"^https?://", "", value, count=1)
    for prefix in ("doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.strip()


def normalize_patent_number(value: Any) -> str:
    return re.sub(r"[\s\-./]", "", str(value or "").strip()).upper()


def organization_id_from_vid(vid: str) -> str:
    """从 Organization VID 解析稳定 ID（org_{id} → id；否则原样返回）。"""
    text = str(vid or "").strip()
    if text.startswith("org_"):
        return text[4:] or text
    return text


def resolve_organization_id(
    vid: str,
    *,
    node_props: dict[str, Any] | None = None,
    cache: dict[str, str] | None = None,
) -> str:
    """优先 cache / 节点 source_record_id|org_id|organization_id，再回退 VID 解析。"""
    if cache and vid in cache and cache[vid]:
        return cache[vid]
    props = node_props or {}
    for key in ("source_record_id", "org_id", "organization_id"):
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return organization_id_from_vid(vid)


class ProjectEntityMatcher:
    def __init__(self) -> None:
        self.organization = ExactIndex()
        self.person = ExactIndex()
        self.paper_doi = ExactIndex()
        self.paper_title = ExactIndex()
        self.paper_title_year = ExactIndex()
        self.patent_number = ExactIndex()
        self.patent_title = ExactIndex()
        self.report_title = ExactIndex()
        self.report_title_year = ExactIndex()
        # vid → 稳定 organization_id（来自 source_record_id / org_id 或 VID 解析）
        self.organization_ids: dict[str, str] = {}

    def organization_id(self, vid: str) -> str:
        return resolve_organization_id(vid, cache=self.organization_ids)

    def remember_organization(self, vid: str, row: dict[str, Any]) -> None:
        oid = resolve_organization_id(vid, node_props=row)
        if oid:
            self.organization_ids[str(vid)] = oid

    @classmethod
    def from_graph(cls, graph: Any, candidates: dict[str, set[str]]) -> ProjectEntityMatcher:
        matcher = cls()
        for row in _candidate_rows(
            graph,
            "Organization",
            ("name_cn", "name_en", "source_record_id", "org_id"),
            {"name_cn": candidates["organization"], "name_en": candidates["organization"]},
        ):
            vid = str(row["vid"])
            for prop in ("name_cn", "name_en"):
                matcher.organization.add(row.get(prop), vid)
            matcher.remember_organization(vid, row)
        for row in _candidate_rows(
            graph,
            "Person",
            ("name_zh", "name_cn", "name_en"),
            {prop: candidates["person"] for prop in ("name_zh", "name_cn", "name_en")},
        ):
            for prop in ("name_zh", "name_cn", "name_en"):
                matcher.person.add(row.get(prop), row["vid"])
        for row in _candidate_rows(
            graph,
            "Paper",
            ("doi", "title_zh", "title_en", "publication_year"),
            {
                "doi": candidates["paper_doi"],
                "title_zh": candidates["paper_title"],
                "title_en": candidates["paper_title"],
            },
        ):
            matcher.paper_doi.add(row.get("doi"), row["vid"], normalizer=normalize_doi)
            year = normalize_text(row.get("publication_year"))
            for prop in ("title_zh", "title_en"):
                title = row.get(prop)
                matcher.paper_title.add(title, row["vid"])
                if normalize_text(title) and year:
                    matcher.paper_title_year.add(f"{title}|{year}", row["vid"])
        for row in _candidate_rows(
            graph,
            "Patent",
            (
                "application_number",
                "publication_number",
                "patent_id",
                "title_original",
                "title_zh",
                "title_en",
            ),
            {
                **{
                    prop: candidates["patent_number"]
                    for prop in ("application_number", "publication_number", "patent_id")
                },
                **{
                    prop: candidates["patent_title"]
                    for prop in ("title_original", "title_zh", "title_en")
                },
            },
        ):
            for prop in ("application_number", "publication_number", "patent_id"):
                matcher.patent_number.add(
                    row.get(prop), row["vid"], normalizer=normalize_patent_number
                )
            for prop in ("title_original", "title_zh", "title_en"):
                matcher.patent_title.add(row.get(prop), row["vid"])
        for row in _candidate_rows(
            graph,
            "Report",
            ("title_cn", "title_en", "publication_date"),
            {
                "title_cn": candidates["report_title"],
                "title_en": candidates["report_title"],
            },
        ):
            year = normalize_text(row.get("publication_date"))[:4]
            for prop in ("title_cn", "title_en"):
                title = row.get(prop)
                matcher.report_title.add(title, row["vid"])
                if normalize_text(title) and year:
                    matcher.report_title_year.add(f"{title}|{year}", row["vid"])
        return matcher

    def match_paper(self, item: dict[str, Any]) -> MatchResult:
        doi = item.get("doi")
        if normalize_doi(doi):
            result = self.paper_doi.match(doi, method="doi_exact", normalizer=normalize_doi)
            if result.status != "not_found":
                return result
        title, year = item.get("title"), item.get("year")
        if normalize_text(title) and normalize_text(year):
            result = self.paper_title_year.match(f"{title}|{year}", method="title_year_exact")
            if result.status != "not_found":
                return result
        return self.paper_title.match(title, method="title_exact")

    def match_patent(self, item: dict[str, Any]) -> MatchResult:
        number = (
            item.get("patent_number")
            or item.get("application_number")
            or item.get("publication_number")
            or item.get("patent_id")
        )
        if normalize_patent_number(number):
            result = self.patent_number.match(
                number,
                method="patent_number_exact",
                normalizer=normalize_patent_number,
            )
            if result.status != "not_found":
                return result
        return self.patent_title.match(
            item.get("patent_title") or item.get("title"), method="title_exact"
        )

    def match_report(self, item: dict[str, Any]) -> MatchResult:
        title, year = item.get("title"), item.get("year")
        if normalize_text(title) and normalize_text(year):
            result = self.report_title_year.match(f"{title}|{year}", method="title_year_exact")
            if result.status != "not_found":
                return result
        return self.report_title.match(title, method="title_exact")


EXACT_MATCH_METHODS = frozenset(
    {
        "name_exact",
        "doi_exact",
        "doi_registry_exact",
        "patent_number_exact",
        "patent_number_registry_exact",
        "title_exact",
        "title_year_exact",
    }
)


def confidence_from_method(method: str, evidence: str = "") -> float:
    """实体/关系匹配置信度：精确类 1.0；hybrid 取 evidence 中 score；否则 0.9。"""
    if method in EXACT_MATCH_METHODS:
        return 1.0
    match = re.search(r"score=([0-9.]+)", evidence or "")
    if match:
        try:
            return round(float(match.group(1)), 4)
        except ValueError:
            pass
    return 0.9


def match_audit_props(method: str, evidence: str = "") -> dict[str, Any]:
    """边审计三件套：match_method / match_evidence / confidence。"""
    return {
        "match_method": method or "",
        "match_evidence": evidence or "",
        "confidence": confidence_from_method(method or "", evidence or ""),
    }


def parse_json_objects(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    text = str(raw).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


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


OUTPUT_FIELDS = (
    ("output_journal_articles", "journal_article", "paper"),
    ("output_conference_papers", "conference_paper", "paper"),
    ("output_degree_papers", "degree_paper", "paper"),
    ("output_patents", "patent", "patent"),
    ("output_reports", "report", "report"),
)


TARGET_TAGS = {"paper": "Paper", "patent": "Patent", "report": "Report"}


def _matched_vid(
    report: ProjectIngestReport,
    result: Any,
    category: str,
    record: dict[str, Any],
) -> str | None:
    """旧 _matched_vid：matched 计数返回 vid，否则进复核目录。"""
    if result.status == "matched":
        report.increment(f"{category}_matched")
        return result.vid
    report.add(f"{category}_{result.status}", {**record, "evidence": result.evidence})
    return None


def _output_identifier(item: dict[str, Any]) -> str:
    return str(
        item.get("doi")
        or item.get("patent_number")
        or item.get("application_number")
        or item.get("publication_number")
        or item.get("patent_id")
        or ""
    )


def _output_title(item: dict[str, Any]) -> str:
    return str(item.get("patent_title") or item.get("title") or "")


def make_has_output_mapper(
    matcher: ProjectEntityMatcher,
    report: ProjectIngestReport,
) -> Callable[[str, dict[str, Any], str], list[EdgeRecord]]:
    matchers = {
        "paper": matcher.match_paper,
        "patent": matcher.match_patent,
        "report": matcher.match_report,
    }

    def has_output(table: str, row: dict[str, Any], batch: str) -> list[EdgeRecord]:
        project_id = str(row.get("id") or "")
        if not project_id:
            return []
        pvid = f"project_{project_id}"
        records: list[EdgeRecord] = []
        for field_name, output_type, target_type in OUTPUT_FIELDS:
            for item in parse_json_objects(row.get(field_name)):
                report.increment(f"{target_type}_output_candidates")
                result = matchers[target_type](item)
                title, identifier = _output_title(item), _output_identifier(item)
                target = _matched_vid(
                    report,
                    result,
                    "output",
                    {
                        "project_id": project_id,
                        "output_type": output_type,
                        "target_type": target_type,
                        "title": title,
                        "identifier": identifier,
                        "source_table": table,
                    },
                )
                if not target:
                    continue
                relation_key = f"{project_id}|{output_type}|{target}"
                props = {
                    "output_type": output_type,
                    "output_title": title,
                    "output_identifier": identifier,
                    **match_audit_props(result.method, result.evidence),
                    "source_table": table,
                    "source_record_id": relation_key,
                    "ingest_batch": batch,
                    "ingest_time": now_utc(),
                }
                report.increment("edges_HAS_OUTPUT")
                records.append(
                    EdgeRecord(
                        "HAS_OUTPUT",
                        pvid,
                        target,
                        props,
                        source_tag="Project",
                        target_tag=TARGET_TAGS[target_type],
                    )
                )
        return records

    return has_output


def _add(target: set[str], value: Any) -> None:
    cleaned = str(value or "").strip()
    if cleaned:
        target.add(cleaned)


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


EDGE_SCHEMA = {
    "output_type": "string",
    "output_title": "string",
    "output_identifier": "string",
    "match_method": "string",
    "match_evidence": "string",
    "confidence": "double",
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
}


def _load_matcher(candidates: dict[str, set[str]], dry_run: bool) -> ProjectEntityMatcher:
    graph = graph_client()
    try:
        matcher = ProjectEntityMatcher.from_graph(graph, candidates)
        if not dry_run:
            ensure_edge_schema(graph, "HAS_OUTPUT", EDGE_SCHEMA)
    finally:
        graph.close()
    return matcher


EMPTY_CANDIDATES: dict[str, set[str]] = {
    "organization": set(),
    "person": set(),
    "paper_doi": set(),
    "paper_title": set(),
    "patent_number": set(),
    "patent_title": set(),
    "report_title": set(),
}


def resolve_report_dir(payload: Mapping[str, Any], batch: str) -> Path:
    """Resolve an explicit report directory or a private runtime default."""
    configured = payload.get("report_dir")
    return (
        Path(str(configured)) if configured else private_state_dir("project-ingest-reports", batch)
    )


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON；matcher 候选取自本批行。"""
    source = payload.get("source") or {}
    batch = f"se-{str(source.get('id') or 'x')[:8]}"
    rows = payload.get("rows") or []
    candidates = {key: set() for key in EMPTY_CANDIDATES}
    for r in rows:
        for field_name in (
            "output_journal_articles",
            "output_conference_papers",
            "output_degree_papers",
        ):
            for item in parse_json_objects(r.get(field_name)):
                _add(candidates["paper_doi"], item.get("doi"))
                _add(candidates["paper_doi"], normalize_doi(item.get("doi")))
                _add(candidates["paper_title"], item.get("title"))
        for item in parse_json_objects(r.get("output_patents")):
            number = (
                item.get("patent_number")
                or item.get("application_number")
                or item.get("publication_number")
                or item.get("patent_id")
            )
            _add(candidates["patent_number"], number)
            _add(candidates["patent_number"], normalize_patent_number(number))
            _add(candidates["patent_title"], item.get("patent_title") or item.get("title"))
        for item in parse_json_objects(r.get("output_reports")):
            _add(candidates["report_title"], item.get("title"))
    matcher = _load_matcher(candidates, dry_run=False)
    report = ProjectIngestReport(
        resolve_report_dir(payload, batch), ingest_batch=batch, dry_run=False
    )
    result = edge_transform(payload, builder=make_has_output_mapper(matcher, report))
    result["report_dir"] = str(report.report_dir)
    result["report"] = report.write()
    return result


def private_state_dir(*parts: str) -> Path:
    """平台注入版：报告落盘用临时目录（老 var/ 私有目录在容器外无意义）。"""
    import tempfile

    return Path(tempfile.gettempdir()).joinpath(*parts)


@step("has_output")
def emit(payload):
    return _transform(payload)
