"""One-relation extractor: CITES / CITED_BY / RELATED_TO（Paper → DOI 桩）.

复刻旧 paper_journal_chain_etl.py 口径：目标论文顶点不存在，终点为 DOI 的
16 位 md5 桩（paper_ref_ / paper_cit_ / paper_rel_ 前缀），桩端点允许悬空，
后续由论文桩对齐流程认领。CITES/CITED_BY confidence=0.5，RELATED_TO=0.7。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.paper_cites_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from typing import Any

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
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


def build_sources(payload: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """从 payload dict 构造 sources；CLI vars(args) 与 workflow payload 同形态。"""
    table_choice = payload.get("table", "all")
    tables = tuple(CONFIG_BY_TABLE) if table_choice == "all" else (table_choice,)
    return [
        (
            table,
            f"SELECT id, doi, updated_time FROM {table} WHERE doi IS NOT NULL AND doi != ''",
            paper_cites,
        )
        for table in tables
    ]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *CONFIG_BY_TABLE), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources(vars(args))
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


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources(payload)
    return run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        since=common["since"],
        sources=sources,
    )


if __name__ == "__main__":
    main()
