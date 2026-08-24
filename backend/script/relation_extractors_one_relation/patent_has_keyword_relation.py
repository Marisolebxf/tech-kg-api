"""One-relation extractor: HAS_KEYWORD（Patent → Keyword，专利域）.

复刻旧 load_patent_graph.py 口径：解析 dwd_patent.keywords JSON 数组
（NFKC 归一 + 去重），边属性 (confidence=1.0, source_table=dwd_patent,
source_record_id=patent_id)，rank@0。Keyword 顶点由 keyword_entity.py 先行写入。
"""

from script.entity_extractors_one_entity.mappers import _keyword_values
from script.entity_extractors_one_entity.patent_entity import PATENT_SQL
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import keyword_vid


def patent_has_keyword(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    patent_id = str(row.get("patent_id") or "").strip()
    if not patent_id:
        return []
    records = []
    for keyword in _keyword_values(row.get("keywords")):
        records.append(
            EdgeRecord(
                "HAS_KEYWORD",
                f"patent_{patent_id}",
                keyword_vid(keyword),
                {
                    "confidence": 1.0,
                    "source_table": "dwd_patent",
                    "source_record_id": patent_id,
                },
                rank=0,
            )
        )
    return records


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
            sources=[("dwd_patent", PATENT_SQL, patent_has_keyword)],
            cursor_column="source_row_id",
        )
    )


if __name__ == "__main__":
    main()
