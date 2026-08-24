"""One-relation extractor: MEMBER_OF_FAMILY（Patent → PatentFamily）.

复刻旧 load_patent_graph.py family_statements 口径：simple_family_number 与
patent_id 均非空即建边，属性 (confidence=1.0, match_method=source_family_number,
match_evidence, source_table=dwd_patent_family, source_record_id=patent_id)，
rank@0。PatentFamily 顶点由 patent_family_entity.py 先行写入。
"""

from script.entity_extractors_one_entity.patent_entity import PATENT_SQL
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)


def member_of_family(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    number = str(row.get("simple_family_number") or "").strip()
    patent_id = str(row.get("patent_id") or "").strip()
    if not number or not patent_id:
        return []
    return [
        EdgeRecord(
            "MEMBER_OF_FAMILY",
            f"patent_{patent_id}",
            f"patent_family_{number}",
            {
                "confidence": 1.0,
                "match_method": "source_family_number",
                "match_evidence": "simple_family_number由源表直接给出",
                "source_table": "dwd_patent_family",
                "source_record_id": patent_id,
            },
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
            sources=[("dwd_patent", PATENT_SQL, member_of_family)],
            cursor_column="source_row_id",
        )
    )


if __name__ == "__main__":
    main()
