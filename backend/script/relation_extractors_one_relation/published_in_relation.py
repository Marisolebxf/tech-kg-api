"""One-relation extractor: PUBLISHED_IN（Paper → Journal）.

复刻旧 paper_journal_chain_etl.py：dwd_zh/en_paper.publication_id 非空即建边，
边属性仅 confidence=1.0，rank@0（旧口径此边无溯源字段）。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import paper_source_id

TABLES = ("dwd_zh_paper", "dwd_en_paper")


def published_in(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("id"))
    jid = str(row.get("publication_id")) if row.get("publication_id") else ""
    if not pid or not jid:
        return []
    return [
        EdgeRecord(
            "PUBLISHED_IN",
            f"paper_{pid}",
            f"journal_{jid}",
            {"confidence": 1.0},
            rank=0,
        )
    ]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = TABLES if args.table == "all" else (args.table,)
    sources = [
        (
            table,
            f"SELECT id, publication_id, updated_time FROM {table} "
            "WHERE publication_id IS NOT NULL AND publication_id != ''",
            published_in,
        )
        for table in tables
    ]
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=sources,
        )
    )


if __name__ == "__main__":
    main()
