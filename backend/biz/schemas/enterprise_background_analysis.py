"""企业背景关联分析 请求/响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import check_text

VALID_DIMENSIONS = {"industry_status", "core_tech", "financial"}


class EnterpriseBackgroundAnalysisRequest(BaseModel):
    enterpriseId: str = Field(..., min_length=1, max_length=64, description="企业唯一标识")
    analysisDimensions: list[str]
    patentCPC: list[str] = Field(default_factory=list)

    @field_validator("enterpriseId", mode="before")
    @classmethod
    def _validate_enterprise_id(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="企业标识")

    @field_validator("patentCPC", mode="before")
    @classmethod
    def _validate_patent_cpc(cls, v: list[str]) -> list[str]:
        if not v:
            return v
        return [check_text(str(item).strip(), label="CPC 分类号", allow_space=True) for item in v]

    @field_validator("analysisDimensions")
    @classmethod
    def _validate_dims(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("analysisDimensions 不能为空")
        bad = [d for d in v if d not in VALID_DIMENSIONS]
        if bad:
            raise ValueError(f"非法分析维度: {bad}")
        return v


class DimensionResult(BaseModel):
    available: bool = False
    facts: dict[str, Any] | None = None
    summary: str | None = None
    conclusion: str | None = None


class PatentDistItem(BaseModel):
    cpcSection: str
    count: int


class EnterpriseBackgroundAnalysisResponse(BaseModel):
    status: str = "success"
    enterpriseId: str
    enterpriseName: str
    dimensions: dict[str, DimensionResult]
    patentDistribution: list[PatentDistItem] = Field(default_factory=list)
    coreTechLayout: str = ""
