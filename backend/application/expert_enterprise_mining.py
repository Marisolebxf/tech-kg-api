"""专家企业关系挖掘 编排层。"""

from __future__ import annotations

from typing import Any

from service.expert_enterprise_mining import ExpertEnterpriseMiningService


class ExpertEnterpriseMiningApplication:
    def __init__(self) -> None:
        self._service = ExpertEnterpriseMiningService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def mine(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._service.mine(payload)
