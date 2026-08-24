"""One-entity extractor for News.

两个来源分别复刻旧脚本口径：

- ``dwd_org_important_news_info``：旧 organization_entity_etl.py
  （VID 含表名 + 整行哈希稳定键，动态置信度）。
- ``dwd_industry_chain_news_info``：旧 load_industry_chain_graph.py
  （news_{news_id}，缺 news_id 跳过，release_date 取源表 relaese_date 列）。

Dual-mode 入口：
- CLI: ``python -m script.entity_extractors_one_entity.news_entity --dry-run --limit 1``
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
from script.entity_extractors_one_entity.mappers import news_chain_record, news_org_record

TABLES = ("dwd_org_important_news_info", "dwd_industry_chain_news_info")

MAPPER_BY_TABLE = {
    "dwd_org_important_news_info": news_org_record,
    "dwd_industry_chain_news_info": news_chain_record,
}


def build_sources(payload: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """从 payload dict 构造 sources；CLI vars(args) 与 workflow payload 同形态。"""
    table_choice = payload.get("table", "all")
    tables = TABLES if table_choice == "all" else (table_choice,)
    return [
        (table, f"SELECT * FROM {table} ORDER BY 1", MAPPER_BY_TABLE[table]) for table in tables
    ]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources(vars(args))
    print_json(
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


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources(payload)
    return run_entity_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        since=common["since"],
        sources=sources,
    )


if __name__ == "__main__":
    main()
