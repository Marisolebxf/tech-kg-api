"""专家-企业关系构建 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from service.enterprise_relation_catalog import validate_relation_types


class ExpertEnterpriseBuildRequest(BaseModel):
    scholarId: str
    enterpriseId: str
    relationTypes: list[str]

    @field_validator("relationTypes")
    @classmethod
    def _validate_relation_types(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("relationTypes 不能为空")
        return validate_relation_types(v)


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
