"""专家-企业关系构建 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpertEnterpriseBuildRequest(BaseModel):
    scholarId: str
    enterpriseId: str
    relationTypes: list[str] = Field(default_factory=list)


class BuiltRelation(BaseModel):
    relationId: str
    relationType: str
    effective: bool


class ExpertEnterpriseBuildResponse(BaseModel):
    status: str = "success"
    scholarId: str
    enterpriseId: str
    scholarName: str | None = None
    enterpriseName: str | None = None
    relations: list[BuiltRelation] = Field(default_factory=list)
