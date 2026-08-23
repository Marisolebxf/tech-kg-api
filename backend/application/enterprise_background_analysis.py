"""企业背景关联分析 编排层。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from service.enterprise_background_analysis import EnterpriseBackgroundAnalysisService


class EnterpriseBackgroundAnalysisApplication:
    def __init__(self) -> None:
        self._service = EnterpriseBackgroundAnalysisService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    def analyze(self, payload: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
        return self._service.analyze(payload, session=session)
