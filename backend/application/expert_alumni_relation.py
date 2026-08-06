from service.expert_alumni_relation import ExpertAlumniRelationService


class ExpertAlumniRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertAlumniRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def query(
        self,
        *,
        expert_id: str,
        target_expert_id: str | None = None,
        school: str | None = None,
        education_stage: str | None = None,
        limit: int = 20,
    ) -> dict[str, object]:
        return self._service.query(
            expert_id=expert_id,
            target_expert_id=target_expert_id,
            school=school,
            education_stage=education_stage,
            limit=limit,
        )
