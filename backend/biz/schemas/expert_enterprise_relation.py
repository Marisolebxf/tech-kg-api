"""专家-企业关系构建 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpertEnterpriseBuildRequest(BaseModel):
    scholarId: str
    enterpriseId: str
    relationType: str


class RelationItem(BaseModel):
    relationId: str
    enterpriseId: str
    enterpriseName: str
    relationType: str


class ExpertEnterpriseBuildResponse(BaseModel):
    status: str = "success"
    scholarId: str
    scholarName: str | None = None
    builtRelationId: str | None = None
    relationType: str = ""
    effective: bool = False
    relations: list[RelationItem] = Field(default_factory=list)
