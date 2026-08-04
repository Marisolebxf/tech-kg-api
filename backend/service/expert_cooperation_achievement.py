from __future__ import annotations

from collections import Counter
from typing import Any

from dao.scholar import ScholarDAO
from service.base_module import KGModuleService
from service.common.scholar_relationship import resolve_scholar, scholar_data


class ExpertCooperationAchievementService(KGModuleService):
    module_code = "expert_cooperation_achievement"

    def __init__(self, scholar_dao: ScholarDAO | None = None) -> None:
        self._dao = scholar_dao or ScholarDAO()

    def query(
        self,
        *,
        expert_a_id: str,
        expert_b_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if expert_a_id == expert_b_id:
            raise ValueError("两个专家不能相同")
        expert_a = resolve_scholar(self._dao, expert_a_id)
        expert_b = resolve_scholar(self._dao, expert_b_id)
        common = {
            "expert_a_id": expert_a.scholar_id,
            "expert_b_id": expert_b.scholar_id,
            "start_time": start_time,
            "end_time": end_time,
            "limit": max(1, min(limit, 500)),
        }
        rows = [
            *self._dao.list_direct_coauthor_relations(**common),
            *self._dao.list_direct_patent_relations(**common),
            *self._dao.list_direct_project_relations(**common),
        ]
        achievements = []
        for row in rows:
            kind = str(row.get("evidence_kind") or "paper")
            titles = [str(item) for item in row.get("evidence_titles") or [] if item]
            count = int(row.get("evidence_count") or row.get("co_paper_count") or len(titles))
            achievements.append(
                {
                    "type": kind,
                    "typeLabel": {"paper": "论文", "patent": "专利", "project": "项目"}.get(
                        kind, kind
                    ),
                    "count": count,
                    "titles": titles[:20],
                    "institution": row.get("institution"),
                    "latestAt": _time_value(row.get("relation_time")),
                }
            )
        counts = Counter()
        for item in achievements:
            counts[item["type"]] += item["count"]
        total = sum(counts.values())
        return {
            "expertA": scholar_data(expert_a),
            "expertB": scholar_data(expert_b),
            "totalAchievements": total,
            "categoryCounts": dict(counts),
            "cooperationScore": min(100, 40 + total * 5 + len(counts) * 10),
            "items": achievements,
            "graph": {
                "nodes": [scholar_data(expert_a), scholar_data(expert_b)],
                "edges": [
                    {
                        "source": expert_a.scholar_id,
                        "target": expert_b.scholar_id,
                        "type": "COOPERATED_WITH",
                        "properties": {"achievementCount": total, "categories": dict(counts)},
                    }
                ],
            },
        }


def _time_value(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
