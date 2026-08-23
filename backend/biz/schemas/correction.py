"""人工修正、审核同步和成员管理请求模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TargetType = Literal["expert", "organization", "relation"]
CorrectionOperation = Literal["create", "update", "delete"]


class CorrectionCreateRequest(BaseModel):
    target_type: TargetType
    operation: CorrectionOperation
    target_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=2, max_length=255)
    reason: str = Field(min_length=2, max_length=2000)
    before_data: dict = Field(default_factory=dict)
    after_data: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.operation != "delete" and not self.after_data:
            raise ValueError("新增或修改必须填写修正后的数据")
        return self


class CorrectionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    reason: str | None = Field(default=None, min_length=2, max_length=2000)
    before_data: dict | None = None
    after_data: dict | None = None


class CorrectionReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)


class CorrectionRetryRequest(BaseModel):
    note: str = Field(default="", max_length=1000)


class AdminRoleUpdateRequest(BaseModel):
    is_admin: bool
