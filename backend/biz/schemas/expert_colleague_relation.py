from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExpertColleagueRelationRequest(BaseModel):
    """科技专家同事关系查询条件。"""

    model_config = ConfigDict(
        populate_by_name=False,
        extra="forbid",
        json_schema_extra={
            "example": {
                "expert_a_id": "person_0209a7v6",
                "expert_b_id": "person_1S5195f4",
                "start_time": "2021-01",
                "end_time": "2026-08",
            }
        },
    )

    expertId: str = Field(
        min_length=1,
        max_length=64,
        validation_alias="expert_a_id",
        description="专家 A 的 VID、scholar_id、source_record_id 或精确姓名。",
    )
    targetExpertId: str = Field(
        min_length=1,
        max_length=64,
        validation_alias="expert_b_id",
        description="专家 B 的 VID、scholar_id、source_record_id 或精确姓名。",
    )
    startTime: str | None = Field(
        default=None,
        validation_alias="start_time",
        description="查询开始时间，格式 YYYY-MM。",
    )
    endTime: str | None = Field(
        default=None,
        validation_alias="end_time",
        description="查询结束时间，格式 YYYY-MM。",
    )

    @field_validator("expertId", "targetExpertId", mode="before")
    @classmethod
    def normalize_expert_id(cls, value: str) -> str:
        if re.search(r"\s", value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        value = value.strip()
        if not value:
            raise ValueError("expertId cannot be empty")
        if len(value) > 64:
            raise ValueError("专家标识长度不能超过 64 个字符")
        if not re.fullmatch(r"[\w\u4e00-\u9fff·.\-]+", value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        return value

    @field_validator("startTime", "endTime")
    @classmethod
    def validate_boundary_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", value):
            raise ValueError("开始时间和结束时间必须使用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> ExpertColleagueRelationRequest:
        if bool(self.startTime) != bool(self.endTime):
            raise ValueError("start_time 和 end_time 必须同时提供")
        if self.startTime and self.endTime and self.startTime > self.endTime:
            raise ValueError("start_time 不能晚于 end_time")
        current_month = date.today().strftime("%Y-%m")
        if self.startTime and self.startTime > current_month:
            raise ValueError("start_time 不能晚于当前月份")
        if self.endTime and self.endTime > current_month:
            raise ValueError("end_time 不能晚于当前月份")
        return self


class EntityProvenance(BaseModel):
    sourceTable: str | None = None
    sourceField: str | None = None
    sourceValue: str | None = None
    ingestBatch: str | None = None
    ingestTime: str | None = None


class ColleagueExpert(BaseModel):
    id: str
    name: str
    organization: str | None = None
    department: str | None = None
    title: str | None = None
    confidence: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    provenance: EntityProvenance | None = None


class ColleagueAchievement(BaseModel):
    id: str
    type: str
    title: str
    year: int | None = None
    confidence: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    provenance: EntityProvenance | None = None


class ColleagueRelationItem(BaseModel):
    colleague: ColleagueExpert
    commonOrganization: str
    organizationEntity: dict[str, Any] = Field(default_factory=dict)
    organizationId: str | None = None
    organizationHierarchy: list[str] = Field(default_factory=list)
    commonDepartment: str | None = None
    commonTeamOrProject: list[str] = Field(default_factory=list)
    effectivePeriod: str
    overlapMonths: int | None = None
    overlapYears: float | None = None
    workContent: list[str] = Field(default_factory=list)
    collaborationScenes: list[str] = Field(default_factory=list)
    achievements: list[ColleagueAchievement] = Field(default_factory=list)
    coPaperCount: int = 0
    coauthorEdge: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    reviewRequired: bool = False
    employmentHistory: list[dict[str, Any]] = Field(default_factory=list)
    employmentEdges: dict[str, dict[str, Any]] = Field(default_factory=dict)
    scoreBreakdown: dict[str, float] = Field(default_factory=dict)


class ExpertColleagueRelationData(BaseModel):
    expert: ColleagueExpert
    targetExpert: ColleagueExpert | None = None
    queryMode: str = "network"
    colleagues: list[ColleagueRelationItem]
    total: int
    summary: dict[str, Any]
    graph: dict[str, list[dict[str, Any]]]
    rules: list[dict[str, Any]] = Field(default_factory=list)
    apiCalls: list[dict[str, Any]]
    returnedCount: int = 0
    offset: int = 0
    limit: int = 20
    persistence: dict[str, Any] = Field(default_factory=dict)
