"""角色与合作详情标注 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import EDGE_ID_TEXT_PATTERN, check_text
from service.enterprise_relation_catalog import role_info


class Period(BaseModel):
    start: str | None = None
    end: str | None = None


class RelationDetailAnnotationRequest(BaseModel):
    relationId: str = Field(..., min_length=1, max_length=64, description="EMPLOYED_BY 边 ID")
    roleType: str
    techField: str = Field(default="", max_length=64, description="技术领域")
    period: Period = Field(default_factory=Period)

    @field_validator("relationId", mode="before")
    @classmethod
    def _validate_relation_id(cls, v: str) -> str:
        if v is None:
            return v
        # 边 ID 形如 scholar_id->enterprise_id@0,额外允许 > 与 @
        return check_text(str(v).strip(), label="关系 ID", pattern=EDGE_ID_TEXT_PATTERN)

    @field_validator("techField", mode="before")
    @classmethod
    def _validate_tech_field(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="技术领域", allow_space=True)

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
