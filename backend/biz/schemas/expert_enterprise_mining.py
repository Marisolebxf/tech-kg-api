"""专家企业关系挖掘 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import check_text


class ExpertEnterpriseMiningRequest(BaseModel):
    scholarId: str = Field(..., min_length=1, max_length=64, description="专家唯一标识")
    topN: int = Field(default=5, ge=1, le=10)
    analysisDimensions: list[str] = Field(
        default_factory=lambda: ["industry_status", "core_tech", "financial"]
    )
    regenerate: bool = False

    @field_validator("scholarId", mode="before")
    @classmethod
    def _validate_scholar_id(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="专家标识")


class ExpertEnterpriseQueryRequest(BaseModel):
    scholarId: str = Field(min_length=1, max_length=64, description="专家唯一标识")
    topN: int = Field(default=5, ge=1, le=10)

    @field_validator("scholarId", mode="before")
    @classmethod
    def _validate_scholar_id(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="专家标识")
