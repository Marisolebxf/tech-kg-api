import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DataSource = Literal["all"]
MAX_KEY_ENTITIES = 20
MAX_TEXT_LENGTH = 64
MAX_RELATION_TYPES = 20

# 产业关键词：字母数字下划线、中文、间隔号、点、连字符、括号、顿号、斜杠和空格
INDUSTRY_PATTERN = re.compile(r"[\w\u4e00-\u9fff·.\-()（）、，,/\s]+")
# 核心节点 VID：不允许空格与 !@#￥%& 等符号
ANCHOR_ID_PATTERN = re.compile(r"[\w\u4e00-\u9fff·.\-]+")
# 关系类型（Nebula 边类型）：大写字母、数字和下划线
RELATION_TYPE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


class IndustryChainPanoramaQueryRequest(BaseModel):
    """产业链全景图查询请求。

    - ``industry``：产业关键词，用于过滤/匹配核心节点；空则整体全景。
    - ``anchorId``：可选，指定核心节点 VID（如 ``person_xxx``、``paper_xxx``）从此扩展子图。
    - ``depth``：从核心节点向外扩展的跳数（1-3）。
    - ``topK``：每类关键实体（专家/机构/论文）返回条数。
    - ``relationTypes``：关系筛选，只保留这些边类型的子图关系；空则不筛选。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dataSource": "all",
                "industry": "人工智能",
                "anchorId": "",
                "depth": 2,
                "topK": 5,
                "relationTypes": ["COAUTHOR_WITH", "AFFILIATED_WITH"],
            }
        }
    )

    dataSource: DataSource = Field(default="all", description="数据来源，固定为 all。")
    industry: str | None = Field(
        default=None,
        description=f"产业关键词，如 人工智能 / 集成电路，最多 {MAX_TEXT_LENGTH} 个字符。",
    )
    anchorId: str | None = Field(
        default=None,
        description=f"核心节点 VID，用于生成扩展子图，最多 {MAX_TEXT_LENGTH} 个字符。",
    )
    depth: int = Field(default=2, ge=1, le=3, description="子图扩展跳数 1-3。")
    topK: int = Field(
        default=5, ge=1, description=f"每类实体返回数上限 (最大 {MAX_KEY_ENTITIES})。"
    )
    relationTypes: list[str] | None = Field(
        default=None,
        description=(
            "关系筛选：只保留这些边类型（如 COAUTHOR_WITH / AFFILIATED_WITH），"
            f"最多 {MAX_RELATION_TYPES} 项；留空表示不筛选。"
        ),
    )
    refresh: bool = Field(
        default=False, description="true 时忽略服务端缓存，强制重新组装分层与子图。"
    )

    @field_validator("topK")
    @classmethod
    def clamp_top_k(cls, value: int) -> int:
        return min(value, MAX_KEY_ENTITIES)

    @field_validator("relationTypes", mode="before")
    @classmethod
    def normalize_relation_types(cls, value: Any) -> list[str] | None:
        if value is None or value == "":
            return None
        # 兼容前端用逗号拼接传参
        items = value.split(",") if isinstance(value, str) else value
        if not isinstance(items, list):
            raise ValueError("关系筛选必须是边类型数组")
        normalized: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise ValueError("关系筛选必须是边类型数组")
            name = item.strip().upper()
            if not name:
                continue
            if len(name) > MAX_TEXT_LENGTH:
                raise ValueError(f"关系类型长度不能超过 {MAX_TEXT_LENGTH} 个字符")
            if not RELATION_TYPE_PATTERN.fullmatch(name):
                raise ValueError("关系类型只能包含字母、数字和下划线")
            if name not in normalized:
                normalized.append(name)
        if not normalized:
            return None
        if len(normalized) > MAX_RELATION_TYPES:
            raise ValueError(f"关系筛选最多选择 {MAX_RELATION_TYPES} 项")
        return normalized

    @field_validator("industry", mode="before")
    @classmethod
    def normalize_industry(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("产业关键词必须是字符串")
        value = value.strip()
        if not value:
            return None
        if len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"产业关键词长度不能超过 {MAX_TEXT_LENGTH} 个字符")
        if not INDUSTRY_PATTERN.fullmatch(value):
            raise ValueError("产业关键词不能包含 !@#￥%& 等异常字符")
        return value

    @field_validator("anchorId", mode="before")
    @classmethod
    def normalize_anchor_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("核心节点标识必须是字符串")
        value = value.strip()
        if not value:
            return None
        if len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"核心节点标识长度不能超过 {MAX_TEXT_LENGTH} 个字符")
        if re.search(r"\s", value):
            raise ValueError("核心节点标识不能包含空格或 !@#￥%& 等异常字符")
        if not ANCHOR_ID_PATTERN.fullmatch(value):
            raise ValueError("核心节点标识不能包含空格或 !@#￥%& 等异常字符")
        return value


class PanoramaKeyEntity(BaseModel):
    id: str
    label: str
    type: str
    subtitle: str | None = None
    metric: str | None = None
    metricValue: float | int | None = None
    sourceSystem: str | None = None
    sourceTable: str | None = None
    sourceField: str | None = None
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
