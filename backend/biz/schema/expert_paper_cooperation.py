import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EXPERT_ID_PATTERN = r"^[\w\u4e00-\u9fff·.\-]+$"
DATE_PATTERN = r"^\d{4}(?:-\d{2}){0,2}$"


def _boundary_date(value: str, *, end: bool) -> date:
    """YYYY / YYYY-MM / YYYY-MM-DD → 起止边界日历日（end=False 取当期首日）。

    与两点合作成果模块同语义：年/月粒度输入按自然周期取边界，供校验比较；
    过滤本身只取年份（service 层 ``startTime[:4]``）。
    """
    if len(value) == 4:
        return date(int(value), 12 if end else 1, 31 if end else 1)
    if len(value) == 7:
        year, month = map(int, value.split("-"))
        if not 1 <= month <= 12:
            raise ValueError(f"月份越界: {value}")
        if not end:
            return date(year, month, 1)
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return date.fromordinal(next_month.toordinal() - 1)
    return datetime.strptime(value, "%Y-%m-%d").date()


class ExpertPaperCooperationDemoRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "expertAId": "person_121d48631f434f4d323ba521d33032ad",
                "expertBId": "person_42914016fe8d6e0e1d01dad5845c47e6",
                "startTime": "2021-01-01",
                "endTime": "2024-12-31",
            }
        }
    )

    expertAId: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=EXPERT_ID_PATTERN,
        description="专家 A 的 VID、scholar_id、source_record_id 或精确姓名。",
    )
    expertBId: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=EXPERT_ID_PATTERN,
        description="专家 B 的 VID、scholar_id、source_record_id 或精确姓名。",
    )
    startTime: str | None = Field(
        default=None, description="统计开始时间，格式 YYYY / YYYY-MM / YYYY-MM-DD（过滤按年份）。"
    )
    endTime: str | None = Field(
        default=None, description="统计结束时间，格式 YYYY / YYYY-MM / YYYY-MM-DD（过滤按年份）。"
    )

    @field_validator("expertAId", "expertBId", mode="before")
    @classmethod
    def normalize_expert_id(cls, value: str) -> str:
        if value is None:
            return value
        value = str(value)
        if re.search(r"\s", value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        value = value.strip()
        if len(value) > 64:
            raise ValueError("专家标识长度不能超过 64 个字符")
        if value and not re.fullmatch(EXPERT_ID_PATTERN, value):
            raise ValueError("专家标识不能包含空格或 !@#￥%& 等异常字符")
        return value

    @field_validator("startTime", "endTime", mode="before")
    @classmethod
    def normalize_optional_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        if not re.fullmatch(DATE_PATTERN, value):
            raise ValueError("时间格式错误，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD")
        return value

    @field_validator("startTime", "endTime")
    @classmethod
    def validate_calendar_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            _boundary_date(value, end=True)
        except ValueError as exc:
            raise ValueError("时间格式错误，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD") from exc
        return value

    @model_validator(mode="after")
    def validate_experts(self):
        if self.expertAId == self.expertBId:
            raise ValueError("expertAId 和 expertBId 不能相同")
        today = date.today()
        if self.startTime and _boundary_date(self.startTime, end=False) > today:
            raise ValueError("startTime 超出当前时间")
        if self.endTime and _boundary_date(self.endTime, end=True) > today:
            raise ValueError("endTime 超出当前时间")
        if self.startTime and self.endTime:
            if _boundary_date(self.startTime, end=False) > _boundary_date(self.endTime, end=True):
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
    stableTeamNote: str = Field(
        default="", description="未构成长期稳定合作团队时的原因说明；已构成时为空。"
    )
    coreCollaborators: list[str] = Field(default_factory=list, description="核心合作人员。")
    sharedContribution: list[str] = Field(default_factory=list, description="合作贡献标签。")
    relationConfidences: dict[str, float] = Field(
        default_factory=dict,
        description="按结构化证据规则计算的各类论文合作关系置信度，取值范围 0-1。",
    )


class PaperCooperationProvenanceEvidence(BaseModel):
    title: str
    sourceTable: str
    sourceField: str
    graphVid: str
    summary: str = Field(default="", description="来源性质说明（入库血缘或图库查询）。")


class PaperCooperationProvenance(BaseModel):
    sourceDatabase: str
    summary: str
    evidences: list[PaperCooperationProvenanceEvidence] = Field(default_factory=list)


class PaperCooperationGraphNode(BaseModel):
    id: str
    type: str
    label: str
    subtitle: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class PaperCooperationGraphEdge(BaseModel):
    source: str
    target: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class PaperCooperationGraph(BaseModel):
    nodes: list[PaperCooperationGraphNode] = Field(default_factory=list)
    edges: list[PaperCooperationGraphEdge] = Field(default_factory=list)


class ExpertPaperCooperationStructuredResultOnlyResponse(BaseModel):
    structuredResult: StructuredPaperCooperationResult
    provenance: PaperCooperationProvenance
    graph: PaperCooperationGraph = Field(
        default_factory=PaperCooperationGraph,
        description="查到即记组装的真实合作子图（专家/论文/主题/期刊/合作者）。",
    )
    rules: list[dict[str, Any]] = Field(default_factory=list)
