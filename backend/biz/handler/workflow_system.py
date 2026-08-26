"""工作流定义、脚本上传、执行和 Schedule API。"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import TypeAdapter, ValidationError

from application.workflow_operations import workflow_operations_application
from biz.schemas.common import ApiResponse
from biz.schemas.workflow_operations import (
    ScheduleStateRequest,
    StepManifest,
    WorkflowDefinitionRequest,
    WorkflowExecuteRequest,
    WorkflowScheduleRequest,
)
from service.temporal_runtime import temporal_runtime

router = APIRouter(prefix="/workflow-system", tags=["workflow-system"])
service = workflow_operations_application.service


@router.get("/health", response_model=ApiResponse)
async def workflow_health() -> ApiResponse:
    return ApiResponse(data=await temporal_runtime.health())


@router.get("/definitions", response_model=ApiResponse)
async def list_definitions() -> ApiResponse:
    items = service.repo.list_definitions()
    return ApiResponse(data={"items": items, "total": len(items)})


@router.post("/definitions", response_model=ApiResponse)
async def create_definition(request: WorkflowDefinitionRequest) -> ApiResponse:
    return ApiResponse(
        data=service.create_definition(request.model_dump()), msg="自定义工作流定义已保存"
    )


@router.post("/definitions/python", response_model=ApiResponse)
async def upload_python_definition(
    file: Annotated[UploadFile, File()],
    function_name: Annotated[str, Form()] = "workflow",
    definition_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    timeout_seconds: Annotated[int | None, Form(alias="timeoutSeconds")] = None,
) -> ApiResponse:
    try:
        content = await file.read()
        definition = service.create_python_definition(
            file.filename or "workflow.py",
            content,
            function_name,
            definition_id,
            name,
            timeout_seconds=timeout_seconds,
        )
        return ApiResponse(data=definition, msg="Python 工作流脚本已上传并完成校验")
    except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/definitions/steps", response_model=ApiResponse)
async def upload_step_pipeline_definition(
    file: Annotated[UploadFile, File()],
    steps_json: Annotated[str, Form(alias="steps")],
    definition_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
) -> ApiResponse:
    """上传 kg.custom.steps 流水线脚本 + step manifest。

    steps 为 JSON 编码的 StepManifest 列表（Form 字符串），file 为 Python 脚本。
    """
    try:
        steps_raw = json.loads(steps_json)
        steps = TypeAdapter(list[StepManifest]).validate_python(steps_raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=f"steps manifest 无效: {exc}") from exc
    try:
        content = await file.read()
        definition = service.create_step_pipeline_definition(
            file.filename or "pipeline.py",
            content,
            [s.model_dump(by_alias=True) for s in steps],
            definition_id,
            name,
        )
        return ApiResponse(data=definition, msg="Step pipeline 定义已上传并完成校验")
    except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/definitions/{definition_id}", response_model=ApiResponse)
async def get_definition(definition_id: str) -> ApiResponse:
    definition = service.repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="工作流定义不存在")
    return ApiResponse(data=definition)


@router.post("/definitions/{definition_id}/execute", response_model=ApiResponse)
async def execute_definition(definition_id: str, request: WorkflowExecuteRequest) -> ApiResponse:
    definition = service.repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="工作流定义不存在")
    payload = dict(request.payload)
    if request.llm_config_id is not None:
        payload["llm_config_id"] = request.llm_config_id
    if request.embedding_config_id is not None:
        payload["embedding_config_id"] = request.embedding_config_id
    if request.mysql_datasource_id is not None:
        payload["mysql_datasource_id"] = request.mysql_datasource_id
    if request.mysql_database is not None:
        payload["mysql_database"] = request.mysql_database
    if request.milvus_config_id is not None:
        payload["milvus_config_id"] = request.milvus_config_id
    if request.milvus_database is not None:
        payload["milvus_database"] = request.milvus_database
    if request.graph_space is not None:
        payload["graph_space"] = request.graph_space
    if request.since is not None:
        payload["since"] = request.since
    try:
        execution = await service.execute_definition(
            definition, payload, request.workflow_id, persist_task=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(data=execution, msg="工作流执行请求已受理")


@router.get("/executions", response_model=ApiResponse)
async def list_executions(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ApiResponse:
    return ApiResponse(data=service.list_executions(limit=limit))


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution(execution_id: str) -> ApiResponse:
    execution = await service.get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="工作流执行记录不存在")
    return ApiResponse(data=execution)


@router.get("/schedules", response_model=ApiResponse)
async def list_schedules() -> ApiResponse:
    items = service.repo.list_schedules()
    return ApiResponse(data={"items": items, "total": len(items)})


@router.post("/definitions/{definition_id}/schedules", response_model=ApiResponse)
async def create_schedule(definition_id: str, request: WorkflowScheduleRequest) -> ApiResponse:
    definition = service.repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="工作流定义不存在")
    schedule = {**request.model_dump(), "definitionId": definition_id}
    try:
        schedule = await temporal_runtime.create_schedule(definition, schedule)
    except Exception as exc:
        temporal_runtime._client = None
        schedule["dispatchStatus"] = "LOCAL_SAVED"
        schedule["message"] = str(exc)
    service.repo.save_schedule(schedule)
    return ApiResponse(data=schedule, msg="Schedule 已保存")


@router.put("/schedules/{schedule_id}/state", response_model=ApiResponse)
async def update_schedule_state(schedule_id: str, request: ScheduleStateRequest) -> ApiResponse:
    schedule = service.repo.get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule 不存在")
    try:
        await temporal_runtime.pause_schedule(schedule_id, paused=not request.active)
        schedule["dispatchStatus"] = "TEMPORAL_UPDATED"
    except Exception as exc:
        temporal_runtime._client = None
        schedule["dispatchStatus"] = "LOCAL_SAVED"
        schedule["message"] = str(exc)
    schedule["active"] = request.active
    service.repo.save_schedule(schedule)
    return ApiResponse(data=schedule)


@router.post("/schedules/{schedule_id}/trigger", response_model=ApiResponse)
async def trigger_schedule(schedule_id: str) -> ApiResponse:
    if service.repo.get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="Schedule 不存在")
    try:
        await temporal_runtime.trigger_schedule(schedule_id)
        return ApiResponse(
            data={"id": schedule_id, "dispatchStatus": "TRIGGERED"}, msg="Schedule 已立即触发"
        )
    except Exception as exc:
        temporal_runtime._client = None
        return ApiResponse(code=503, success=False, data={"id": schedule_id}, msg=str(exc))


@router.delete("/schedules/{schedule_id}", response_model=ApiResponse)
async def delete_schedule(schedule_id: str) -> ApiResponse:
    if service.repo.get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="Schedule 不存在")
    try:
        await temporal_runtime.delete_schedule(schedule_id)
    except Exception:
        temporal_runtime._client = None
    service.repo.delete_schedule(schedule_id)
    return ApiResponse(data={"id": schedule_id}, msg="Schedule 已删除")
