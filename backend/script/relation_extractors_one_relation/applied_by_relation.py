"""One-relation transform for APPLIED_BY / OWNED_BY（Patent → Organization）（平台喂数抽取：只输出边 JSON）.

复刻旧 load_patent_relations.py 口径：

- 源 ``dwd_patent``（id/patent_id/inventors/applicants/assignees）：
  applicants → APPLIED_BY（role=applicant），assignees → OWNED_BY
  （role=assignee，is_current=true）；
- 申请人/权利人名称对 org 索引（name_cn/name_en/name_alias，normalize_name
  归一）精确匹配且唯一 → 建边 confidence=0.98，
  match_method=exact_unique_organization_name；
- 命中多个机构 → review；未命中机构但命中 Person → 仅 review（confidence
  0.60，唯一候选时），不自动建 Person 边；
- rank=数组序号，同 (edge,src,dst,rank) 去重保留 confidence 高者；
- review JSONL 输出到 output/ 目录（字段与旧一致），dry-run 也照常分析；
- 旧脚本的 Milvus 向量提升（promote_vector_organization_matches）为可选
  对齐步骤，不在本脚本迁移。

Organization/Patent 端点直接取图内真实 vid，不做端点验存。

"""

from collections import Counter
from typing import Any

from script.extract_transform_common import edge_transform, pending_review_items
from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    ensure_edge_schema,
    graph_client,
    mysql_engine,
)
from script.relation_extractors_one_relation.patent_matching import (
    EDGE_PROPERTY_SCHEMAS,
    ReviewRecord,
    candidate_view,
    canonical_entities,
    make_edge_deduper,
    make_index,
    normalize_name,
    party_items,
    party_properties,
    patent_indexes,
)

SOURCE_SQL = (
    "SELECT id, patent_id, inventors, applicants, assignees FROM dwd_patent ORDER BY patent_id"
)

DEFAULT_REVIEW_OUTPUT = "output/patent_applied_by_reviews.jsonl"


def applied_by_mapper(
    vid_by_id: dict[str, str],
    org_index: dict[str, list[dict]],
    person_index: dict[str, list[dict]],
    reviews: list[ReviewRecord],
    stats: Counter,
):
    accept = make_edge_deduper()

    def mapper(table: str, row: dict, batch: str) -> list[EdgeRecord]:
        patent_vid = vid_by_id.get(str(row.get("patent_id")))
        if not patent_vid:
            stats["party:missing_patent"] += 1
            return []
        records: list[EdgeRecord] = []
        for column, edge_type, role, current in (
            ("applicants", "APPLIED_BY", "applicant", None),
            ("assignees", "OWNED_BY", "assignee", True),
        ):
            for item in party_items(row.get(column)):
                name = str(item["name"]).strip()
                sequence = int(item.get("sequence") or 0)
                org_candidates = org_index.get(normalize_name(name), [])
                if len(org_candidates) == 1:
                    stats[f"{edge_type}:0.98"] += 1
                    accepted = accept(
                        EdgeRecord(
                            edge_type,
                            patent_vid,
                            str(org_candidates[0]["vid"]),
                            party_properties(
                                sequence,
                                role,
                                name,
                                0.98,
                                "Organization",
                                "exact_unique_organization_name",
                                "机构名称或别名与dev已有Organization精确匹配且候选唯一",
                                f"{row['id']}:{column}:{sequence}",
                                current,
                            ),
                            rank=sequence,
                        )
                    )
                    if accepted is not None:
                        records.append(accepted)
                elif len(org_candidates) > 1:
                    stats[f"{edge_type}:review"] += 1
                    reviews.append(
                        ReviewRecord(
                            patent_id=str(row["patent_id"]),
                            relation_type=edge_type,
                            source_name=name,
                            reason="机构名称命中多个已有机构",
                            confidence=None,
                            candidates=[candidate_view(c, "Organization") for c in org_candidates],
                            evidence=["机构名称精确匹配但不唯一"],
                            patent_vid=patent_vid,
                            sequence=sequence,
                            role=role,
                            is_current=True if column == "assignees" else None,
                            source_record_id=f"{row['id']}:{column}:{sequence}",
                        )
                    )
                else:
                    stats[f"{edge_type}:review"] += 1
                    person_candidates = person_index.get(normalize_name(name), [])
                    reason = (
                        "名称可能是个人，但只有姓名证据"
                        if person_candidates
                        else "名称未精确命中已有机构或人才"
                    )
                    reviews.append(
                        ReviewRecord(
                            patent_id=str(row["patent_id"]),
                            relation_type=edge_type,
                            source_name=name,
                            reason=reason,
                            confidence=0.60 if len(person_candidates) == 1 else None,
                            candidates=[candidate_view(c, "Person") for c in person_candidates],
                            evidence=["申请人/权利人源字段只有sequence和name"],
                            patent_vid=patent_vid,
                            sequence=sequence,
                            role=role,
                            is_current=True if column == "assignees" else None,
                            source_record_id=f"{row['id']}:{column}:{sequence}",
                        )
                    )
        return records

    return mapper


def _load_indexes(
    database: str, dry_run: bool
) -> tuple[dict[str, str], dict[str, list[dict]], dict[str, list[dict]]]:
    """连图连库构建 vid_by_id + person/org 索引；dry_run 时也连图（旧口径如此）。"""
    engine = mysql_engine(database)
    graph = graph_client()
    try:
        vid_by_id, _ = patent_indexes(graph, engine)
        people, organizations = canonical_entities(graph, engine)
        if not dry_run:
            ensure_edge_schema(graph, "APPLIED_BY", EDGE_PROPERTY_SCHEMAS["APPLIED_BY"])
            ensure_edge_schema(graph, "OWNED_BY", EDGE_PROPERTY_SCHEMAS["OWNED_BY"])
    finally:
        graph.close()
    engine.dispose()
    person_index = make_index(people, ("name_zh", "name_en"))
    org_index = make_index(organizations, ("name_cn", "name_en", "name_alias"))
    return vid_by_id, person_index, org_index


SOURCES = [
    {
        "table": "dwd_patent",
        "pk": "id",
        "time": "update_time",
        "query_sql": ("SELECT id, patent_id, inventors, applicants, assignees FROM dwd_patent"),
    },
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → edges JSON；歧义候选进 pendingReview（人工审核）。"""
    database = (payload.get("source") or {}).get("databaseName") or "gkx_element"
    vid_by_id, person_index, org_index = _load_indexes(database, dry_run=False)
    reviews: list[ReviewRecord] = []
    stats: Counter = Counter()
    result = edge_transform(
        payload, builder=applied_by_mapper(vid_by_id, org_index, person_index, reviews, stats)
    )
    result["pendingReview"] = pending_review_items(reviews, source_table="dwd_patent")
    stats["review_records"] = len(reviews)
    result["stats"] = {**(result.get("stats") or {}), **dict(stats)}
    return result
