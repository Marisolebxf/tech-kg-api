from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DataSource = Literal["all"]
MAX_KEY_ENTITIES = 20


class IndustryChainPanoramaQueryRequest(BaseModel):
    """产业链全景图查询请求。

    - ``industry``：产业关键词，用于过滤/匹配核心节点；空则整体全景。
    - ``anchorId``：可选，指定核心节点 VID（如 ``person_xxx``、``paper_xxx``）从此扩展子图。
    - ``depth``：从核心节点向外扩展的跳数（1-3）。
    - ``topK``：每类关键实体（专家/机构/论文）返回条数。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dataSource": "all",
                "industry": "人工智能",
                "anchorId": "",
                "depth": 2,
                "topK": 5,
            }
        }
    )

    dataSource: DataSource = Field(default="all", description="数据来源，固定为 all。")
    industry: str | None = Field(default=None, description="产业关键词，如 人工智能 / 集成电路。")
    anchorId: str | None = Field(default=None, description="核心节点 VID，用于生成扩展子图。")
    depth: int = Field(default=2, ge=1, le=3, description="子图扩展跳数 1-3。")
    topK: int = Field(
        default=5, ge=1, description=f"每类实体返回数上限 (最大 {MAX_KEY_ENTITIES})。"
    )

    @field_validator("topK")
    @classmethod
    def clamp_top_k(cls, value: int) -> int:
        return min(value, MAX_KEY_ENTITIES)


class PanoramaKeyEntity(BaseModel):
    id: str
    label: str
    type: str
    subtitle: str | None = None
    metric: str | None = None
    metricValue: float | int | None = None
    sourceSystem: str | None = None
    sourceRecordId: str | None = None
    ingestBatch: str | None = None
    ingestTime: str | None = None


class PanoramaLayer(BaseModel):
    """全景图分层：核心技术 / 领军企业 / 领军专家 / 代表成果。"""

    key: str
    title: str
    total: int
    items: list[PanoramaKeyEntity] = Field(default_factory=list)


class PanoramaGraphNode(BaseModel):
    id: str
    type: str
    label: str
    subtitle: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class PanoramaGraphEdge(BaseModel):
    source: str
    target: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class PanoramaSummary(BaseModel):
    industry: str | None
    totalNodes: int
    totalEdges: int
    nodesByLabel: dict[str, int]
    edgesByType: dict[str, int]


class IndustryChainPanoramaQueryResponse(BaseModel):
    taskName: str
    input: dict[str, Any]
    summary: PanoramaSummary
    layers: list[PanoramaLayer]
    graph: dict[str, list[Any]]
    source: dict[str, Any]
    provenance: dict[str, Any] | None = None
    apiResultExample: dict[str, Any]
