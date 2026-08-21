"""科技两点合作成果 请求/响应模型。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DATE_PATTERN = re.compile(r"^(?:\d{4}|\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))$")

AchievementType = Literal["paper", "patent", "project"]
MAX_LIMIT_PER_TYPE = 50


class CooperationAchievementQueryRequest(BaseModel):
    sourceExpertId: str = Field(..., min_length=1, description="专家 A 图节点 ID")
    targetExpertId: str = Field(..., min_length=1, description="专家 B 图节点 ID")
    achievementTypes: list[AchievementType] | None = Field(
        default=None, description="成果类型过滤，空表示全部"
    )
    timeRangeStart: str | None = Field(default=None, description="可选时间起点 YYYY / YYYY-MM-DD")
    timeRangeEnd: str | None = Field(default=None, description="可选时间终点 YYYY / YYYY-MM-DD")
    limitPerType: int = Field(
        default=20, ge=1, description=f"每类成果上限，最大 {MAX_LIMIT_PER_TYPE}"
    )

    @field_validator("limitPerType")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return min(value, MAX_LIMIT_PER_TYPE)

    @field_validator("sourceExpertId", "targetExpertId")
    @classmethod
    def strip_ids(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("专家 ID 不能为空")
        return cleaned

    @field_validator("timeRangeStart", "timeRangeEnd")
    @classmethod
    def validate_time_range(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not DATE_PATTERN.fullmatch(cleaned):
            raise ValueError("日期格式必须为 YYYY 或 YYYY-MM-DD")
        return cleaned
