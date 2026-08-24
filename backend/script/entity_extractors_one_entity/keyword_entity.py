"""One-entity extractor for Keyword.

关键词来源：学者研究方向、论文分类、项目表、专利关键词（复用专利聚合 SQL，
keyset 游标分页）。VID 为 keyword_{md5(lower(keyword))} 完整 32 位。
"""

from typing import Any

from script.entity_extractors_one_entity.common import (
    build_parser,
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


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES, "dwd_patent"), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    include_patent = args.table in ("all", "dwd_patent")
    tables = TABLES if args.table == "all" else ()
    if args.table in TABLES:
        tables = (args.table,)
    summary: dict[str, Any] = {}
    if tables:
        sources = [
            (table, f"SELECT * FROM {table} ORDER BY 1", keyword_records) for table in tables
        ]
        summary.update(
            run_entity_extractor(
                database=args.database,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
                ingest_batch=args.ingest_batch,
                since=args.since,
                sources=sources,
            )
        )
    if include_patent:
        patent_summary = run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=[("dwd_patent", PATENT_SQL, keyword_records)],
            cursor_column="source_row_id",
        )
        summary.setdefault("sources", {}).update(patent_summary["sources"])
        summary.setdefault("ingest_batch", patent_summary["ingest_batch"])
    print_json(summary)


if __name__ == "__main__":
    main()
