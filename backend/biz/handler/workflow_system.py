"""工作流定义、脚本上传、执行和 Schedule API。"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import TypeAdapter, ValidationError

from application.workflow_jobs import workflow_job_application
from application.workflow_operations import workflow_operations_application
from biz.dependencies.auth import CurrentActor
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.workflow_operations import (
    JobCreateRequest,
    JobUpdateRequest,
    ScheduleStateRequest,
    StepManifest,
    WorkflowChainRequest,
    WorkflowDefinitionRequest,
    WorkflowExecuteRequest,
    WorkflowScheduleRequest,
)
from service.platform_access import PlatformActor
from service.temporal_runtime import temporal_runtime
from service.workflow_jobs import WorkflowJobError

SCHEDULE_NOT_FOUND = "Schedule 不存在"
WORKFLOW_DEFINITION_NOT_FOUND = "工作流定义不存在"

router = APIRouter(prefix="/workflow-system", tags=["workflow-system"])
service = workflow_operations_application.service
job_service = workflow_job_application.service
logger = logging.getLogger(__name__)


@router.get("/health")
async def workflow_health() -> ApiResponse:
    return ApiResponse(data=await temporal_runtime.health())


@router.get("/definitions")
async def list_definitions(
    request: Request,
    category: str | None = Query(default=None, pattern="^(entity|relation|graph|custom)$"),
) -> Response:
    cached = get_cache.try_get("workflow:definitions", request)
    if cached is not None:
        return cached
    items = service.repo.list_definitions(category=category)
    return get_cache.store(
        "workflow:definitions",
        request,
        ApiResponse(data={"items": items, "total": len(items)}).model_dump(),
    )


@router.post("/definitions")
async def create_definition(request: WorkflowDefinitionRequest) -> ApiResponse:
    result = ApiResponse(
        data=service.create_definition(request.model_dump()), msg="自定义工作流定义已保存"
    )
    get_cache.invalidate("workflow:definitions")
    return result


@router.post("/definitions/python", responses={400: {"description": "请求参数无效"}})
async def upload_python_definition(
    file: Annotated[UploadFile, File()],
    function_name: Annotated[str, Form()] = "workflow",
    definition_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
    timeout_seconds: Annotated[int | None, Form(alias="timeoutSeconds")] = None,
    category: Annotated[str, Form(pattern="^(entity|relation|graph|custom)$")] = "custom",
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
            category=category,
        )
        get_cache.invalidate("workflow:definitions")
        return ApiResponse(data=definition, msg="Python 工作流脚本已上传并完成校验")
    except (SyntaxError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/definitions/chains", response_model=ApiResponse)
async def create_chain_definition(request: WorkflowChainRequest) -> ApiResponse:
    """把多个已注册 python 定义按顺序串成 kg.custom.chain 串行链。"""
    try:
        definition = service.create_chain_definition(
            request.name, request.definition_ids, request.definition_id
        )
        return ApiResponse(data=definition, msg="脚本串行链已创建")
    except ValueError as exc:
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


@router.get(
    "/definitions/{definition_id}",
    response_model=ApiResponse,
    responses={404: {"description": "请求的资源不存在"}},
)
async def get_definition(definition_id: str) -> ApiResponse:
    definition = service.repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail=WORKFLOW_DEFINITION_NOT_FOUND)
    return ApiResponse(data=definition)


def _validate_resource_selectors(actor: PlatformActor, selectors: dict) -> None:
    """非管理员触发时校验：所选配置的 owner 必须是自己，图空间必须已绑定。

    selectors 为 snake_case 键的字典（llm_config_id / embedding_config_id /
    mysql_datasource_id / milvus_config_id / graph_space 等）。
    """
    if actor.is_admin:
        return
    from dao.embedding_config import EmbeddingConfigDAO
    from dao.llm_config import LlmConfigDAO
    from dao.milvus_config import MilvusConfigDAO
    from dao.mysql_datasource import MysqlDatasourceDAO
    from infra.mysql import create_session
    from service.graph_space import GraphSpaceService

    session = create_session()
    try:
        checks = (
            (LlmConfigDAO(session), selectors.get("llm_config_id")),
            (EmbeddingConfigDAO(session), selectors.get("embedding_config_id")),
            (MysqlDatasourceDAO(session), selectors.get("mysql_datasource_id")),
            (MilvusConfigDAO(session), selectors.get("milvus_config_id")),
        )
        for dao, config_id in checks:
            if not config_id:
                continue
            row = dao.get(config_id)
            if row is None or (getattr(row, "owner", "") or "") != actor.user_id:
                raise HTTPException(
                    status_code=403, detail=f"无权使用配置 {config_id}（仅能选择自己的配置）"
                )
        graph_space = selectors.get("graph_space")
        if graph_space:
            if not GraphSpaceService(session).is_bound(actor.user_id, graph_space):
                raise HTTPException(
                    status_code=403, detail=f"图空间 {graph_space} 未绑定到当前用户"
                )
    finally:
        session.close()


_SELECTOR_KEYS = (
    "llm_config_id",
    "embedding_config_id",
    "mysql_datasource_id",
    "mysql_database",
    "milvus_config_id",
    "milvus_database",
    "graph_space",
    "since",
)


def _merge_selectors_into_payload(payload: dict, source: WorkflowExecuteRequest) -> dict:
    """把 execute/schedule/job 请求上的资源选择器合并进 workflow payload。"""
    for key in _SELECTOR_KEYS:
        value = getattr(source, key, None)
        if value is not None:
            payload[key] = value
    return payload


@router.post(
    "/definitions/{definition_id}/execute",
    response_model=ApiResponse,
    responses={404: {"description": "请求的资源不存在"}, 409: {"description": "资源状态冲突"}},
)
async def execute_definition(
    definition_id: str, request: WorkflowExecuteRequest, actor: CurrentActor
) -> ApiResponse:
    _validate_resource_selectors(actor, request.model_dump())
    definition = service.repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail=WORKFLOW_DEFINITION_NOT_FOUND)
    payload = _merge_selectors_into_payload(dict(request.payload), request)
    try:
        execution = await service.execute_definition(
            definition, payload, request.workflow_id, persist_task=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiResponse(data=execution, msg="工作流执行请求已受理")


@router.get("/executions")
async def list_executions(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    definition_id: Annotated[str | None, Query(alias="definitionId")] = None,
    schedule_id: Annotated[str | None, Query(alias="scheduleId")] = None,
    trigger_source: Annotated[str | None, Query(alias="triggerSource")] = None,
) -> ApiResponse:
    if trigger_source is not None and trigger_source not in ("MANUAL", "SCHEDULE", "RERUN"):
        raise HTTPException(status_code=422, detail="triggerSource 仅支持 MANUAL/SCHEDULE/RERUN")
    return ApiResponse(
        data=service.list_executions(
            limit=limit,
            definition_id=definition_id,
            schedule_id=schedule_id,
            trigger_source=trigger_source,
        )
    )


@router.get("/executions/{execution_id}", responses={404: {"description": "请求的资源不存在"}})
async def get_execution(execution_id: str) -> ApiResponse:
    execution = await service.get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="工作流执行记录不存在")
    return ApiResponse(data=execution)


@router.get("/schedules")
async def list_schedules() -> ApiResponse:
    items = service.repo.list_schedules()
    return ApiResponse(data={"items": items, "total": len(items)})


@router.post(
    "/definitions/{definition_id}/schedules",
    response_model=ApiResponse,
    responses={404: {"description": "请求的资源不存在"}},
)
async def create_schedule(
    definition_id: str, request: WorkflowScheduleRequest, actor: CurrentActor
) -> ApiResponse:
    _validate_resource_selectors(actor, request.model_dump())
    definition = service.repo.get_definition(definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail=WORKFLOW_DEFINITION_NOT_FOUND)
    schedule = {**request.model_dump(), "definitionId": definition_id}
    payload = _merge_selectors_into_payload(dict(request.payload), request)
    schedule["payload"] = payload
    try:
        schedule = await temporal_runtime.create_schedule(definition, schedule)
    except Exception:
        logger.exception("创建 Temporal Schedule 失败，已仅保存本地记录")
        temporal_runtime._client = None
        schedule["dispatchStatus"] = "LOCAL_SAVED"
        schedule["message"] = "Temporal 服务暂时不可用，计划仅保存到本地"
    service.repo.save_schedule(schedule)
    return ApiResponse(data=schedule, msg="Schedule 已保存")


@router.put("/schedules/{schedule_id}/state", responses={404: {"description": "请求的资源不存在"}})
async def update_schedule_state(schedule_id: str, request: ScheduleStateRequest) -> ApiResponse:
    schedule = service.repo.get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND)
    try:
        await temporal_runtime.pause_schedule(schedule_id, paused=not request.active)
        schedule["dispatchStatus"] = "TEMPORAL_UPDATED"
    except Exception:
        logger.exception("更新 Temporal Schedule 状态失败，已仅更新本地记录")
        temporal_runtime._client = None
        schedule["dispatchStatus"] = "LOCAL_SAVED"
        schedule["message"] = "Temporal 服务暂时不可用，状态仅保存到本地"
    schedule["active"] = request.active
    service.repo.save_schedule(schedule)
    return ApiResponse(data=schedule)


@router.post(
    "/schedules/{schedule_id}/trigger", responses={404: {"description": "请求的资源不存在"}}
)
async def trigger_schedule(schedule_id: str) -> ApiResponse:
    if service.repo.get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND)
    try:
        await temporal_runtime.trigger_schedule(schedule_id)
        return ApiResponse(
            data={"id": schedule_id, "dispatchStatus": "TRIGGERED"}, msg="Schedule 已立即触发"
        )
    except Exception:
        logger.exception("立即触发 Temporal Schedule 失败")
        temporal_runtime._client = None
        return ApiResponse(
            code=503,
            success=False,
            data={"id": schedule_id},
            msg="Temporal 服务暂时不可用",
        )


@router.delete("/schedules/{schedule_id}", responses={404: {"description": "请求的资源不存在"}})
async def delete_schedule(schedule_id: str) -> ApiResponse:
    if service.repo.get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND)
    try:
        await temporal_runtime.delete_schedule(schedule_id)
    except Exception:
        temporal_runtime._client = None
    service.repo.delete_schedule(schedule_id)
    return ApiResponse(data={"id": schedule_id}, msg="Schedule 已删除")


# ---------- 任务中心 Job API ----------


def _job_error(exc: WorkflowJobError) -> HTTPException:
    from service.workflow_jobs import WorkflowJobConflictError, WorkflowJobPermissionError

    if isinstance(exc, WorkflowJobPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, WorkflowJobConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/jobs", response_model=ApiResponse)
async def list_jobs(
    actor: CurrentActor,
    name: Annotated[str | None, Query(max_length=128)] = None,
    status: str | None = Query(None, pattern="^(启用|暂停)$"),
    task_type: Annotated[str | None, Query(alias="taskType")] = None,
) -> ApiResponse:
    items = await job_service.list_jobs(actor, name=name, status=status, task_type=task_type)
    return ApiResponse(data={"items": items, "total": len(items)})


@router.post("/jobs", response_model=ApiResponse)
async def create_job(request: JobCreateRequest, actor: CurrentActor) -> ApiResponse:
    _validate_resource_selectors(actor, request.model_dump())
    try:
        job = await job_service.create_job(actor, request.model_dump(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=job, msg="任务已创建")


@router.get("/jobs/{job_id}", response_model=ApiResponse)
async def get_job(job_id: str, actor: CurrentActor) -> ApiResponse:
    try:
        detail = await job_service.get_job_detail(actor, job_id)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=detail)


@router.post("/jobs/{job_id}/trigger", response_model=ApiResponse)
async def trigger_job(job_id: str, actor: CurrentActor) -> ApiResponse:
    try:
        execution = await job_service.trigger_job(actor, job_id)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=execution, msg="任务已触发")


@router.put("/jobs/{job_id}/state", response_model=ApiResponse)
async def update_job_state(
    job_id: str, request: ScheduleStateRequest, actor: CurrentActor
) -> ApiResponse:
    try:
        job = await job_service.set_job_state(actor, job_id, request.active)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=job)


@router.put("/jobs/{job_id}", response_model=ApiResponse)
async def update_job(job_id: str, request: JobUpdateRequest, actor: CurrentActor) -> ApiResponse:
    _validate_resource_selectors(actor, request.model_dump())
    try:
        job = await job_service.update_job(actor, job_id, request.model_dump(by_alias=True))
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=job, msg="任务已更新")


@router.delete("/jobs/{job_id}", response_model=ApiResponse)
async def delete_job(job_id: str, actor: CurrentActor) -> ApiResponse:
    try:
        ok = await job_service.delete_job(actor, job_id)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data={"id": job_id}, msg="任务已删除")
