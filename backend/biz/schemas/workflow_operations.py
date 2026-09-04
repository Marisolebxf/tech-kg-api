"""任务中心、人工审核和工作流控制面请求模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_TIMEZONE = "Asia/Shanghai"


class UpdatePolicyRequest(BaseModel):
    enabled: bool = True
    frequency: Literal["每天", "每12小时", "每6小时", "每周"] = "每天"
    execution_time: str = Field(
        default="02:00", alias="executionTime", pattern=r"^([01]\d|2[0-3]):[0-5]\d$"
    )
    timezone: str = DEFAULT_TIMEZONE
    skip_when_no_changes: bool = Field(default=True, alias="skipWhenNoChanges")

    model_config = {"populate_by_name": True}


class TriggerGraphBuildRequest(BaseModel):
    domains: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    since: str | None = None
    reason: str = "客户端立即触发"
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewActionRequest(BaseModel):
    action_id: str = Field(alias="actionId")
    note: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    handler: str | None = None
    rerun: bool = False

    model_config = {"populate_by_name": True}


class ReviewResultRequest(BaseModel):
    result: dict[str, Any]
    note: str = ""
    handler: str | None = None


class RetryRequest(BaseModel):
    note: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=1)
    handler: str | None = None


class WorkflowDefinitionRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    name: str = Field(min_length=1, max_length=100)
    category: Literal["entity", "relation", "graph", "custom"] = "custom"
    steps: list[str | dict[str, Any]] = Field(min_length=1)
    task_queue: str = Field(default="tech-kg-workflows", alias="taskQueue")
    active: bool = True

    model_config = {"populate_by_name": True}


class WorkflowExecuteRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict, strict=True)
    workflow_id: str | None = Field(default=None, alias="workflowId")
    llm_config_id: str | None = Field(default=None, alias="llmConfigId")
    embedding_config_id: str | None = Field(default=None, alias="embeddingConfigId")
    mysql_datasource_id: str | None = Field(default=None, alias="mysqlDatasourceId")
    mysql_database: str | None = Field(default=None, alias="mysqlDatabase")
    milvus_config_id: str | None = Field(default=None, alias="milvusConfigId")
    milvus_database: str | None = Field(default=None, alias="milvusDatabase")
    graph_space: str | None = Field(default=None, alias="graphSpace")
    since: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator("payload")
    @classmethod
    def validate_limit(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "limit" in value:
            limit = value["limit"]
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("limit 必须为正整数")
        return value


class WorkflowScheduleRequest(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,127}$")
    cron: str = Field(min_length=5, max_length=100)
    timezone: str = DEFAULT_TIMEZONE
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


class RetryPolicyConfig(BaseModel):
    """Per-step Temporal RetryPolicy；缺省 maximumAttempts=1 不重试。"""

    maximum_attempts: int = Field(default=1, ge=1, alias="maximumAttempts")
    initial_interval_seconds: int = Field(default=1, ge=1, alias="initialIntervalSeconds")
    maximum_interval_seconds: int = Field(default=100, ge=1, alias="maximumIntervalSeconds")
    non_retryable_error_types: list[str] | None = Field(
        default=None, alias="nonRetryableErrorTypes"
    )

    model_config = {"populate_by_name": True}


class StepManifest(BaseModel):
    """kg.custom.steps 流水线中单个 step 的声明。"""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)
    function_name: str = Field(alias="functionName", pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    timeout_seconds: int = Field(default=600, ge=1, alias="timeoutSeconds")
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig, alias="retryPolicy")

    model_config = {"populate_by_name": True}


class TaskRetryRequest(BaseModel):
    """失败任务重试：调 Temporal ResetWorkflowExecution。"""

    reason: str = "manual retry"


class WorkflowChainRequest(BaseModel):
    """多脚本串行链：按顺序串行执行多个已注册 python 定义。"""

    name: str = Field(min_length=1, max_length=100)
    definition_ids: list[str] = Field(min_length=1, max_length=20, alias="definitionIds")
    definition_id: str | None = Field(default=None, alias="definitionId")

    model_config = {"populate_by_name": True}


class JobScheduleSpec(BaseModel):
    """任务调度方式：一次性 / cron 周期。"""

    kind: Literal["once", "cron"] = "once"
    cron: str | None = Field(default=None, min_length=5, max_length=100)
    timezone: str = DEFAULT_TIMEZONE


class JobCreateRequest(BaseModel):
    """任务中心新建任务：single 单脚本 / chain 多脚本串行 / upload 上传脚本 / extract 数据抽取。"""

    name: str = Field(min_length=1, max_length=128)
    task_type: Literal["single", "chain", "upload", "extract"] = Field(
        default="single", alias="taskType"
    )
    definition_id: str | None = Field(default=None, alias="definitionId")
    definition_ids: list[str] | None = Field(default=None, max_length=20, alias="definitionIds")
    # extract 任务：目标 Schema（须已传脚本且绑定来源表）
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
    """编辑任务：名称 / 脚本顺序 / 资源选择器 / cron。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    definition_ids: list[str] | None = Field(default=None, max_length=20, alias="definitionIds")
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
