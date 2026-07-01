"""专家企业关系挖掘 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpertEnterpriseMiningRequest(BaseModel):
    scholarId: str
    topN: int = 5
    analysisDimensions: list[str] = Field(
        default_factory=lambda: ["industry_status", "core_tech", "financial"]
    )
