"""角色与合作详情标注 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from service.enterprise_relation_catalog import role_info


class Period(BaseModel):
    start: str | None = None
    end: str | None = None


class RelationDetailAnnotationRequest(BaseModel):
    relationId: str
    roleType: str
    techField: str = ""
    period: Period = Field(default_factory=Period)

    @field_validator("roleType")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        role_info(v)
        return v


class RelationDetailAnnotationResponse(BaseModel):
    status: str = "success"
    relationId: str
    roleType: str
    roleLabel: str
    roleLevel: str
    techField: str = ""
    period: Period = Field(default_factory=Period)
    annotated: bool = False
