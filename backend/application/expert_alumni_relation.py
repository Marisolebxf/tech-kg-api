from service.expert_alumni_relation import ExpertAlumniRelationService


class ExpertAlumniRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertAlumniRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
