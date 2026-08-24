"""One-relation extractor: DOWNSTREAM_OF（IndustryNode → 下游 IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：downstream_link_code 非空即建边，
无属性，rank@0。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.downstream_of_relation --dry-run --limit 1``
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


def downstream_of(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    node_id = str(row.get("node_id") or "").strip()
    downstream = str(row.get("downstream_link_code") or "").strip()
    if not node_id or not downstream:
        return []
    return [EdgeRecord("DOWNSTREAM_OF", f"node_{node_id}", f"node_{downstream}", {}, rank=0)]


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_industry_chain_info", SQL, downstream_of)]


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
