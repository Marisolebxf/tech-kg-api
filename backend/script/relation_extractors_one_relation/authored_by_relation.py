"""One-relation extractor: AUTHORED_BY（Paper → Person，论文工作流口径）.

复刻旧 paper_journal_chain_etl.py：dwd_zh/en_author，paper 端去 ``__数字``
后缀，author_id 非空；边属性 (author_order, is_corresponding, confidence=1.0)，
rank@0。Person 顶点由 person_entity.py --source paper-author 先行写入。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import paper_source_id

TABLES = ("dwd_zh_author", "dwd_en_author")


def authored_by(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("paper_id"))
    aid = str(row.get("author_id")) if row.get("author_id") else ""
    if not pid or not aid:
        return []
    return [
        EdgeRecord(
            "AUTHORED_BY",
            f"paper_{pid}",
            f"person_{aid}",
            {
                "author_order": str(row.get("author_sequence"))
                if row.get("author_sequence") is not None
                else "",
                "is_corresponding": str(row.get("correspond"))
                if row.get("correspond") is not None
                else "",
                "confidence": 1.0,
            },
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
        (table, f"SELECT * FROM {table} ORDER BY paper_id, author_id", authored_by)
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
