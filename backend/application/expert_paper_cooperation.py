from typing import Any

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.expert_paper_cooperation import ExpertPaperCooperationService


class ExpertPaperCooperationApplication:
    def __init__(self) -> None:
        self._service = ExpertPaperCooperationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def build_structured_result_only(
        self, body: ExpertPaperCooperationDemoRequest
    ) -> dict[str, Any]:
        return self._service.build_structured_result_only(body)

