from service.expert_enterprise_relation import ExpertEnterpriseRelationService


class ExpertEnterpriseRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertEnterpriseRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
