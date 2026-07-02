from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from dao.scholar import ScholarDAO
from service.base_module import KGModuleScaffoldService

FALLBACK_ITEMS: list[dict[str, Any]] = [
    {
        "relation_key": "direct:fallback:zhangmingyuan:lijianing",
        "expert_a_id": "fallback_zhangmingyuan",
        "expert_a_name": "张明远",
        "expert_a_org": "清华大学",
        "expert_a_h_index": 36,
        "expert_a_paper_nums": 128,
        "expert_a_citation_nums": 4380,
        "expert_b_id": "fallback_lijianing",
        "expert_b_name": "李佳宁",
        "expert_b_org": "清华大学",
        "expert_b_h_index": 24,
        "expert_b_paper_nums": 86,
        "expert_b_citation_nums": 1930,
        "co_paper_count": 4,
        "relation_time": datetime(2026, 6, 29, 12, 0, 0),
    },
    {
        "relation_key": "direct:fallback:lijianning:zhouxinyi",
        "expert_a_id": "fallback_lijianing",
        "expert_a_name": "李佳宁",
        "expert_a_org": "智能决策联合实验室",
        "expert_a_h_index": 24,
        "expert_a_paper_nums": 86,
        "expert_a_citation_nums": 1930,
        "expert_b_id": "fallback_zhouxinyi",
        "expert_b_name": "周欣怡",
        "expert_b_org": "北京航空航天大学计算机学院",
        "expert_b_h_index": 41,
        "expert_b_paper_nums": 149,
        "expert_b_citation_nums": 5160,
        "co_paper_count": 2,
        "relation_time": datetime(2026, 6, 29, 12, 5, 0),
    },
]

MAX_QUERY_LIMIT = 100


