"""One-relation extractor: HAS_NODE（IndustryChain → IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：chain_code 非空即建边，无属性，
rank@0 覆盖幂等。IndustryChain/IndustryNode 顶点由实体脚本先行写入。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT * FROM dwd_industry_chain_info ORDER BY id"


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


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=[("dwd_industry_chain_info", SQL, has_node)],
        )
    )


if __name__ == "__main__":
    main()
