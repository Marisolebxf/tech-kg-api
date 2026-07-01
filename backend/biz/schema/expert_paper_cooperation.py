from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DataSource = Literal["all", "knowledge_graph", "cnki", "wanfang", "web_of_science"]
EXPERT_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class ExpertPaperCooperationDemoRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dataSource": "knowledge_graph",
                "expertAId": "4P566No1",
                "expertBId": "d492835p",
                "startTime": "2021-01-01",
                "endTime": "2024-12-31",
            }
        }
    )

    dataSource: DataSource = Field(
        ..., description="论文数据源：all、knowledge_graph、cnki、wanfang、web_of_science。"
    )
    expertAId: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=EXPERT_ID_PATTERN,
        description="专家A唯一标识，仅支持字母、数字、下划线和中划线。",
    )
    expertBId: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=EXPERT_ID_PATTERN,
        description="专家B唯一标识，仅支持字母、数字、下划线和中划线。",
    )
    startTime: str | None = Field(
        default=None, pattern=DATE_PATTERN, description="统计开始时间，格式 YYYY-MM-DD。"
    )
    endTime: str | None = Field(
        default=None, pattern=DATE_PATTERN, description="统计结束时间，格式 YYYY-MM-DD。"
    )

    @field_validator("expertAId", "expertBId", mode="before")
    @classmethod
    def normalize_expert_id(cls, value: str) -> str:
        if value is None:
            return value
        return str(value).strip()

    @field_validator("startTime", "endTime", mode="before")
    @classmethod
    def normalize_optional_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("startTime", "endTime")
    @classmethod
    def validate_calendar_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("时间格式错误，请使用有效日期 YYYY-MM-DD") from exc
        return value

    @model_validator(mode="after")
    def validate_experts(self):
        if self.expertAId == self.expertBId:
            raise ValueError("expertAId 和 expertBId 不能相同")
        if self.startTime and self.endTime:
            start_date = date.fromisoformat(self.startTime)
            end_date = date.fromisoformat(self.endTime)
            if start_date > end_date:
                raise ValueError("startTime 不能晚于 endTime")
        return self


class ExpertBrief(BaseModel):
    expertId: str
    name: str
    organization: str
    title: str
    researchDirection: list[str] = Field(default_factory=list)
    paperCount: int = 0
    citationCount: int = 0
    hIndex: float = 0


class CitationSummary(BaseModel):
    total: int
    max: int


class CooperationTimeRange(BaseModel):
    startYear: int
    endYear: int
    displayText: str


class StructuredPaperCooperationResult(BaseModel):
    authorList: list[str] = Field(..., description="作者列表。")
    authorUnits: list[str] = Field(..., description="作者单位，按专家A/专家B顺序输出。")
    cooperationTimeRange: CooperationTimeRange = Field(..., description="合作发表时间范围。")
    paperTopics: list[str] = Field(..., description="合作论文主题列表。")
    cooperationPaperCount: int = Field(..., description="合作论文数量。")
    journalLevelCount: dict[str, int] = Field(..., description="期刊级别统计。")
    conferenceLevelCount: dict[str, int] = Field(..., description="会议级别统计。")
    citation: CitationSummary = Field(..., description="论文被引情况。")
    cooperationFrequency: int = Field(..., description="合作频次。")
    academicImpactScore: float = Field(..., description="学术影响力/核心贡献评分。")
    stableTeamMembers: list[str] = Field(default_factory=list, description="长期稳定合作团队成员。")
    coreCollaborators: list[str] = Field(default_factory=list, description="核心合作人员。")
    sharedContribution: list[str] = Field(default_factory=list, description="合作贡献标签。")


class ExpertPaperCooperationStructuredResultOnlyResponse(BaseModel):
    structuredResult: StructuredPaperCooperationResult
