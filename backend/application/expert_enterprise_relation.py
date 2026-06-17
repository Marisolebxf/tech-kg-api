"""专家-企业关系构建 编排层。"""

from __future__ import annotations

from typing import Any

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


class ExpertEnterpriseRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertEnterpriseRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._service.build(payload)
