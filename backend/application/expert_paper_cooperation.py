from service.expert_paper_cooperation import ExpertPaperCooperationService


class ExpertPaperCooperationApplication:
    def __init__(self) -> None:
        self._service = ExpertPaperCooperationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()
