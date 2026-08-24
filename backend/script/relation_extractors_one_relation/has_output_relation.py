"""One-relation extractor: HAS_OUTPUT（Project → Paper/Patent/Report）.

复刻旧 load_project_graph.py stage_outputs 口径：dwd_zh/en_project_output JOIN
项目表（等价旧 allowed_ids 过滤：产出所属项目必须存在于 zh/en 项目表之一），
按 OUTPUT_FIELDS 展开 JSON 产出并走 ProjectEntityMatcher 匹配链——paper：doi
精确→title|year→title；patent：号码精确→标题；report：title|year→title。
仅 matched 写边；ambiguous/not_found 进 ProjectIngestReport 复核目录。
source_record_id = ``{project_id}|{output_type}|{target_vid}``，REST merge_edge 按
其幂等。不做 update_node 产出计数回填（project_entity.py 实体侧职责）；
跨域 OUTPUT_OF（dwd_rel_project_paper/patent）只写报告分类，不建边。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.has_output_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from script.project_entity_matcher import (
    ProjectEntityMatcher,
    normalize_doi,
    normalize_patent_number,
)
from script.project_graph_utils import match_audit_props, parse_json_objects
from script.project_ingest_report import ProjectIngestReport
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    apply_since,
    build_parser,
    common_args_from_payload,
    configure_logging,
    ensure_edge_schema,
    graph_client,
    iter_rows,
    mysql_engine,
    now_utc,
    print_json,
    run_relation_extractor,
)

TABLES = ("dwd_zh_project_output", "dwd_en_project_output")
PROJECT_TABLES = ("dwd_zh_project", "dwd_en_project")
# 旧 OUTPUT_FIELDS：字段 → output_type → target_type。
OUTPUT_FIELDS = (
    ("output_journal_articles", "journal_article", "paper"),
    ("output_conference_papers", "conference_paper", "paper"),
    ("output_degree_papers", "degree_paper", "paper"),
    ("output_patents", "patent", "patent"),
    ("output_reports", "report", "report"),
)
TARGET_TAGS = {"paper": "Paper", "patent": "Patent", "report": "Report"}

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


def output_sql(table: str) -> str:
    """产出表 JOIN 项目 ID 全集（等价旧 allowed_ids = zh∪en 项目 ID）。"""
    project_ids = " UNION ALL ".join(f"SELECT id FROM {name}" for name in PROJECT_TABLES)
    return f"SELECT o.* FROM {table} o JOIN ({project_ids}) p ON p.id = o.id"


def _add(target: set[str], value: Any) -> None:
    cleaned = str(value or "").strip()
    if cleaned:
        target.add(cleaned)


def _output_title(item: dict[str, Any]) -> str:
    return str(item.get("patent_title") or item.get("title") or "")


def _output_identifier(item: dict[str, Any]) -> str:
    return str(
        item.get("doi")
        or item.get("patent_number")
        or item.get("application_number")
        or item.get("publication_number")
        or item.get("patent_id")
        or ""
    )


def collect_output_candidates(
    engine: Any,
    tables: tuple[str, ...],
    *,
    batch_size: int,
    limit: int | None,
    since: str | None,
) -> dict[str, set[str]]:
    """旧 collect_match_candidates 的产出通道（paper/patent/report 候选）。"""
    candidates = {key: set() for key in EMPTY_CANDIDATES}
    for table in tables:
        sql = output_sql(table)
        if since:
            sql = apply_since(sql, since, col="o.updated_time")
        params = {"since": since} if since else None
        for row in iter_rows(engine, sql, batch_size=batch_size, limit=limit, params=params):
            for field in (
                "output_journal_articles",
                "output_conference_papers",
                "output_degree_papers",
            ):
                for item in parse_json_objects(row.get(field)):
                    _add(candidates["paper_doi"], item.get("doi"))
                    _add(candidates["paper_doi"], normalize_doi(item.get("doi")))
                    _add(candidates["paper_title"], item.get("title"))
            for item in parse_json_objects(row.get("output_patents")):
                number = (
                    item.get("patent_number")
                    or item.get("application_number")
                    or item.get("publication_number")
                    or item.get("patent_id")
                )
                _add(candidates["patent_number"], number)
                _add(candidates["patent_number"], normalize_patent_number(number))
                _add(candidates["patent_title"], item.get("patent_title") or item.get("title"))
            for item in parse_json_objects(row.get("output_reports")):
                _add(candidates["report_title"], item.get("title"))
    return candidates


def collect_all_project_ids(engine: Any) -> set[str]:
    """旧 allowed_ids 全量口径：zh/en 项目表全部项目 ID。"""
    ids: set[str] = set()
    with engine.connect() as conn:
        for table in PROJECT_TABLES:
            for row in conn.execute(text(f"SELECT id FROM `{table}`")):
                ids.add(str(row[0]))
    return ids


def report_output_of_candidates(
    engine: Any,
    report: ProjectIngestReport,
    *,
    allowed_ids: set[str],
) -> None:
    """旧 stage_rel_table_candidates：跨域 OUTPUT_OF 只记报告，不建边。"""
    for table, source_column, owner in (
        ("dwd_rel_project_paper", "paper_id", "paper"),
        ("dwd_rel_project_patent", "patent_id", "patent"),
    ):
        with engine.connect() as conn:
            exists = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_name=:table"
                ),
                {"table": table},
            ).scalar()
            if not exists:
                continue
            rows = conn.execute(
                text(f"SELECT project_id, {source_column} AS source_id FROM `{table}`")
            ).mappings()
            for row in rows:
                if str(row["project_id"]) in allowed_ids:
                    report.add(
                        "cross_domain",
                        {
                            "project_id": str(row["project_id"]),
                            "relation": "OUTPUT_OF",
                            "owner_domain": owner,
                            "source_id": str(row["source_id"]),
                            "source_table": table,
                        },
                    )


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
        for field, output_type, target_type in OUTPUT_FIELDS:
            for item in parse_json_objects(row.get(field)):
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
) -> dict[str, set[str]]:
    """连 MySQL 收集 paper/patent/report 候选。"""
    engine = mysql_engine(database)
    try:
        return collect_output_candidates(
            engine,
            tables,
            batch_size=batch_size,
            limit=limit,
            since=since,
        )
    finally:
        engine.dispose()


def _load_matcher(candidates: dict[str, set[str]], dry_run: bool) -> ProjectEntityMatcher:
    graph = graph_client()
    try:
        matcher = ProjectEntityMatcher.from_graph(graph, candidates)
        if not dry_run:
            ensure_edge_schema(graph, "HAS_OUTPUT", EDGE_SCHEMA)
    finally:
        graph.close()
    return matcher


def _build_sources(
    tables: tuple[str, ...],
    since: str | None,
    matcher: ProjectEntityMatcher,
    report: ProjectIngestReport,
) -> list[tuple[str, str, Callable[[str, dict[str, Any], str], list[EdgeRecord]]]]:
    sources = []
    for table in tables:
        sql = output_sql(table)
        if since:
            sql = apply_since(sql, since, col="o.updated_time")
        sources.append((table, sql, make_has_output_mapper(matcher, report)))
    return sources


def _report_cross_domain(database: str, report: ProjectIngestReport) -> None:
    """跨域 OUTPUT_OF 报告（旧 main 末尾那段，独立连 MySQL）。"""
    engine = mysql_engine(database)
    try:
        report_output_of_candidates(engine, report, allowed_ids=collect_all_project_ids(engine))
    finally:
        engine.dispose()


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
    sources = _build_sources(tables, args.since, matcher, report)
    summary = run_relation_extractor(
        database=args.database,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run,
        ingest_batch=batch,
        # since 已按 o.updated_time 预注入（JOIN 下默认列名有歧义）。
        sources=sources,
        extra_params={"since": args.since} if args.since else None,
    )
    _report_cross_domain(args.database, report)
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
    sources = _build_sources(tables, common["since"], matcher, report)
    summary = run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=batch,
        sources=sources,
        extra_params={"since": common["since"]} if common["since"] else None,
    )
    _report_cross_domain(common["database"], report)
    summary["report_dir"] = str(report.report_dir)
    summary["report"] = report.write()
    return summary


if __name__ == "__main__":
    main()
