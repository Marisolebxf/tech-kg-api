"""科技专家校友关系 请求/响应模型。"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import check_text

MAX_ALUMNI_LIMIT = 50
MAX_EXPERT_ID_LENGTH = 64
MAX_SCHOOL_LENGTH = 100
EXPERT_ID_PATTERN = re.compile(r"^[\w\u4e00-\u9fff·.\-]+$")
SCHOOL_PATTERN = re.compile(r"^[\w\u4e00-\u9fff·（）()《》.\-\s]+$")


class AlumniRelationQueryRequest(BaseModel):
    expertId: str = Field(
        ..., min_length=1, max_length=MAX_EXPERT_ID_LENGTH, description="源专家图节点 ID"
    )
    targetExpertId: str | None = Field(
        default=None, max_length=MAX_EXPERT_ID_LENGTH, description="目标专家 ID，有则双点判定"
    )
    school: str | None = Field(
        default=None, max_length=MAX_SCHOOL_LENGTH, description="院校关键词过滤"
    )
    educationStage: str | None = Field(
        default=None, description="教育阶段/学历过滤，多选时用逗号分隔"
    )
    limit: int = Field(
        default=20,
        strict=True,
        ge=1,
        le=MAX_ALUMNI_LIMIT,
        description=f"返回校友数上限，1-{MAX_ALUMNI_LIMIT}",
    )

    @field_validator("expertId", "targetExpertId", mode="before")
    @classmethod
    def validate_expert_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("专家 ID 必须是字符串")
        if len(value) > MAX_EXPERT_ID_LENGTH:
            raise ValueError(f"专家 ID 长度不能超过 {MAX_EXPERT_ID_LENGTH} 个字符")
        if re.search(r"\s", value) or not EXPERT_ID_PATTERN.fullmatch(value):
            raise ValueError("专家 ID 不能包含空格或 !@#￥%& 等异常字符")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("专家 ID 不能为空")
        return cleaned

    @field_validator("limit", mode="before")
    @classmethod
    def validate_limit(cls, value: object) -> object:
        # 只做长度/异常字符检查,类型与范围仍交给 strict int 约束
        check_text(str(value).strip(), label="校友数量上限")
        return value

    @field_validator("school", mode="before")
    @classmethod
    def validate_school(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("院校名称必须是字符串")
        if len(value) > MAX_SCHOOL_LENGTH:
            raise ValueError(f"院校名称长度不能超过 {MAX_SCHOOL_LENGTH} 个字符")
        cleaned = value.strip()
        if cleaned and not SCHOOL_PATTERN.fullmatch(cleaned):
            raise ValueError("院校名称包含 !@#￥%& 等异常字符")
        return cleaned or None

    @field_validator("educationStage")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return check_text(cleaned, label="教育阶段", allow_space=True)
