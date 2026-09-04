from collections.abc import Mapping

from service.expert_direct_relation import ExpertDirectRelationService


class ExpertDirectRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertDirectRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    async def query(
        self,
        *,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 10,
        auth_headers: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        return await self._service.query(
            data_source=data_source,
            expert_a_id=expert_a_id,
            expert_b_id=expert_b_id,
            institution=institution,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            auth_headers=auth_headers,
        )
