"""任务中心、人工审核和工作流控制面请求模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import check_text


def _check_id(value):
    if value is None or value == "":
        return value
    return check_text(str(value).strip(), label="标识")


def _check_text(value):
    if value is None or value == "":
        return value
    return check_text(str(value).strip(), label="输入", allow_space=True)


class UpdatePolicyRequest(BaseModel):
    enabled: bool = True
    frequency: Literal["每天", "每12小时", "每6小时", "每周"] = "每天"
    execution_time: str = Field(
        default="02:00", alias="executionTime", pattern=r"^([01]\d|2[0-3]):[0-5]\d$"
    )
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    skip_when_no_changes: bool = Field(default=True, alias="skipWhenNoChanges")

    model_config = {"populate_by_name": True}


class TriggerGraphBuildRequest(BaseModel):
    domains: list[str] = Field(default_factory=list, max_length=64)
    entities: list[str] = Field(default_factory=list, max_length=64)
    relations: list[str] = Field(default_factory=list, max_length=64)
    since: str | None = None
    reason: str = "客户端立即触发"
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("domains", "entities", "relations", mode="before")
    @classmethod
    def _validate_catalog_items(cls, v: list[str]) -> list[str]:
        if not v:
            return v
        return [_check_id(item) for item in v]

    @field_validator("since", mode="before")
    @classmethod
    def _validate_since(cls, v: str | None) -> str | None:
        return _check_id(v)

    @field_validator("reason", mode="before")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return _check_text(v)


class ReviewActionRequest(BaseModel):
    action_id: str = Field(alias="actionId", min_length=1, max_length=64)
    note: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    handler: str | None = Field(default=None, max_length=64)
    rerun: bool = False

    model_config = {"populate_by_name": True}

    @field_validator("action_id", "handler", mode="before")
    @classmethod
    def _validate_ids(cls, v: str | None) -> str | None:
        return _check_id(v)

    @field_validator("note", mode="before")
    @classmethod
    def _validate_note(cls, v: str) -> str:
        return _check_text(v)


class ReviewResultRequest(BaseModel):
    result: dict[str, Any]
    note: str = ""
    handler: str | None = Field(default=None, max_length=64)

    @field_validator("handler", mode="before")
    @classmethod
    def _validate_handler(cls, v: str | None) -> str | None:
        return _check_id(v)

    @field_validator("note", mode="before")
    @classmethod
    def _validate_note(cls, v: str) -> str:
        return _check_text(v)


class RetryRequest(BaseModel):
    note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("note", mode="before")
    @classmethod
    def _validate_note(cls, v: str) -> str:
        return _check_text(v)


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=64)
    handler: str | None = Field(default=None, max_length=64)

    @field_validator("handler", mode="before")
    @classmethod
    def _validate_handler(cls, v: str | None) -> str | None:
        return _check_id(v)

    @field_validator("reason", mode="before")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return _check_text(v)


class WorkflowDefinitionRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    name: str = Field(min_length=1, max_length=64)
    category: Literal["entity", "relation", "graph", "custom"] = "custom"
    steps: list[str | dict[str, Any]] = Field(min_length=1)
    task_queue: str = Field(default="tech-kg-workflows", alias="taskQueue", max_length=64)
    active: bool = True

    model_config = {"populate_by_name": True}

    @field_validator("name", "task_queue", mode="before")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        return _check_id(v)

    @field_validator("steps", mode="before")
    @classmethod
    def _validate_steps(cls, v: list[str | dict[str, Any]]) -> list[str | dict[str, Any]]:
        if not v:
            return v
        for item in v:
            if isinstance(item, str):
                _check_id(item)
        return v


class WorkflowExecuteRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict, strict=True)
    workflow_id: str | None = Field(default=None, alias="workflowId", max_length=64)
    llm_config_id: str | None = Field(default=None, alias="llmConfigId", max_length=64)
    since: str | None = Field(default=None, max_length=64)

    model_config = {"populate_by_name": True}

    @field_validator("workflow_id", "llm_config_id", "since", mode="before")
    @classmethod
    def _validate_ids(cls, v: str | None) -> str | None:
        return _check_id(v)

    @field_validator("payload")
    @classmethod
    def validate_limit(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "limit" not in value:
            return value
        limit = value["limit"]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit 必须为正整数")
        return value


class WorkflowScheduleRequest(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")
    cron: str = Field(min_length=5, max_length=64)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    active: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduleStateRequest(BaseModel):
    active: bool
