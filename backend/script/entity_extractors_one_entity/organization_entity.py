"""One-entity extractor for Organization.

表集合与字段映射复刻旧 organization_entity_etl.py（含 dwd_org_stock_base 在内
的 10 张 Organization 表；enrichment 表稀疏行只下发非空字段）。

Dual-mode 入口：
- CLI: ``python -m script.entity_extractors_one_entity.organization_entity --dry-run --limit 1``
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
from script.entity_extractors_one_entity.mappers import organization_record
from script.entity_extractors_one_entity.org_catalog import ORGANIZATION_TABLES


def build_sources(payload: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """从 payload dict 构造 sources；CLI vars(args) 与 workflow payload 同形态。"""
    table_choice = payload.get("table", "all")
    tables = ORGANIZATION_TABLES if table_choice == "all" else (table_choice,)
    return [(table, f"SELECT * FROM {table} ORDER BY 1", organization_record) for table in tables]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *ORGANIZATION_TABLES), default="all")
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
