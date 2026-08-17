from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpertColleagueRelationRequest(BaseModel):
    """科技专家同事关系查询条件。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expertId": "person_10001",
                "organization": "中国科学院自动化研究所",
                "department": "智能系统实验室",
                "overlapPeriod": "2018-2022",
                "limit": 20,
                "space": "dev",
            }
        }
    )

    expertId: str = Field(min_length=1, description="专家 VID、scholar_id 或中文姓名。")
    organization: str | None = Field(default=None, description="共同任职机构关键词。")
    department: str | None = Field(default=None, description="共同部门、实验室或团队关键词。")
    overlapPeriod: str | None = Field(
        default=None, description="要求覆盖的年份区间，如 2018-2022。"
    )
    limit: int = Field(default=20, ge=1, le=50)
    space: Literal["dev"] = Field(default="dev", description="固定查询 dev 图空间。")

    @field_validator("expertId")
    @classmethod
    def normalize_expert_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("expertId cannot be empty")
        return value


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
    commonDepartment: str | None = None
    commonTeamOrProject: list[str] = Field(default_factory=list)
    effectivePeriod: str
    overlapMonths: int | None = None
    overlapYears: float | None = None
    workContent: list[str] = Field(default_factory=list)
    collaborationScenes: list[str] = Field(default_factory=list)
    achievements: list[ColleagueAchievement] = Field(default_factory=list)
    confidence: float
    evidence: list[str] = Field(default_factory=list)
    reviewRequired: bool = False


class ExpertColleagueRelationData(BaseModel):
    expert: ColleagueExpert
    colleagues: list[ColleagueRelationItem]
    total: int
    summary: dict[str, Any]
    graph: dict[str, list[dict[str, Any]]]
    rules: list[dict[str, Any]] = Field(default_factory=list)
    apiCalls: list[dict[str, Any]]
