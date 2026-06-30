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
                rows = self._scholar_dao.list_direct_coauthor_relations(
                    expert_a_id=expert_a_id,
                    expert_b_id=expert_b_id,
                    institution=institution,
                    start_time=start_time,
                    end_time=end_time,
                    limit=normalized_limit,
                )
                source = {"requested": normalized_source, "actual": "mysql", "fallback": False}
            except Exception:
                rows = []

        if not rows and source["actual"] != "mysql":
            rows = FALLBACK_ITEMS[: max(1, min(normalized_limit, len(FALLBACK_ITEMS)))]

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
        institution = expert_a_org or expert_b_org or "合作关系"
        co_paper_count = int(row.get("co_paper_count") or 0)

        reason_tags = ["共论文"] if co_paper_count else ["合作关系"]
        if expert_a_org and expert_b_org and expert_a_org == expert_b_org:
            reason_tags.insert(0, "同机构")

        relation_strength = min(99, max(60, 60 + co_paper_count * 5 + len(reason_tags) * 4))
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
            "coPaperCount": co_paper_count,
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
                ["合作论文数", co_paper_count],
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
                    "label": f"直接关系 / 合作论文 {item['coPaperCount']}",
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

    def fallback_limit(self) -> int:
        return int(os.getenv("EXPERT_DIRECT_RELATION_REAL_LIMIT", "20"))
