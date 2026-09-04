"""One-relation transform for FUNDED_BY（Project → Organization）（平台喂数抽取：只输出边 JSON）.

复刻旧 load_project_graph.py stage_project_relations 口径：dwd_zh/en_project 的
funded_institution（normalize_text 后去尾部分号）经 ProjectEntityMatcher 的
organization 索引（name_cn/name_en 精确唯一）匹配既有 Organization 顶点，仅
matched 写边；ambiguous/not_found 进 ProjectIngestReport 复核目录（报告路径沿用
旧默认 /tmp/project-ingest-reports/{batch}）。参与单位（participating_institution）
按旧口径只记 cross_domain 报告（PARTICIPATES_IN 归机构域），不建边。
REST merge_edge 按 source_record_id（= 项目 ID）幂等。

"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from script.extract_transform_common import edge_transform
from script.project_entity_matcher import ProjectEntityMatcher, normalize_text
from script.project_graph_utils import (
    funded_by_org_props,
    match_audit_props,
    parse_list,
    to_float,
)
from script.project_ingest_report import ProjectIngestReport
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    apply_since,
    edge_provenance,
    ensure_edge_schema,
    graph_client,
    iter_rows,
    mysql_engine,
    resolve_report_dir,
)

TABLES = ("dwd_zh_project", "dwd_en_project")
PROJECT_SQL = "SELECT * FROM {table} ORDER BY id"
# from_graph 需要全部候选键；空集合不会触发对应 Tag 的图查询。
EMPTY_CANDIDATES: dict[str, set[str]] = {
    "organization": set(),
    "person": set(),
    "paper_doi": set(),
    "paper_title": set(),
    "patent_number": set(),
    "patent_title": set(),
    "report_title": set(),
}

# 旧 ensure_alignment_edge_schema 口径的幂等补列（含溯源与匹配审计全集）。
EDGE_SCHEMA = {
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
    "funded_amount": "double",
    "fund_category": "string",
    "match_method": "string",
    "match_evidence": "string",
    "confidence": "double",
    "organization_id": "string",
    "organization_source_table": "string",
}


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


def collect_organization_candidates(
    engine: Any,
    tables: tuple[str, ...],
    *,
    batch_size: int,
    limit: int | None,
    since: str | None,
) -> set[str]:
    """旧 collect_match_candidates 的 organization 通道：候选为原始 funded_institution。"""
    candidates: set[str] = set()
    for table in tables:
        sql = apply_since(f"SELECT funded_institution FROM {table} ORDER BY id", since)
        params = {"since": since} if since else None
        for row in iter_rows(engine, sql, batch_size=batch_size, limit=limit, params=params):
            cleaned = str(row.get("funded_institution") or "").strip()
            if cleaned:
                candidates.add(cleaned)
    return candidates


def make_funded_by_mapper(
    matcher: ProjectEntityMatcher,
    report: ProjectIngestReport,
) -> Callable[[str, dict[str, Any], str], list[EdgeRecord]]:
    def funded_by(table: str, row: dict[str, Any], batch: str) -> list[EdgeRecord]:
        project_id = str(row.get("id") or "")
        if not project_id:
            return []
        institution = normalize_text(row.get("funded_institution")).rstrip("；;")
        records: list[EdgeRecord] = []
        if institution:
            report.increment("organization_candidates")
            org_result = matcher.organization.match(institution, method="name_exact")
            target = _matched_vid(
                report,
                org_result,
                "organization",
                {"project_id": project_id, "field": "funded_institution", "value": institution},
            )
            if target:
                props = {
                    **edge_provenance(
                        source_table=table, source_record_id=project_id, ingest_batch=batch
                    ),
                    "funded_amount": to_float(row.get("funded_amount")),
                    "fund_category": row.get("fund_category") or "",
                    **match_audit_props(org_result.method, org_result.evidence),
                    **funded_by_org_props(matcher.organization_id(target)),
                }
                report.increment("edges_FUNDED_BY")
                records.append(
                    EdgeRecord(
                        "FUNDED_BY",
                        f"project_{project_id}",
                        target,
                        props,
                        source_tag="Project",
                        target_tag="Organization",
                    )
                )
        # 参与单位跨域候选：只记报告（PARTICIPATES_IN 归机构域），不建边。
        for name in sorted(set(parse_list(row.get("participating_institution")))):
            report.add(
                "cross_domain",
                {
                    "project_id": project_id,
                    "relation": "PARTICIPATES_IN",
                    "owner_domain": "organization",
                    "value": name,
                    "source_table": table,
                },
            )
        return records

    return funded_by


def _resolve_tables(payload: dict[str, Any]) -> tuple[str, ...]:
    table_choice = payload.get("table", "all")
    return TABLES if table_choice == "all" else (str(table_choice),)


def _collect_candidates(
    database: str,
    tables: tuple[str, ...],
    batch_size: int,
    limit: int | None,
    since: str | None,
) -> set[str]:
    """连 MySQL 收集 organization 候选（旧 main 里 try/finally dispose 那段）。"""
    engine = mysql_engine(database)
    try:
        return collect_organization_candidates(
            engine,
            tables,
            batch_size=batch_size,
            limit=limit,
            since=since,
        )
    finally:
        engine.dispose()


def _load_matcher(candidates: set[str], dry_run: bool) -> ProjectEntityMatcher:
    """连图加载 matcher；dry_run 时也连图（matcher.from_graph 不写图）。"""
    graph = graph_client()
    try:
        matcher = ProjectEntityMatcher.from_graph(
            graph, {**EMPTY_CANDIDATES, "organization": candidates}
        )
        if not dry_run:
            ensure_edge_schema(graph, "FUNDED_BY", EDGE_SCHEMA)
    finally:
        graph.close()
    return matcher


SOURCES = [
    {"table": t, "pk": "id", "time": "update_time", "query_sql": f"SELECT * FROM {t}"}
    for t in TABLES
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON；matcher 候选取自本批行。"""
    source = payload.get("source") or {}
    batch = f"se-{str(source.get('id') or 'x')[:8]}"
    rows = payload.get("rows") or []
    candidates = {str(r.get("funded_institution") or "").strip() for r in rows}
    candidates.discard("")
    matcher = _load_matcher(candidates, dry_run=False)
    report = ProjectIngestReport(
        resolve_report_dir(payload, batch), ingest_batch=batch, dry_run=False
    )
    result = edge_transform(payload, builder=make_funded_by_mapper(matcher, report))
    result["report_dir"] = str(report.report_dir)
    result["report"] = report.write()
    return result
