"""专家-企业关系构建 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start: str | None = None
    end: str | None = None


class ExpertEnterpriseBuildRequest(BaseModel):
    dataSource: str = "all"
    expertAId: str
    relationType: str = "all"
    timeRange: TimeRange | None = None


class EnterpriseItem(BaseModel):
    enterprise_id: str
    name: str
    type: str = ""
    province: str = ""
    relation: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""


class ExpertEnterpriseBuildResponse(BaseModel):
    status: str = "success"
    expert: str | None = None
    expert_id: str | None = None
    title: str | None = None
    enterprises: list[EnterpriseItem] = Field(default_factory=list)
