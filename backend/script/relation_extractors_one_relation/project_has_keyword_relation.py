"""One-relation transform for HAS_KEYWORD（Project → Keyword）（平台喂数抽取：只输出边 JSON）.

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

"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from script.extract_transform_common import edge_transform
from script.project_entity_matcher import normalize_text
from script.project_graph_utils import parse_list
from script.project_ingest_report import ProjectIngestReport
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    edge_provenance,
    ensure_edge_schema,
    graph_client,
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


SOURCES = [
    {"table": t, "pk": "id", "time": "update_time", "query_sql": f"SELECT * FROM {t}"}
    for t in TABLES
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
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
