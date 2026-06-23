from __future__ import annotations

from service.expert_direct_relation import ExpertDirectRelationService


class ExpertDirectRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertDirectRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def get_relation_response(
        self,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        relation_type: str = "direct",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, object]:
        return self._service.build_relation_response(
            data_source=data_source,
            expert_a_id=expert_a_id,
            expert_b_id=expert_b_id,
            institution=institution,
            relation_type=relation_type,
            start_time=start_time,
            end_time=end_time,
        )
