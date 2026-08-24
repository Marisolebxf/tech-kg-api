"""One-relation extractor: CHILD_OF（IndustryNode → 父 IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：parent_id 非空即建边，无属性，rank@0。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT * FROM dwd_industry_chain_info ORDER BY id"


def child_of(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    node_id = str(row.get("node_id") or "").strip()
    parent_id = str(row.get("parent_id") or "").strip()
    if not node_id or not parent_id:
        return []
    return [EdgeRecord("CHILD_OF", f"node_{node_id}", f"node_{parent_id}", {}, rank=0)]


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
            sources=[("dwd_industry_chain_info", SQL, child_of)],
        )
    )


if __name__ == "__main__":
    main()
