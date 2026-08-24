"""One-relation extractor: HAS_NODE（IndustryChain → IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：chain_code 非空即建边，无属性，
rank@0 覆盖幂等。IndustryChain/IndustryNode 顶点由实体脚本先行写入。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.has_node_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT * FROM dwd_industry_chain_info ORDER BY chain_code"


def has_node(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    chain_code = str(row.get("chain_code") or "").strip()
    node_id = str(row.get("node_id") or "").strip()
    if not chain_code or not node_id:
        return []
    return [
        EdgeRecord(
            "HAS_NODE",
            f"chain_{chain_code}",
            f"node_{node_id}",
            {},
            rank=0,
        )
    ]


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_industry_chain_info", SQL, has_node)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources()
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=sources,
        )
    )


def workflow(payload: dict) -> dict:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources()
    return run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        sources=sources,
    )


if __name__ == "__main__":
    main()
