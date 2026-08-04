"""重点关注科技企业关系业务（九大业务之一）请求/响应模型。

对齐前端 service-modules.ts 的 enterprise-relation 契约：
端点 POST /api/v1/kg-service/key-enterprise-relation，请求 {expert_id, enterprise_name,
role_type, industry}，响应 data={enterprises, roles, cooperation_fields, relations}。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BusinessPeriod(BaseModel):
    start: str | None = None
    end: str | None = None


class KeyEnterpriseRelationRequest(BaseModel):
    expert_id: str = Field(..., description="科技专家/人才唯一标识 VID")
    enterprise_name: str = Field("", description="企业名称筛选（模糊）")
    role_type: str = Field("", description="专家企业角色筛选")
    industry: str = Field("", description="企业行业方向筛选")
    key_tech_enterprise_only: bool = Field(
        True, description="只保留重点科技企业（已上市/公司类），排除高校/研究院/MOCK"
    )


class EnterpriseRelationItem(BaseModel):
    enterprise_id: str
    enterprise_name: str | None = None
    cooperation_type: str = ""  # governance / project_cooperation / patent_cooperation
    cooperation_mode: str = ""  # 高管任职/法人代表/项目合作/专利合作/任职/...
    role_label: str | None = None
    role_level: str | None = None
    tech_field: str | None = None
    period: BusinessPeriod = Field(default_factory=BusinessPeriod)
    enterprise_background: dict[str, Any] = Field(default_factory=dict)
    source: str = ""  # 来源边类型或 project_id/patent_id


class KeyEnterpriseRelationResponse(BaseModel):
    expert_id: str
    expert_name: str | None = None
    enterprises: int = 0  # 关联企业数
    roles: int = 0  # 角色类型数
    cooperation_fields: list[str] = Field(default_factory=list)
    relations: list[EnterpriseRelationItem] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
