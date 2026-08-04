from __future__ import annotations

from typing import Any

from dao.scholar import ScholarDAO
from service.base_module import KGModuleService
from service.common.scholar_relationship import (
    institution_evidence,
    resolve_scholar,
    scholar_data,
    shared_institutions,
)


class ExpertColleagueRelationService(KGModuleService):
    module_code = "expert_colleague_relation"

    def __init__(self, scholar_dao: ScholarDAO | None = None) -> None:
        self._dao = scholar_dao or ScholarDAO()

    def query(
        self,
        *,
        expert_id: str,
        peer_id: str | None = None,
        institution: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        center = resolve_scholar(self._dao, expert_id)
        candidates = (
            [resolve_scholar(self._dao, peer_id)] if peer_id else self._dao.list_active(limit=1000)
        )
        center_evidence = institution_evidence(
            center.scholar_org_name_zh,
            center.scholar_org_name_en,
            center.work_experience_zh,
            center.work_experience_en,
        )
        keyword = (institution or "").strip().casefold()
        items = []
        for candidate in candidates:
            if candidate.scholar_id == center.scholar_id:
                continue
            shared = shared_institutions(
                center_evidence,
                institution_evidence(
                    candidate.scholar_org_name_zh,
                    candidate.scholar_org_name_en,
                    candidate.work_experience_zh,
                    candidate.work_experience_en,
                ),
            )
            if keyword:
                shared = [item for item in shared if keyword in item.casefold()]
            if not shared:
                continue
            score = min(100, 70 + len(shared) * 10)
            items.append(
                {
                    "expert": scholar_data(candidate),
                    "sharedInstitutions": sorted(shared),
                    "score": score,
                    "evidence": [f"共同任职/工作经历: {item}" for item in sorted(shared)],
                }
            )
        items.sort(key=lambda item: (item["score"], item["expert"]["hIndex"]), reverse=True)
        items = items[: max(1, min(limit, 100))]
        return _scholar_relation_result("COLLEAGUE_OF", center, items)


def _scholar_relation_result(
    relation_type: str, center: Any, items: list[dict[str, Any]]
) -> dict[str, Any]:
    center_data = scholar_data(center)
    nodes = [{"id": center_data["id"], "type": "expert", **center_data}]
    edges = []
    for item in items:
        expert = item["expert"]
        nodes.append({"id": expert["id"], "type": "expert", **expert})
        edges.append(
            {
                "source": center_data["id"],
                "target": expert["id"],
                "type": relation_type,
                "score": item["score"],
                "evidence": item["evidence"],
            }
        )
    return {
        "center": center_data,
        "total": len(items),
        "items": items,
        "graph": {"nodes": nodes, "edges": edges},
    }
