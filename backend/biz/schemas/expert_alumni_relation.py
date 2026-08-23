"""科技专家校友关系 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_ALUMNI_LIMIT = 50


class AlumniRelationQueryRequest(BaseModel):
    expertId: str = Field(..., min_length=1, description="源专家图节点 ID")
    targetExpertId: str | None = Field(default=None, description="目标专家 ID，有则双点判定")
    school: str | None = Field(default=None, description="院校关键词过滤")
    educationStage: str | None = Field(
        default=None, description="教育阶段/学历过滤，多选时用逗号分隔"
    )
    limit: int = Field(default=20, ge=1, description=f"返回校友数上限，最大 {MAX_ALUMNI_LIMIT}")

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return min(value, MAX_ALUMNI_LIMIT)

    @field_validator("expertId")
    @classmethod
    def strip_expert_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("专家 ID 不能为空")
        return cleaned

    @field_validator("targetExpertId", "school", "educationStage")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
