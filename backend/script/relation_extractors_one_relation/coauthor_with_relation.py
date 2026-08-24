"""One-relation extractor: COAUTHOR_WITH（Person → Person）.

复刻旧 load_scholar_relations.py：dwd_scholar_coauthor（status=1），有向单条边，
属性 co_paper_count + 溯源 + 置信度三件套；REST merge_edge 按
source_record_id 幂等 upsert。Person 顶点由 person_entity.py 先行写入。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    edge_provenance,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT * FROM dwd_scholar_coauthor WHERE status = 1 ORDER BY scholar_id, co_scholar_id"


def coauthor_with(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    sid = str(row.get("scholar_id") or "").strip()
    co_sid = str(row.get("co_scholar_id") or "").strip()
    if not sid or not co_sid:
        return []
    record_id = f"{sid}_{co_sid}"
    props = {
        "co_paper_count": int(row.get("co_paper_count") or 0),
        "confidence": 1.0,
        "match_method": "source_primary_key",
        "match_evidence": "dwd_scholar_coauthor.scholar_id 主键直接抽取，未经推断",
        **edge_provenance(source_table=table, source_record_id=record_id, ingest_batch=batch),
    }
    return [
        EdgeRecord(
            "COAUTHOR_WITH",
            f"person_{sid}",
            f"person_{co_sid}",
            props,
            identity={"source_record_id": record_id},
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
            since=args.since,
            sources=[("dwd_scholar_coauthor", SQL, coauthor_with)],
        )
    )


if __name__ == "__main__":
    main()
