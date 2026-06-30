from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DataSource = Literal["all", "knowledge_graph", "cnki", "wanfang", "web_of_science"]


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
    expertAId: str = Field(..., min_length=1, description="专家A唯一标识。")
    expertBId: str = Field(..., min_length=1, description="专家B唯一标识。")
    startTime: str | None = Field(default=None, description="统计开始时间，格式 YYYY-MM-DD。")
    endTime: str | None = Field(default=None, description="统计结束时间，格式 YYYY-MM-DD。")

    @model_validator(mode="after")
    def validate_experts(self):
        if self.expertAId == self.expertBId:
            raise ValueError("expertAId 和 expertBId 不能相同")
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
