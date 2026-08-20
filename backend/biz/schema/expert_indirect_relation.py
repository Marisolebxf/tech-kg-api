from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

NODE_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


class ExpertIndirectRelationRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "core_node_id": "4G7t0B0t",
                "relation_types": ["学术关联", "机构关联"],
                "path_depth": 2,
                "min_strength": 0.65,
            }
        }
    )

    core_node_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=NODE_ID_PATTERN,
        description="核心专家或人才节点 ID。",
    )
    relation_types: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="需要保留的间接关系类型；空列表表示全部类型。",
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
        return str(value).strip()

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


class ExpertIndirectRelationResponse(BaseModel):
    structuredResult: StructuredIndirectRelationResult
