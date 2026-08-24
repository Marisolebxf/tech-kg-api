"""One-relation extractor: COAUTHOR_WITH（Person → Person）.

复刻旧 load_scholar_relations.py：dwd_scholar_coauthor（status=1），有向单条边，
属性 co_paper_count + 溯源 + 置信度三件套；REST merge_edge 按
source_record_id 幂等 upsert。Person 顶点由 person_entity.py 先行写入。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.coauthor_with_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
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


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_scholar_coauthor", SQL, coauthor_with)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources()
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


def workflow(payload: dict) -> dict:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources()
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
