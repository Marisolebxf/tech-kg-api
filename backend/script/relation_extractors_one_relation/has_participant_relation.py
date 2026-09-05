"""One-relation transform for HAS_PARTICIPANT（Project → Person）（平台喂数抽取：只输出边 JSON）.

复刻旧 load_project_graph.py stage_project_relations 口径：dwd_zh/en_project 的
participants 按 parse_list 解析、normalize_text 去重排序后逐个经 person 索引
（name_zh/name_cn/name_en 精确唯一）匹配既有 Person 顶点，每个 matched 一条边；
ambiguous/not_found 进 ProjectIngestReport 复核目录。候选集沿用旧
collect_match_candidates 的 person 通道（project_host + participants 全集，二者
会并入同一索引）。REST merge_edge 按 source_record_id（= 项目 ID）幂等。

"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from script.extract_transform_common import edge_transform
from script.project_entity_matcher import ProjectEntityMatcher, normalize_text
from script.project_graph_utils import match_audit_props, parse_list
from script.project_ingest_report import ProjectIngestReport
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    edge_provenance,
    ensure_edge_schema,
    graph_client,
    mysql_engine,
    resolve_report_dir,
)
from script.relation_extractors_one_relation.leads_relation import collect_person_candidates

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

EDGE_SCHEMA = {
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
    "match_method": "string",
    "match_evidence": "string",
    "confidence": "double",
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


def make_has_participant_mapper(
    matcher: ProjectEntityMatcher,
    report: ProjectIngestReport,
) -> Callable[[str, dict[str, Any], str], list[EdgeRecord]]:
    def has_participant(table: str, row: dict[str, Any], batch: str) -> list[EdgeRecord]:
        project_id = str(row.get("id") or "")
        if not project_id:
            return []
        participants = {normalize_text(value) for value in parse_list(row.get("participants"))}
        records: list[EdgeRecord] = []
        for participant in sorted(value for value in participants if value):
            report.increment("person_candidates")
            part_result = matcher.person.match(participant, method="name_exact")
            target = _matched_vid(
                report,
                part_result,
                "person",
                {"project_id": project_id, "field": "participants", "value": participant},
            )
            if not target:
                continue
            props = {
                **edge_provenance(
                    source_table=table, source_record_id=project_id, ingest_batch=batch
                ),
                **match_audit_props(part_result.method, part_result.evidence),
            }
            report.increment("edges_HAS_PARTICIPANT")
            records.append(
                EdgeRecord(
                    "HAS_PARTICIPANT",
                    f"project_{project_id}",
                    target,
                    props,
                    source_tag="Project",
                    target_tag="Person",
                )
            )
        return records

    return has_participant


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
    """连 MySQL 收集 person 候选（复用 leads_relation.collect_person_candidates）。"""
    engine = mysql_engine(database)
    try:
        return collect_person_candidates(
            engine,
            tables,
            batch_size=batch_size,
            limit=limit,
            since=since,
        )
    finally:
        engine.dispose()


def _load_matcher(candidates: set[str], dry_run: bool) -> ProjectEntityMatcher:
    graph = graph_client()
    try:
        matcher = ProjectEntityMatcher.from_graph(graph, {**EMPTY_CANDIDATES, "person": candidates})
        if not dry_run:
            ensure_edge_schema(graph, "HAS_PARTICIPANT", EDGE_SCHEMA)
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
    candidates = set()
    for r in rows:
        host = str(r.get("project_host") or "").strip()
        if host:
            candidates.add(host)
        for value in parse_list(r.get("participants")):
            if str(value).strip():
                candidates.add(str(value).strip())
    matcher = _load_matcher(candidates, dry_run=False)
    report = ProjectIngestReport(
        resolve_report_dir(payload, batch), ingest_batch=batch, dry_run=False
    )
    result = edge_transform(payload, builder=make_has_participant_mapper(matcher, report))
    result["report_dir"] = str(report.report_dir)
    result["report"] = report.write()
    return result
