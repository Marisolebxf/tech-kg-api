"""One-relation extractor: BELONGS_TO_NODE（Organization → IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：dwd_org_industry_chain_dtl，
org 端 VID = org_{antitypic}，仅当图中已存在该 Organization 才建边
（写层端点验存，防悬挂）；chain_score 数值，解析失败落 0.0。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.belongs_to_node_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    now_utc,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT * FROM dwd_org_industry_chain_dtl ORDER BY 1"


def belongs_to_node(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    antitypic = str(row.get("antitypic") or "").strip()
    node_id = str(row.get("node_id") or "").strip()
    if not antitypic or not node_id:
        return []
    try:
        chain_score = float(row.get("chain_score") or 0)
    except (TypeError, ValueError):
        chain_score = 0.0
    return [
        EdgeRecord(
            "BELONGS_TO_NODE",
            f"org_{antitypic}",
            f"node_{node_id}",
            {
                "chain_score": chain_score,
                "source_table": table,
                "source_record_id": antitypic,
                "ingest_batch": batch,
                "ingest_time": now_utc(),
            },
            rank=0,
            source_tag="Organization",
            target_tag="IndustryNode",
        )
    ]


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_org_industry_chain_dtl", SQL, belongs_to_node)]


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
