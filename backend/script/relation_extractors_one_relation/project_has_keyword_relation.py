"""One-relation extractor: HAS_KEYWORD（Project → Keyword）.

复刻旧 load_project_graph.py stage_keywords 口径：dwd_zh/en_project.keywords 按
parse_list 解析、normalize_text 去重排序，每个关键词一条边；边属性仅溯源四件套
（无 confidence / match 审计列，旧口径如此）。REST merge_edge 按
source_record_id（= 项目 ID）幂等。

与旧脚本的两处有意偏差（拆分设计声明的统一决策，见 resolvers 模块说明）：

- Keyword 端点 VID 改用三域统一公式 ``resolvers.keyword_vid``
  （NFKC+空白折叠+casefold 后完整 md5）；旧项目域公式为 md5(lower(keyword))，
  与专利/论文域不一致。
- 本脚本不再创建 Keyword 顶点（keyword_entity.py 已承接）；Keyword 端点不验存，
  以兼容实体侧解析口径差异产生的悬空目标（旧脚本在写边时顺手建点）。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.project_has_keyword_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from script.project_entity_matcher import normalize_text
from script.project_graph_utils import parse_list
from script.project_ingest_report import ProjectIngestReport
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    edge_provenance,
    ensure_edge_schema,
    graph_client,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import keyword_vid

TABLES = ("dwd_zh_project", "dwd_en_project")
PROJECT_SQL = "SELECT * FROM {table} ORDER BY id"

EDGE_SCHEMA = {
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
}


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


def build_sources(
    tables: tuple[str, ...],
    report: ProjectIngestReport,
) -> list[tuple[str, str, Callable[[str, dict[str, Any], str], list[EdgeRecord]]]]:
    """构造 sources；report 由 main/workflow 共享同一实例（汇总到 report.write）。"""
    return [
        (table, PROJECT_SQL.format(table=table), make_project_has_keyword_mapper(report))
        for table in tables
    ]


def _resolve_tables(payload: dict[str, Any]) -> tuple[str, ...]:
    table_choice = payload.get("table", "all")
    return TABLES if table_choice == "all" else (str(table_choice),)


def _resolve_report_dir(payload: dict[str, Any], batch: str) -> Path:
    return Path(payload.get("report_dir") or f"/tmp/project-ingest-reports/{batch}")


def _ensure_schema(dry_run: bool) -> None:
    if dry_run:
        return
    graph = graph_client()
    try:
        ensure_edge_schema(graph, "HAS_KEYWORD", EDGE_SCHEMA)
    finally:
        graph.close()


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = _resolve_tables(vars(args))
    batch = args.ingest_batch or f"RELATION_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    _ensure_schema(args.dry_run)
    report = ProjectIngestReport(
        _resolve_report_dir(vars(args), batch),
        ingest_batch=batch,
        dry_run=args.dry_run,
    )
    sources = build_sources(tables, report)
    summary = run_relation_extractor(
        database=args.database,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run,
        ingest_batch=batch,
        since=args.since,
        sources=sources,
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
    _ensure_schema(common["dry_run"])
    report = ProjectIngestReport(
        _resolve_report_dir(payload, batch),
        ingest_batch=batch,
        dry_run=common["dry_run"],
    )
    sources = build_sources(tables, report)
    summary = run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=batch,
        since=common["since"],
        sources=sources,
    )
    summary["report_dir"] = str(report.report_dir)
    summary["report"] = report.write()
    return summary


if __name__ == "__main__":
    main()
