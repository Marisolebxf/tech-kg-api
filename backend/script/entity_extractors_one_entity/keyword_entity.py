"""One-entity extractor for Keyword.

关键词来源：学者研究方向、论文分类、项目表、专利关键词（复用专利聚合 SQL，
keyset 游标分页）。VID 为 keyword_{md5(lower(keyword))} 完整 32 位。

Dual-mode 入口：
- CLI: ``python -m script.entity_extractors_one_entity.keyword_entity --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from typing import Any

from script.entity_extractors_one_entity.common import (
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import keyword_records
from script.entity_extractors_one_entity.patent_entity import PATENT_SQL

TABLES = (
    "dwd_scholar_research_direction",
    "dwd_zh_paper_classification",
    "dwd_en_paper_classification",
    "dwd_zh_project",
    "dwd_en_project",
)


def _build_keyword_sources(tables: tuple[str, ...]) -> list[tuple[str, str, Any]]:
    return [(table, f"SELECT * FROM {table} ORDER BY 1", keyword_records) for table in tables]


def build_sources(
    payload: dict[str, Any],
) -> tuple[list[tuple[str, str, Any]], list[tuple[str, str, Any]]]:
    """从 payload dict 构造 (keyword_sources, patent_sources)；同形态 vars(args)/payload。

    返回两个 sources 列表：普通 keyword 表 + 专利 keyword 表（keyset 游标分页），
    供 main/workflow 分别喂给 run_entity_extractor。
    """
    table_choice = payload.get("table", "all")
    include_patent = table_choice in ("all", "dwd_patent")
    tables = TABLES if table_choice == "all" else ()
    if table_choice in TABLES:
        tables = (table_choice,)
    keyword_sources = _build_keyword_sources(tables) if tables else []
    patent_sources = [("dwd_patent", PATENT_SQL, keyword_records)] if include_patent else []
    return keyword_sources, patent_sources


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES, "dwd_patent"), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    keyword_sources, patent_sources = build_sources(vars(args))
    summary: dict[str, Any] = {}
    if keyword_sources:
        summary.update(
            run_entity_extractor(
                database=args.database,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
                ingest_batch=args.ingest_batch,
                since=args.since,
                sources=keyword_sources,
            )
        )
    if patent_sources:
        patent_summary = run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=patent_sources,
            cursor_column="source_row_id",
        )
        summary.setdefault("sources", {}).update(patent_summary["sources"])
        summary.setdefault("ingest_batch", patent_summary["ingest_batch"])
    print_json(summary)


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    keyword_sources, patent_sources = build_sources(payload)
    summary: dict[str, Any] = {}
    if keyword_sources:
        summary.update(
            run_entity_extractor(
                database=common["database"],
                batch_size=common["batch_size"],
                limit=common["limit"],
                dry_run=common["dry_run"],
                ingest_batch=common["ingest_batch"],
                since=common["since"],
                sources=keyword_sources,
            )
        )
    if patent_sources:
        patent_summary = run_entity_extractor(
            database=common["database"],
            batch_size=common["batch_size"],
            limit=common["limit"],
            dry_run=common["dry_run"],
            ingest_batch=common["ingest_batch"],
            sources=patent_sources,
            cursor_column="source_row_id",
        )
        summary.setdefault("sources", {}).update(patent_summary["sources"])
        summary.setdefault("ingest_batch", patent_summary["ingest_batch"])
    return summary


if __name__ == "__main__":
    main()
