"""任务中心、人工审核和工作流控制面请求模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from biz.schemas.text_rules import check_text

DEFAULT_TIMEZONE = "Asia/Shanghai"


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
    timezone: str = Field(default=DEFAULT_TIMEZONE, max_length=64)
    skip_when_no_changes: bool = Field(default=True, alias="skipWhenNoChanges")

    model_config = {"populate_by_name": True}


class TriggerGraphBuildRequest(BaseModel):
    """POST /task-center/trigger：遍历可抽取 schema 全量触发 kg.schema.extract（D3 重指向）。

    旧 domains/entities/relations 域选择器已随 kg.graph.build stub 族删除——
    触发范围即"已上传脚本且绑定来源的全部 schema"。
    """

    since: str | None = None
    reason: str = "客户端立即触发"

    @field_validator("since", mode="before")
    @classmethod
    def _validate_since(cls, v: str | None) -> str | None:
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
        return [_check_id(item) if isinstance(item, str) else item for item in v]


class WorkflowExecuteRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict, strict=True)
    workflow_id: str | None = Field(default=None, alias="workflowId", max_length=64)
    llm_config_id: str | None = Field(default=None, alias="llmConfigId", max_length=64)
    embedding_config_id: str | None = Field(default=None, alias="embeddingConfigId", max_length=64)
    mysql_datasource_id: str | None = Field(default=None, alias="mysqlDatasourceId", max_length=64)
    mysql_database: str | None = Field(default=None, alias="mysqlDatabase", max_length=64)
    milvus_config_id: str | None = Field(default=None, alias="milvusConfigId", max_length=64)
    milvus_database: str | None = Field(default=None, alias="milvusDatabase", max_length=64)
    graph_space: str | None = Field(default=None, alias="graphSpace", max_length=64)
    since: str | None = Field(default=None, max_length=64)

    model_config = {"populate_by_name": True}

    @field_validator(
        "workflow_id",
        "llm_config_id",
        "embedding_config_id",
        "mysql_datasource_id",
        "milvus_config_id",
        "since",
        mode="before",
    )
    @classmethod
    def _validate_ids(cls, v: str | None) -> str | None:
        return _check_id(v)

    @field_validator("payload")
    @classmethod
    def validate_limit(cls, value: dict[str, Any]) -> dict[str, Any]:
        validated = dict(value)
        if "limit" in validated:
            limit = validated["limit"]
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("limit 必须为正整数")
        return validated


class WorkflowScheduleRequest(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,127}$")
    cron: str = Field(min_length=5, max_length=100)
    timezone: str = Field(default=DEFAULT_TIMEZONE, max_length=64)
    active: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    llm_config_id: str | None = Field(default=None, alias="llmConfigId")
    embedding_config_id: str | None = Field(default=None, alias="embeddingConfigId")
    mysql_datasource_id: str | None = Field(default=None, alias="mysqlDatasourceId")
    mysql_database: str | None = Field(default=None, alias="mysqlDatabase")
    milvus_config_id: str | None = Field(default=None, alias="milvusConfigId")
    milvus_database: str | None = Field(default=None, alias="milvusDatabase")
    graph_space: str | None = Field(default=None, alias="graphSpace")
    since: str | None = None

    model_config = {"populate_by_name": True}


class ScheduleStateRequest(BaseModel):
    active: bool


class TaskRetryRequest(BaseModel):
    """失败任务重试：调 Temporal ResetWorkflowExecution。"""

    reason: str = "manual retry"


class JobScheduleSpec(BaseModel):
    """任务调度方式：一次性 / cron 周期。"""

    kind: Literal["once", "cron"] = "once"
    cron: str | None = Field(default=None, min_length=5, max_length=100)
    timezone: str = DEFAULT_TIMEZONE


class JobCreateRequest(BaseModel):
    """任务中心新建任务：extract 数据抽取（唯一类型，D2 后脚本通道已收敛到 Schema 管理）。"""

    name: str = Field(min_length=1, max_length=128)
    task_type: Literal["extract"] = Field(default="extract", alias="taskType")
    # 目标 Schema（须已传脚本且绑定来源表）
    schema_id: str | None = Field(default=None, alias="schemaId")
    batch_size: int | None = Field(default=None, ge=1, le=5000, alias="batchSize")
    schedule: JobScheduleSpec = Field(default_factory=JobScheduleSpec)
    run_now: bool = Field(default=False, alias="runNow")
    llm_config_id: str | None = Field(default=None, alias="llmConfigId")
    embedding_config_id: str | None = Field(default=None, alias="embeddingConfigId")
    mysql_datasource_id: str | None = Field(default=None, alias="mysqlDatasourceId")
    mysql_database: str | None = Field(default=None, alias="mysqlDatabase")
    milvus_config_id: str | None = Field(default=None, alias="milvusConfigId")
    milvus_database: str | None = Field(default=None, alias="milvusDatabase")
    graph_space: str | None = Field(default=None, alias="graphSpace")
    since: str | None = None

    model_config = {"populate_by_name": True}


class JobUpdateRequest(BaseModel):
    """编辑任务：名称 / 资源选择器 / cron。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    schedule: JobScheduleSpec | None = None
    llm_config_id: str | None = Field(default=None, alias="llmConfigId")
    embedding_config_id: str | None = Field(default=None, alias="embeddingConfigId")
    mysql_datasource_id: str | None = Field(default=None, alias="mysqlDatasourceId")
    mysql_database: str | None = Field(default=None, alias="mysqlDatabase")
    milvus_config_id: str | None = Field(default=None, alias="milvusConfigId")
    milvus_database: str | None = Field(default=None, alias="milvusDatabase")
    graph_space: str | None = Field(default=None, alias="graphSpace")
    since: str | None = None

    model_config = {"populate_by_name": True}
