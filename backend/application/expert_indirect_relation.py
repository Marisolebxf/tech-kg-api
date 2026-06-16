from service.expert_indirect_relation import ExpertIndirectRelationService


class ExpertIndirectRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertIndirectRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
