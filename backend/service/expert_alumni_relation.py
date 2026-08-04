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
from service.expert_colleague_relation import _scholar_relation_result


class ExpertAlumniRelationService(KGModuleService):
    module_code = "expert_alumni_relation"

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
            center.education_background_zh, center.education_background_en
        )
        keyword = (institution or "").strip().casefold()
        items: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.scholar_id == center.scholar_id:
                continue
            shared = shared_institutions(
                center_evidence,
                institution_evidence(
                    candidate.education_background_zh, candidate.education_background_en
                ),
            )
            if keyword:
                shared = [item for item in shared if keyword in item.casefold()]
            if not shared:
                continue
            items.append(
                {
                    "expert": scholar_data(candidate),
                    "sharedInstitutions": sorted(shared),
                    "score": min(100, 65 + len(shared) * 12),
                    "evidence": [f"共同教育经历: {item}" for item in sorted(shared)],
                }
            )
        items.sort(key=lambda item: (item["score"], item["expert"]["hIndex"]), reverse=True)
        return _scholar_relation_result("ALUMNI_OF", center, items[: max(1, min(limit, 100))])
