"""One-relation extractor: DOWNSTREAM_OF（IndustryNode → 下游 IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：downstream_link_code 非空即建边，
无属性，rank@0。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT * FROM dwd_industry_chain_info ORDER BY id"


def downstream_of(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    node_id = str(row.get("node_id") or "").strip()
    downstream = str(row.get("downstream_link_code") or "").strip()
    if not node_id or not downstream:
        return []
    return [EdgeRecord("DOWNSTREAM_OF", f"node_{node_id}", f"node_{downstream}", {}, rank=0)]


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
            sources=[("dwd_industry_chain_info", SQL, downstream_of)],
        )
    )


if __name__ == "__main__":
    main()
