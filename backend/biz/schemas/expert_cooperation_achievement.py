"""科技两点合作成果 请求/响应模型。"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DATE_PATTERN = re.compile(
    r"^(?:\d{4}|\d{4}-(?:0[1-9]|1[0-2])|"
    r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))$"
)
EXPERT_ID_PATTERN = re.compile(r"^[\w\u4e00-\u9fff·.\-]+$")
MAX_EXPERT_ID_LENGTH = 64

AchievementType = Literal["paper", "patent", "project"]
MAX_LIMIT_PER_TYPE = 50


class CooperationAchievementQueryRequest(BaseModel):
    sourceExpertId: str = Field(
        ..., min_length=1, max_length=MAX_EXPERT_ID_LENGTH, description="专家 A 图节点 ID"
    )
    targetExpertId: str = Field(
        ..., min_length=1, max_length=MAX_EXPERT_ID_LENGTH, description="专家 B 图节点 ID"
    )
    achievementTypes: list[AchievementType] | None = Field(
        default=None, description="成果类型过滤，空表示全部"
    )
    timeRangeStart: str | None = Field(default=None, description="可选时间起点 YYYY / YYYY-MM-DD")
    timeRangeEnd: str | None = Field(default=None, description="可选时间终点 YYYY / YYYY-MM-DD")
    limitPerType: int = Field(
        default=20,
        strict=True,
        ge=1,
        le=MAX_LIMIT_PER_TYPE,
        description=f"每类成果上限，1-{MAX_LIMIT_PER_TYPE}",
    )

    @field_validator("sourceExpertId", "targetExpertId", mode="before")
    @classmethod
    def strip_ids(cls, value: str) -> str:
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

    @field_validator("timeRangeStart", "timeRangeEnd")
    @classmethod
    def validate_time_range(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not DATE_PATTERN.fullmatch(cleaned):
            raise ValueError("日期格式必须为 YYYY、YYYY-MM 或 YYYY-MM-DD")
        if len(cleaned) == 10:
            try:
                datetime.strptime(cleaned, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("日期不是有效的日历日期") from exc
        return cleaned

    @model_validator(mode="after")
    def validate_time_bounds(self) -> CooperationAchievementQueryRequest:
        if bool(self.timeRangeStart) != bool(self.timeRangeEnd):
            raise ValueError("开始时间和结束时间必须同时填写")

        today = date.today()

        def boundary(value: str, *, end: bool) -> date:
            if len(value) == 4:
                return date(int(value), 12 if end else 1, 31 if end else 1)
            if len(value) == 7:
                year, month = map(int, value.split("-"))
                if not end:
                    return date(year, month, 1)
                next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
                return date.fromordinal(next_month.toordinal() - 1)
            return datetime.strptime(value, "%Y-%m-%d").date()

        if self.timeRangeStart and boundary(self.timeRangeStart, end=False) > today:
            raise ValueError("输入时间不能超过当前时间")
        if self.timeRangeEnd and boundary(self.timeRangeEnd, end=False) > today:
            raise ValueError("输入时间不能超过当前时间")
        if self.timeRangeStart and self.timeRangeEnd:
            if boundary(self.timeRangeStart, end=False) > boundary(self.timeRangeEnd, end=True):
                raise ValueError("开始时间不能晚于结束时间")
        return self
