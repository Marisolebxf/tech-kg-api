"""One-relation extractor: CITES（Patent → Patent，专利域匹配边）.

复刻旧 load_patent_relations.py 口径：

- 源 ``dwd_patent_cited``：``patent_citations`` 为正向引用（当前专利 → 被引
  专利），``cited_by`` 为反向引用（被引专利 → 当前专利）；
- 标识符经 ``patent_candidates`` 双格式查找（patent_id/publication_number/
  granted_number 通用规范化 + 申请号 CN 格式归一），候选唯一才建边，自环跳过；
- confidence=1.0，match_method=exact_patent_identifier；
- 旧 ``deduplicate_edges`` 将 CITES 归 rank@0 并按 (src,dst) 去重、同键保留
  confidence 更高者（本边恒为 1.0，即保留首条）——新实现 rank=0 +
  框架 ``dedupe="first"``；
- 候选索引 ``identifier_index`` 由图内 Patent（限定 dwd_patent.patent_id 集合）
  查询构建，端点直接取图内真实 vid，不做端点验存。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.patent_cites_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from collections import Counter
from typing import Any

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    apply_since,
    build_parser,
    common_args_from_payload,
    configure_logging,
    ensure_edge_schema,
    graph_client,
    mysql_engine,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.patent_matching import (
    EDGE_PROPERTY_SCHEMAS,
    parse_json,
    patent_candidates,
    patent_indexes,
)

SOURCE_SQL = (
    "SELECT id, patent_id, patent_citations, cited_by FROM dwd_patent_cited ORDER BY patent_id"
)


def cites_mapper(index: dict[str, list[str]], stats: Counter):
    def mapper(table: str, row: dict, batch: str) -> list[EdgeRecord]:
        current = patent_candidates(index, row.get("patent_id"))
        if len(current) != 1:
            stats["CITES:missing_source"] += 1
            return []
        records: list[EdgeRecord] = []
        for column in ("patent_citations", "cited_by"):
            for sequence, identifier in enumerate(parse_json(row.get(column), []), start=1):
                candidates = patent_candidates(index, identifier)
                if len(candidates) != 1:
                    stats["CITES:unmatched_target"] += 1
                    continue
                source_vid, target_vid = (
                    (current[0], candidates[0])
                    if column == "patent_citations"
                    else (candidates[0], current[0])
                )
                if source_vid == target_vid:
                    continue
                stats["CITES:exact"] += 1
                records.append(
                    EdgeRecord(
                        "CITES",
                        source_vid,
                        target_vid,
                        {
                            "reference_identifier": str(identifier),
                            "sequence": sequence,
                            "confidence": 1.0,
                            "match_method": "exact_patent_identifier",
                            "match_evidence": "引用专利号与现有Patent唯一精确匹配",
                            "source_table": "dwd_patent_cited",
                            "source_record_id": f"{row['id']}:{column}:{sequence}",
                        },
                        rank=0,
                    )
                )
        return records

    return mapper


def _load_index(database: str, dry_run: bool) -> dict[str, list[str]]:
    """连图连库构建 patent_index；dry_run 时也连图（旧口径如此）。"""
    engine = mysql_engine(database)
    graph = graph_client()
    try:
        _, patent_index = patent_indexes(graph, engine)
        if not dry_run:
            ensure_edge_schema(graph, "CITES", EDGE_PROPERTY_SCHEMAS["CITES"])
    finally:
        graph.close()
    engine.dispose()
    return patent_index


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    patent_index = _load_index(args.database, args.dry_run)
    stats: Counter = Counter()
    summary = run_relation_extractor(
        database=args.database,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run,
        ingest_batch=args.ingest_batch,
        sources=[
            (
                "dwd_patent_cited",
                # 旧表无 updated_time，增量水位走 update_time 列。
                apply_since(SOURCE_SQL, args.since, col="update_time"),
                cites_mapper(patent_index, stats),
            )
        ],
        # since 已预应用到 SQL（update_time 列），此处只补绑定参数。
        extra_params={"since": args.since} if args.since else None,
        dedupe="first",
    )
    summary["sources"]["dwd_patent_cited"].update(stats)
    print_json(summary)


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    patent_index = _load_index(common["database"], common["dry_run"])
    stats: Counter = Counter()
    summary = run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        sources=[
            (
                "dwd_patent_cited",
                # 旧表无 updated_time，增量水位走 update_time 列。
                apply_since(SOURCE_SQL, common["since"], col="update_time"),
                cites_mapper(patent_index, stats),
            )
        ],
        extra_params={"since": common["since"]} if common["since"] else None,
        dedupe="first",
    )
    summary["sources"]["dwd_patent_cited"].update(stats)
    return summary


if __name__ == "__main__":
    main()
