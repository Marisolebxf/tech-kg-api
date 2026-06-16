from service.expert_colleague_relation import ExpertColleagueRelationService


class ExpertColleagueRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertColleagueRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
