"""One-relation extractor: HAS_PARTICIPANT（Project → Person）.

复刻旧 load_project_graph.py stage_project_relations 口径：dwd_zh/en_project 的
participants 按 parse_list 解析、normalize_text 去重排序后逐个经 person 索引
（name_zh/name_cn/name_en 精确唯一）匹配既有 Person 顶点，每个 matched 一条边；
ambiguous/not_found 进 ProjectIngestReport 复核目录。候选集沿用旧
collect_match_candidates 的 person 通道（project_host + participants 全集，二者
会并入同一索引）。REST merge_edge 按 source_record_id（= 项目 ID）幂等。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.has_participant_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from script.project_entity_matcher import ProjectEntityMatcher, normalize_text
from script.project_graph_utils import match_audit_props, parse_list
from script.project_ingest_report import ProjectIngestReport
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    edge_provenance,
    ensure_edge_schema,
    graph_client,
    mysql_engine,
    print_json,
    run_relation_extractor,
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


def _resolve_report_dir(payload: dict[str, Any], batch: str) -> Path:
    return Path(payload.get("report_dir") or f"/tmp/project-ingest-reports/{batch}")


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


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = _resolve_tables(vars(args))
    batch = args.ingest_batch or f"RELATION_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    candidates = _collect_candidates(args.database, tables, args.batch_size, args.limit, args.since)
    matcher = _load_matcher(candidates, args.dry_run)
    report = ProjectIngestReport(
        _resolve_report_dir(vars(args), batch),
        ingest_batch=batch,
        dry_run=args.dry_run,
    )
    summary = run_relation_extractor(
        database=args.database,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run,
        ingest_batch=batch,
        since=args.since,
        sources=[
            (table, PROJECT_SQL.format(table=table), make_has_participant_mapper(matcher, report))
            for table in tables
        ],
    )
    summary["report_dir"] = str(report.report_dir)
    summary["report"] = report.write()
    print_json(summary)


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    tables = _resolve_tables(payload)
    batch = common["ingest_batch"] or f"RELATION_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    candidates = _collect_candidates(
        common["database"], tables, common["batch_size"], common["limit"], common["since"]
    )
    matcher = _load_matcher(candidates, common["dry_run"])
    report = ProjectIngestReport(
        _resolve_report_dir(payload, batch),
        ingest_batch=batch,
        dry_run=common["dry_run"],
    )
    summary = run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=batch,
        since=common["since"],
        sources=[
            (table, PROJECT_SQL.format(table=table), make_has_participant_mapper(matcher, report))
            for table in tables
        ],
    )
    summary["report_dir"] = str(report.report_dir)
    summary["report"] = report.write()
    return summary


if __name__ == "__main__":
    main()
