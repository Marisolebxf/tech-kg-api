import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IndirectRelationType = Literal["学术关联", "机构关联", "项目关联"]


class ExpertIndirectRelationRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "core_node_id": "4G7t0B0t",
                "relation_types": "学术关联",
                "path_depth": 2,
                "min_strength": 0.65,
            }
        }
    )

    core_node_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="核心专家或人才节点 ID。",
    )
    relation_types: list[IndirectRelationType] = Field(
        ...,
        min_length=1,
        max_length=1,
        description="需要保留的间接关系类型，必须且只能选择：学术关联、机构关联或项目关联中的一项。",
    )
    path_depth: int = Field(default=2, ge=2, le=3, description="路径分析深度，支持 2-3 跳。")
    min_strength: float = Field(
        default=0.65,
        ge=0,
        le=1,
        description="最小关联强度阈值。",
    )

    @field_validator("core_node_id", mode="before")
    @classmethod
    def normalize_core_node_id(cls, value: str) -> str:
        if value is None:
            return value
        value = str(value)
        if re.search(r"\s", value):
            raise ValueError("核心节点 ID 不能包含空格或 !@#￥%& 等异常字符")
        if len(value) > 64:
            raise ValueError("核心节点 ID 长度不能超过 64 个字符")
        if not re.fullmatch(r"[\w\u4e00-\u9fff·.\-]+", value):
            raise ValueError("核心节点 ID 不能包含空格或 !@#￥%& 等异常字符")
        return value

    @field_validator("relation_types", mode="before")
    @classmethod
    def normalize_relation_types(cls, value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            normalized = value.replace("；", ";").replace("，", ",").replace("、", ",")
            return [
                item.strip() for item in normalized.replace(";", ",").split(",") if item.strip()
            ]
        return value


class IndirectNode(BaseModel):
    id: str
    name: str
    entityType: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class IndirectEdge(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class IndirectRelationPath(BaseModel):
    pathId: str
    depth: int
    relationType: str
    strength: float
    pathText: str
    targetNode: IndirectNode
    nodes: list[IndirectNode]
    edges: list[IndirectEdge]


class StructuredIndirectRelationResult(BaseModel):
    coreNode: IndirectNode
    pathDepth: int
    defaultPathDepth: int = Field(
        default=2,
        description="系统默认路径深度；请求未填写 path_depth 时采用 2 跳。",
    )
    minStrength: float
    directNodeCount: int
    indirectNodeCount: int
    pathCount: int
    relationTypeCount: dict[str, int]
    averageStrength: float
    maxStrength: float
    directNodes: list[IndirectNode]
    indirectNodes: list[IndirectNode]
    paths: list[IndirectRelationPath]


class IndirectProvenanceEvidence(BaseModel):
    title: str
    sourceTable: str
    sourceField: str
    graphVid: str


class IndirectProvenance(BaseModel):
    sourceDatabase: str
    summary: str
    evidences: list[IndirectProvenanceEvidence] = Field(default_factory=list)


class ExpertIndirectRelationResponse(BaseModel):
    structuredResult: StructuredIndirectRelationResult
    provenance: IndirectProvenance
    rules: list[dict[str, Any]] = Field(default_factory=list)
