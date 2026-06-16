from service.expert_direct_relation import ExpertDirectRelationService


class ExpertDirectRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertDirectRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
