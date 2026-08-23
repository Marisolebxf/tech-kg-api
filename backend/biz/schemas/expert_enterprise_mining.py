"""专家企业关系挖掘 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpertEnterpriseMiningRequest(BaseModel):
    scholarId: str
    topN: int = 5
    analysisDimensions: list[str] = Field(
        default_factory=lambda: ["industry_status", "core_tech", "financial"]
    )
    regenerate: bool = False


class ExpertEnterpriseQueryRequest(BaseModel):
    scholarId: str = Field(min_length=1)
    topN: int = Field(default=5, ge=1, le=10)
