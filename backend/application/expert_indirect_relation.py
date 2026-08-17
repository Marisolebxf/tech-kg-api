import os
from collections.abc import Mapping
from typing import Any

from biz.schema.expert_indirect_relation import ExpertIndirectRelationRequest
from service.expert_indirect_relation_api import ExpertIndirectRelationApiService


class ExpertIndirectRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertIndirectRelationApiService()
        self._api_base_url = os.getenv(
            "KG_INTERNAL_API_BASE_URL",
            "http://127.0.0.1:8000/api/v1",
        )

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    async def build_structured_result_only(
        self,
        body: ExpertIndirectRelationRequest,
        *,
        auth_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self._service.build_structured_result_only(
            body,
            api_base_url=self._api_base_url,
            auth_headers=auth_headers,
        )
