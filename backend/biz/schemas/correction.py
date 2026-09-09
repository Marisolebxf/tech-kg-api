"""人工修正、审核同步和成员管理请求模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from biz.schemas.text_rules import EDGE_ID_TEXT_PATTERN, check_text

TargetType = Literal["expert", "organization", "relation"]
CorrectionOperation = Literal["create", "update", "delete"]


class CorrectionCreateRequest(BaseModel):
    target_type: TargetType
    operation: CorrectionOperation
    target_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=2, max_length=64)
    reason: str = Field(min_length=2, max_length=64)
    before_data: dict = Field(default_factory=dict)
    after_data: dict = Field(default_factory=dict)

    @field_validator("target_id", mode="before")
    @classmethod
    def _validate_target_id(cls, v: str) -> str:
        if v is None:
            return v
        # 目标可能是节点 VID,也可能是 scholar->org@0 形式的边 ID
        return check_text(str(v).strip(), label="目标 ID", pattern=EDGE_ID_TEXT_PATTERN)

    @field_validator("title", "reason", mode="before")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="标题/原因", allow_space=True)

    @model_validator(mode="after")
    def validate_payload(self):
        if self.operation != "delete" and not self.after_data:
            raise ValueError("新增或修改必须填写修正后的数据")
        return self


class CorrectionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=64)
    reason: str | None = Field(default=None, min_length=2, max_length=64)
    before_data: dict | None = None
    after_data: dict | None = None

    @field_validator("title", "reason", mode="before")
    @classmethod
    def _validate_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return check_text(str(v).strip(), label="标题/原因", allow_space=True)


class CorrectionReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=64)

    @field_validator("note", mode="before")
    @classmethod
    def _validate_note(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="审核意见", allow_space=True)


class CorrectionRetryRequest(BaseModel):
    note: str = Field(default="", max_length=64)

    @field_validator("note", mode="before")
    @classmethod
    def _validate_note(cls, v: str) -> str:
        if v is None:
            return v
        return check_text(str(v).strip(), label="重试说明", allow_space=True)


class AdminRoleUpdateRequest(BaseModel):
    is_admin: bool
