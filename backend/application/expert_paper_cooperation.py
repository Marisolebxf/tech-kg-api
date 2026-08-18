import os
from collections.abc import Mapping
from typing import Any

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.expert_paper_cooperation_api import ExpertPaperCooperationApiService


class ExpertPaperCooperationApplication:
    def __init__(self) -> None:
        self._service = ExpertPaperCooperationApiService()
        self._api_base_url = os.getenv(
            "KG_INTERNAL_API_BASE_URL",
            "http://127.0.0.1:8000/api/v1",
        )

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    async def build_structured_result_only(
        self,
        body: ExpertPaperCooperationDemoRequest,
        *,
        auth_headers: Mapping[str, str] | None = None,
        app: Any = None,
    ) -> dict[str, Any]:
        return await self._service.build_structured_result_only(
            body,
            api_base_url=self._api_base_url,
            auth_headers=auth_headers,
            app=app,
        )
