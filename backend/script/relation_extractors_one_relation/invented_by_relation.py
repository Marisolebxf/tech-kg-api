"""One-relation extractor: INVENTED_BY（Patent → Person，专利域匹配边）.

复刻旧 load_patent_relations.py 口径：

- 源 ``dwd_patent``（id/patent_id/inventors/applicants/assignees）；
- 发明人姓名精确命中 person 索引（图内 Person 限 source_table=dwd_scholar，
  dwd_scholar 行补充机构经历）后，用「申请人/权利机构名 ∩ 候选人任职机构」
  （confirmed_org_names）二次确认：机构一致且项目证据一致 0.90
  （exact_name_org_project）、仅机构一致且候选唯一 0.80（exact_name_org）；
- 项目证据来自旧 ``project_context``：项目 host/participants/
  funded_institution/participating_institution 名称集合，按产出专利号唯一匹配
  到的 patent_vid 累积（仅图内已有 Project 的行）；
- 未唯一确认 → 不自动建边，写 review JSONL（output/ 目录，字段与旧一致）；
- rank=发明人数组序号，同 (edge,src,dst,rank) 去重保留 confidence 高者；
- 旧脚本的 Milvus 向量提升为可选对齐步骤，不在本脚本迁移。

Person/Organization/Patent 端点直接取图内真实 vid，不做端点验存。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.invented_by_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from collections import Counter
from pathlib import Path
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
    ReviewRecord,
    candidate_view,
    canonical_entities,
    make_edge_deduper,
    make_index,
    names_from,
    normalize_name,
    party_items,
    patent_indexes,
    person_org_names,
    project_evidence_context,
    write_reviews,
)

SOURCE_SQL = (
    "SELECT id, patent_id, inventors, applicants, assignees FROM dwd_patent ORDER BY patent_id"
)

DEFAULT_REVIEW_OUTPUT = "output/patent_invented_by_reviews.jsonl"


def invented_by_mapper(
    vid_by_id: dict[str, str],
    person_index: dict[str, list[dict]],
    org_index: dict[str, list[dict]],
    project_evidence: dict[str, set[str]],
    reviews: list[ReviewRecord],
    stats: Counter,
):
    accept = make_edge_deduper()

    def mapper(table: str, row: dict, batch: str) -> list[EdgeRecord]:
        patent_vid = vid_by_id.get(str(row.get("patent_id")))
        if not patent_vid:
            stats["party:missing_patent"] += 1
            return []
        confirmed_org_names: set[str] = set()
        for column in ("applicants", "assignees"):
            for item in party_items(row.get(column)):
                name = str(item["name"]).strip()
                if len(org_index.get(normalize_name(name), [])) == 1:
                    confirmed_org_names.update(names_from(name))
        records: list[EdgeRecord] = []
        for item in party_items(row.get("inventors")):
            name = str(item["name"]).strip()
            sequence = int(item.get("sequence") or 0)
            candidates = person_index.get(normalize_name(name), [])
            scored: list[tuple[dict, bool, bool]] = []
            for candidate in candidates:
                org_hit = bool(confirmed_org_names & person_org_names(candidate))
                project_hit = normalize_name(name) in project_evidence.get(
                    patent_vid, set()
                ) or bool(person_org_names(candidate) & project_evidence.get(patent_vid, set()))
                scored.append((candidate, org_hit, project_hit))
            strong = [entry for entry in scored if entry[1]]
            if len(strong) == 1:
                candidate, _, project_hit = strong[0]
                confidence = 0.90 if project_hit else 0.80
                evidence = (
                    "姓名和任职机构精确一致，且项目人员/机构信息一致"
                    if project_hit
                    else "姓名和任职机构精确一致且候选唯一"
                )
                stats[f"INVENTED_BY:{confidence:.2f}"] += 1
                accepted = accept(
                    EdgeRecord(
                        "INVENTED_BY",
                        patent_vid,
                        str(candidate["vid"]),
                        {
                            "sequence": sequence,
                            "source_name": name,
                            "confidence": confidence,
                            "subject_type": "Person",
                            "resolution_status": "automatic",
                            "match_method": "exact_name_org_project"
                            if project_hit
                            else "exact_name_org",
                            "match_evidence": evidence,
                            "source_table": "dwd_patent",
                            "source_record_id": f"{row['id']}:inventors:{sequence}",
                        },
                        rank=sequence,
                    )
                )
                if accepted is not None:
                    records.append(accepted)
            else:
                stats["INVENTED_BY:review"] += 1
                reason = (
                    "同名候选仍有多个"
                    if len(candidates) > 1
                    else "只有姓名证据"
                    if len(candidates) == 1
                    else "人才表未找到同名人员"
                )
                reviews.append(
                    ReviewRecord(
                        patent_id=str(row["patent_id"]),
                        relation_type="INVENTED_BY",
                        source_name=name,
                        reason=reason,
                        confidence=0.60 if len(candidates) == 1 else None,
                        candidates=[candidate_view(c, "Person") for c in candidates],
                        evidence=["姓名精确匹配", "申请/权利机构和项目证据未能唯一确认"]
                        if candidates
                        else ["无姓名精确候选"],
                        patent_vid=patent_vid,
                        sequence=sequence,
                        role="inventor",
                        source_record_id=f"{row['id']}:inventors:{sequence}",
                    )
                )
        return records

    return mapper


def _resolve_review_output(payload: dict[str, Any]) -> Path:
    raw = payload.get("review_output")
    return Path(raw) if raw else Path(DEFAULT_REVIEW_OUTPUT)


def _load_indexes(
    database: str, dry_run: bool
) -> tuple[dict[str, str], dict[str, list[dict]], dict[str, list[dict]], dict[str, set[str]]]:
    """连图连库构建 vid_by_id + person/org 索引 + project_evidence；dry_run 也连图。"""
    engine = mysql_engine(database)
    graph = graph_client()
    try:
        vid_by_id, patent_index = patent_indexes(graph, engine)
        people, organizations = canonical_entities(graph, engine)
        if not dry_run:
            ensure_edge_schema(graph, "INVENTED_BY", EDGE_PROPERTY_SCHEMAS["INVENTED_BY"])
        project_evidence = project_evidence_context(graph, engine, patent_index)
    finally:
        graph.close()
    engine.dispose()
    person_index = make_index(people, ("name_zh", "name_en"))
    org_index = make_index(organizations, ("name_cn", "name_en", "name_alias"))
    return vid_by_id, person_index, org_index, project_evidence


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument(
        "--review-output",
        type=Path,
        default=Path(DEFAULT_REVIEW_OUTPUT),
        help="待人工审核 JSONL 输出路径（dry-run 也照常输出）",
    )
    args = parser.parse_args()
    configure_logging(args.log_level)
    vid_by_id, person_index, org_index, project_evidence = _load_indexes(
        args.database, args.dry_run
    )
    reviews: list[ReviewRecord] = []
    stats: Counter = Counter()
    summary = run_relation_extractor(
        database=args.database,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run,
        ingest_batch=args.ingest_batch,
        sources=[
            (
                "dwd_patent",
                # 旧表无 updated_time，增量水位走 update_time 列。
                apply_since(SOURCE_SQL, args.since, col="update_time"),
                invented_by_mapper(
                    vid_by_id, person_index, org_index, project_evidence, reviews, stats
                ),
            )
        ],
        # since 已预应用到 SQL（update_time 列），此处只补绑定参数。
        extra_params={"since": args.since} if args.since else None,
    )
    stats["review_records"] = len(reviews)
    summary["sources"]["dwd_patent"].update(stats)
    write_reviews(args.review_output, reviews)
    summary["review_output"] = str(args.review_output)
    print_json(summary)


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    vid_by_id, person_index, org_index, project_evidence = _load_indexes(
        common["database"], common["dry_run"]
    )
    reviews: list[ReviewRecord] = []
    stats: Counter = Counter()
    review_output = _resolve_review_output(payload)
    summary = run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        sources=[
            (
                "dwd_patent",
                # 旧表无 updated_time，增量水位走 update_time 列。
                apply_since(SOURCE_SQL, common["since"], col="update_time"),
                invented_by_mapper(
                    vid_by_id, person_index, org_index, project_evidence, reviews, stats
                ),
            )
        ],
        extra_params={"since": common["since"]} if common["since"] else None,
    )
    stats["review_records"] = len(reviews)
    summary["sources"]["dwd_patent"].update(stats)
    write_reviews(review_output, reviews)
    summary["review_output"] = str(review_output)
    return summary


if __name__ == "__main__":
    main()
