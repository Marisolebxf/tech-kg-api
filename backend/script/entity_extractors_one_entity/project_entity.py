"""One-entity extractor for Project.

复刻旧 load_project_graph.py 口径：--project-id/--id-prefix 定向过滤、
limit 跨 zh/en 全局截断、置信度按核心字段完整度打分。

Dual-mode 入口：
- CLI: ``python -m script.entity_extractors_one_entity.project_entity --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from __future__ import annotations

from typing import Any

from script.entity_extractors_one_entity.common import (
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import project_record

TABLES = ("dwd_zh_project", "dwd_en_project")

SQL_BY_TABLE = {
    "dwd_zh_project": """
        SELECT p.*, o.total_outputs, o.journal_articles_count, o.conference_papers_count,
               o.books_count, o.degree_papers_count, o.patents_count, 0 AS clinical_trials_count,
               0 AS products_count, o.awards_count, o.reports_count, o.other_outputs_count
        FROM dwd_zh_project p
        LEFT JOIN dwd_zh_project_output o ON o.id = p.id
        {row_filter}
        ORDER BY p.id
    """,
    "dwd_en_project": """
        SELECT p.*, o.total_outputs, o.journal_articles_count, o.conference_papers_count,
               o.books_count, o.degree_papers_count, o.patents_count, o.clinical_trials_count,
               0 AS products_count, o.awards_count, o.reports_count, o.other_outputs_count
        FROM dwd_en_project p
        LEFT JOIN dwd_en_project_output o ON o.id = p.id
        {row_filter}
        ORDER BY p.id
    """,
}


def build_sources(payload: dict[str, Any]) -> tuple[list[tuple[str, str, Any]], dict[str, Any]]:
    """从 payload dict 构造 (sources, extra_params)；CLI vars(args) 与 workflow payload 同形态。"""
    table_choice = payload.get("table", "all")
    tables = TABLES if table_choice == "all" else (table_choice,)
    project_id = payload.get("project_id")
    id_prefix = payload.get("id_prefix")
    row_filter = ""
    extra_params: dict[str, Any] = {}
    if project_id:
        row_filter = "WHERE p.id = :project_id"
        extra_params["project_id"] = project_id
    elif id_prefix:
        row_filter = "WHERE p.id LIKE :id_prefix"
        extra_params["id_prefix"] = f"{id_prefix}%"
    sources = [
        (table, SQL_BY_TABLE[table].format(row_filter=row_filter), project_record)
        for table in tables
    ]
    return sources, extra_params


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    parser.add_argument("--project-id", help="只装载指定 ID 的项目（旧 --id）")
    parser.add_argument("--id-prefix", help="只装载 ID 前缀匹配的项目（旧 --id-prefix）")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources, extra_params = build_sources(vars(args))
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=sources,
            global_limit=True,
            extra_params=extra_params,
        )
    )


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources, extra_params = build_sources(payload)
    return run_entity_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        since=common["since"],
        sources=sources,
        global_limit=True,
        extra_params=extra_params,
    )


if __name__ == "__main__":
    main()