class ExpertDirectRelationService(KGModuleScaffoldService):
    module_code = "expert_direct_relation"

    def __init__(self, scholar_dao: ScholarDAO | None = None) -> None:
        self._scholar_dao = scholar_dao or ScholarDAO()

    def query(
        self,
        *,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        normalized_source = "all"
        normalized_limit = max(1, min(int(limit or 10), MAX_QUERY_LIMIT))
        query_input = {
            "dataSource": normalized_source,
            "expertAId": (expert_a_id or "").strip(),
            "expertBId": (expert_b_id or "").strip(),
            "institution": (institution or "").strip(),
            "startTime": (start_time or "").strip(),
            "endTime": (end_time or "").strip(),
            "limit": normalized_limit,
        }

        source = {"requested": normalized_source, "actual": "fallback", "fallback": True}
        rows: list[dict[str, Any]] = []

        if normalized_source != "fallback":
            try:
                rows.extend(
                    self._scholar_dao.list_direct_coauthor_relations(
                        expert_a_id=expert_a_id,
                        expert_b_id=expert_b_id,
                        institution=institution,
                        start_time=start_time,
                        end_time=end_time,
                        limit=normalized_limit,
                    )
                )
                rows.extend(
                    self._scholar_dao.list_direct_patent_relations(
                        expert_a_id=expert_a_id,
                        expert_b_id=expert_b_id,
                        institution=institution,
                        start_time=start_time,
                        end_time=end_time,
                        limit=normalized_limit,
                    )
                )
                rows.extend(
                    self._scholar_dao.list_direct_project_relations(
                        expert_a_id=expert_a_id,
                        expert_b_id=expert_b_id,
                        institution=institution,
                        start_time=start_time,
                        end_time=end_time,
                        limit=normalized_limit,
                    )
                )
                rows = self._orient_rows(
                    rows=self._sort_rows(rows)[:normalized_limit],
                    expert_a_id=expert_a_id,
                    expert_b_id=expert_b_id,
                )
                source = {"requested": normalized_source, "actual": "mysql", "fallback": False}
            except Exception:
                rows = []

        if not rows and source["actual"] != "mysql":
            rows = self._orient_rows(
                rows=FALLBACK_ITEMS[: max(1, min(normalized_limit, len(FALLBACK_ITEMS)))],
                expert_a_id=expert_a_id,
                expert_b_id=expert_b_id,
            )

        items = [self._build_item(row) for row in rows]
        graph = self._build_graph(items)

        return {
            "taskName": "科技专家直接关系查询",
            "input": query_input,
            "total": len(items),
            "items": items,
            "graph": graph,
            "source": source,
            "apiResultExample": {
                "url": "/api/v1/kg-construction/expert-direct-relations/query",
                "method": "POST",
                "query": query_input,
            },
        }

    def _build_item(self, row: dict[str, Any]) -> dict[str, Any]:
        expert_a_org = str(row.get("expert_a_org") or "")
        expert_b_org = str(row.get("expert_b_org") or "")
        institution = str(row.get("institution") or expert_a_org or expert_b_org or "合作关系")
        evidence_kind = str(row.get("evidence_kind") or "paper")
        evidence_count = int(row.get("evidence_count") or row.get("co_paper_count") or 0)
        evidence_titles = row.get("evidence_titles") or []

        if evidence_kind == "patent":
            reason_tags = ["共专利"] if evidence_count else ["专利关联"]
        elif evidence_kind == "project":
            reason_tags = ["共项目"] if evidence_count else ["项目关联"]
        else:
            reason_tags = ["共论文"] if evidence_count else ["合作关系"]
        if expert_a_org and expert_b_org and expert_a_org == expert_b_org:
            reason_tags.insert(0, "同机构")

        relation_strength = min(99, max(60, 60 + evidence_count * 5 + len(reason_tags) * 4))
        relation_time = row.get("relation_time")
        last_updated_at = (
            relation_time.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(relation_time, "strftime")
            else None
        )

        expert_a = {
            "expertId": str(row.get("expert_a_id") or ""),
            "name": str(row.get("expert_a_name") or row.get("expert_a_id") or ""),
            "organization": expert_a_org or None,
            "title": "专家",
            "paperCount": int(row.get("expert_a_paper_nums") or 0),
            "citationCount": int(row.get("expert_a_citation_nums") or 0),
            "hIndex": int(row.get("expert_a_h_index") or 0),
        }
        expert_b = {
            "expertId": str(row.get("expert_b_id") or ""),
            "name": str(row.get("expert_b_name") or row.get("expert_b_id") or ""),
            "organization": expert_b_org or None,
            "title": "专家",
            "paperCount": int(row.get("expert_b_paper_nums") or 0),
            "citationCount": int(row.get("expert_b_citation_nums") or 0),
            "hIndex": int(row.get("expert_b_h_index") or 0),
        }

        return {
            "key": str(row.get("relation_key") or ""),
            "relationType": "直接关系",
            "expertA": expert_a,
            "expertB": expert_b,
            "institution": institution,
            "coPaperCount": evidence_count if evidence_kind == "paper" else 0,
            "relationStrength": relation_strength,
            "reasonTags": reason_tags,
            "relationSummary": " + ".join(reason_tags),
            "lastUpdatedAt": last_updated_at,
            "detailRows": [
                ["专家 A", expert_a["name"]],
                ["专家 A 机构", expert_a["organization"] or ""],
                ["专家 A H指数", expert_a["hIndex"]],
                ["专家 B", expert_b["name"]],
                ["专家 B 机构", expert_b["organization"] or ""],
                ["专家 B H指数", expert_b["hIndex"]],
                ["关系类型", "直接关系"],
                ["共同机构/主关系", institution],
                ["证据类型", self._evidence_label(evidence_kind)],
                ["证据数量", evidence_count],
                ["证据示例", "；".join(str(title) for title in evidence_titles[:3])],
                ["判定依据", reason_tags],
                ["关系摘要", " + ".join(reason_tags)],
            ],
        }

    def _build_graph(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()

        for item in items[:4]:
            expert_a = item["expertA"]
            expert_b = item["expertB"]
            institution = item["institution"] or "合作关系"
            institution_id = f"institution:{institution}"

            for node in (
                {
                    "id": expert_a["expertId"],
                    "type": "expert",
                    "label": expert_a["name"],
                    "subtitle": expert_a["organization"],
                    "data": {"role": "A"},
                },
                {
                    "id": expert_b["expertId"],
                    "type": "expert",
                    "label": expert_b["name"],
                    "subtitle": expert_b["organization"],
                    "data": {"role": "B"},
                },
                {
                    "id": institution_id,
                    "type": "institution",
                    "label": institution,
                    "subtitle": "关系归属",
                    "data": {},
                },
            ):
                if node["id"] not in seen_nodes:
                    seen_nodes.add(node["id"])
                    nodes.append(node)

            edges.append(
                {
                    "source": expert_a["expertId"],
                    "target": expert_b["expertId"],
                    "label": f"直接关系 / {item['relationSummary']}",
                    "data": {"strength": item["relationStrength"]},
                }
            )
            edges.append(
                {
                    "source": expert_a["expertId"],
                    "target": institution_id,
                    "label": "关联机构",
                    "data": {},
                }
            )
            edges.append(
                {
                    "source": expert_b["expertId"],
                    "target": institution_id,
                    "label": "关联机构",
                    "data": {},
                }
            )

        return {"nodes": nodes, "edges": edges}

    def _sort_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda row: (
                int(row.get("evidence_count") or row.get("co_paper_count") or 0),
                row.get("relation_time") or "",
            ),
            reverse=True,
        )

    def _orient_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        expert_a_id: str | None,
        expert_b_id: str | None,
    ) -> list[dict[str, Any]]:
        return [
            self._orient_row(row, expert_a_id=expert_a_id, expert_b_id=expert_b_id)
            for row in rows
        ]

    def _orient_row(
        self,
        row: dict[str, Any],
        *,
        expert_a_id: str | None,
        expert_b_id: str | None,
    ) -> dict[str, Any]:
        a_keyword = (expert_a_id or "").strip().lower()
        b_keyword = (expert_b_id or "").strip().lower()
        if not a_keyword and not b_keyword:
            return row

        left_matches_a = self._matches_row_side(row, "a", a_keyword)
        right_matches_a = self._matches_row_side(row, "b", a_keyword)
        left_matches_b = self._matches_row_side(row, "a", b_keyword)
        right_matches_b = self._matches_row_side(row, "b", b_keyword)

        should_swap = False
        if a_keyword and right_matches_a and not left_matches_a:
            should_swap = True
        if a_keyword and b_keyword and right_matches_a and left_matches_b:
            should_swap = True

        if not should_swap:
            return row

        swapped = dict(row)
        for field in ("id", "name", "org", "h_index", "paper_nums", "citation_nums"):
            swapped[f"expert_a_{field}"] = row.get(f"expert_b_{field}")
            swapped[f"expert_b_{field}"] = row.get(f"expert_a_{field}")
        return swapped

    def _matches_row_side(self, row: dict[str, Any], side: str, keyword: str) -> bool:
        if not keyword:
            return False
        values = [
            str(row.get(f"expert_{side}_id") or "").strip().lower(),
            str(row.get(f"expert_{side}_name") or "").strip().lower(),
        ]
        return keyword in values

    def _evidence_label(self, evidence_kind: str) -> str:
        if evidence_kind == "patent":
            return "共同专利"
        if evidence_kind == "project":
            return "共同项目"
        return "共同论文"

    def fallback_limit(self) -> int:
        return int(os.getenv("EXPERT_DIRECT_RELATION_REAL_LIMIT", "20"))
