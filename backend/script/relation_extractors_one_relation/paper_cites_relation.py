"""One-relation extractor: CITES / CITED_BY / RELATED_TO（Paper → DOI 桩）.

复刻旧 paper_journal_chain_etl.py 口径：目标论文顶点不存在，终点为 DOI 的
16 位 md5 桩（paper_ref_ / paper_cit_ / paper_rel_ 前缀），桩端点允许悬空，
后续由论文桩对齐流程认领。CITES/CITED_BY confidence=0.5，RELATED_TO=0.7。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    configure_logging,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import paper_source_id, paper_stub_vid

# (表, 边类型, 桩前缀, 标识字段, confidence)
CONFIGS = (
    ("dwd_zh_paper_reference", "CITES", "paper_ref", "reference_identifier", 0.5),
    ("dwd_en_paper_reference", "CITES", "paper_ref", "reference_identifier", 0.5),
    ("dwd_zh_paper_citation", "CITED_BY", "paper_cit", "citation_identifier", 0.5),
    ("dwd_en_paper_citation", "CITED_BY", "paper_cit", "citation_identifier", 0.5),
    ("dwd_zh_paper_related", "RELATED_TO", "paper_rel", None, 0.7),
    ("dwd_en_paper_related", "RELATED_TO", "paper_rel", None, 0.7),
)

CONFIG_BY_TABLE = {config[0]: config for config in CONFIGS}


def paper_cites(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    _, edge_type, stub_prefix, id_field, confidence = CONFIG_BY_TABLE[table]
    pid = paper_source_id(row.get("id"))
    doi = str(row.get("doi") or "").strip()
    if not pid or not doi:
        return []
    props: dict = {"confidence": confidence}
    if id_field:
        props[id_field] = doi
    return [
        EdgeRecord(
            edge_type,
            f"paper_{pid}",
            paper_stub_vid(stub_prefix, doi),
            props,
            rank=0,
            validate_endpoints=False,
        )
    ]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *CONFIG_BY_TABLE), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    tables = tuple(CONFIG_BY_TABLE) if args.table == "all" else (args.table,)
    sources = [
        (
            table,
            f"SELECT id, doi, updated_time FROM {table} WHERE doi IS NOT NULL AND doi != ''",
            paper_cites,
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
