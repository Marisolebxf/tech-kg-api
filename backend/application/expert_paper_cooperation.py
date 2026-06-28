from typing import Any

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.expert_paper_cooperation import ExpertPaperCooperationService


class ExpertPaperCooperationApplication:
    def __init__(self) -> None:
        self._service = ExpertPaperCooperationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def analyze_demo(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        return self._service.analyze_demo(body)

    def analyze_mysql_demo(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        return self._service.analyze_mysql_demo(body)

    def build_structured_result_only(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        return self._service.build_structured_result_only(body)

    def build_graph_view(self, body: ExpertPaperCooperationDemoRequest) -> dict[str, Any]:
        return self._service.build_graph_view(body)
