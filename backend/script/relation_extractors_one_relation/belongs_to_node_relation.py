"""One-relation extractor: BELONGS_TO_NODE（Organization → IndustryNode）.

复刻旧 load_industry_chain_graph.py 口径：dwd_org_industry_chain_dtl，
org 端 VID = org_{antitypic}，仅当图中已存在该 Organization 才建边
（写层端点验存，防悬挂）；chain_score 数值，解析失败落 0.0。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
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
            sources=[("dwd_org_industry_chain_dtl", SQL, belongs_to_node)],
        )
    )


if __name__ == "__main__":
    main()
