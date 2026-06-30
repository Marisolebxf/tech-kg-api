from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DataSource = Literal["all"]
MAX_QUERY_LIMIT = 100


class ExpertDirectRelationQueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dataSource": "all",
                "expertAId": "王祎",
                "expertBId": "",
                "institution": "",
                "startTime": "",
                "endTime": "",
                "limit": 10,
            }
        }
    )

    dataSource: DataSource = Field(default="all", description="数据来源，固定为 all。")
    expertAId: str | None = Field(default=None, description="专家A scholar_id 或姓名关键词。")
    expertBId: str | None = Field(default=None, description="专家B scholar_id 或姓名关键词。")
    institution: str | None = Field(default=None, description="机构关键词。")
    startTime: str | None = Field(default=None, description="开始日期 YYYY-MM-DD。")
    endTime: str | None = Field(default=None, description="结束日期 YYYY-MM-DD。")
    limit: int = Field(default=10, ge=1, description=f"返回结果数，最大 {MAX_QUERY_LIMIT}。")

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return min(value, MAX_QUERY_LIMIT)


class DirectRelationExpert(BaseModel):
    expertId: str
    name: str
    organization: str | None = None
    title: str = "专家"
    paperCount: int = 0
    citationCount: int = 0
    hIndex: int = 0


class DirectRelationItem(BaseModel):
    key: str
    relationType: str = "直接关系"
    expertA: DirectRelationExpert
    expertB: DirectRelationExpert
    institution: str | None = None
    coPaperCount: int = 0
    relationStrength: int = 0
    reasonTags: list[str] = Field(default_factory=list)
    relationSummary: str = ""
    lastUpdatedAt: str | None = None
    detailRows: list[list[Any]] = Field(default_factory=list)


class DirectRelationGraphNode(BaseModel):
    id: str
    type: str
    label: str
    subtitle: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DirectRelationGraphEdge(BaseModel):
    source: str
    target: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class ExpertDirectRelationQueryResponse(BaseModel):
    taskName: str
    input: dict[str, Any]
    total: int
    items: list[DirectRelationItem]
    graph: dict[str, list[Any]]
    source: dict[str, Any]
    apiResultExample: dict[str, Any]
