"""工作流定义、执行和 Schedule API。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from application.workflow_jobs import workflow_job_application
from application.workflow_operations import workflow_operations_application
from biz.dependencies.auth import CurrentActor
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.workflow_operations import (
    JobCreateRequest,
    JobUpdateRequest,
    ScheduleStateRequest,
    WorkflowDefinitionRequest,
    WorkflowExecuteRequest,
    WorkflowScheduleRequest,
)
from service.job_events import hub as job_event_hub
from service.platform_access import PlatformActor
from service.temporal_runtime import temporal_runtime
from service.workflow_jobs import WorkflowJobError

SCHEDULE_NOT_FOUND = "Schedule 不存在"
WORKFLOW_DEFINITION_NOT_FOUND = "工作流定义不存在"

router = APIRouter(prefix="/workflow-system", tags=["workflow-system"])
# 平台总览「图谱构建」卡片对普通用户只读开放：仅任务列表（按 owner 收敛），
# 其余工作流接口仍走管理端路由组。挂载见 biz/router/register.py 的 protected 组。
readonly_router = APIRouter(prefix="/workflow-system", tags=["workflow-system-readonly"])
# 任务列表/详情/执行历史是读多写少的重查询（列表还会惰性向 Temporal 复核），
# 做短 TTL 响应缓存扛读并发；任务创建/触发/删除/启停时整体失效。
# TTL 环境变量 WORKFLOW_JOBS_CACHE_SECONDS 可调，0=关闭（测试用）。
_JOBS_PAYLOAD_CACHE_SECONDS = float(os.getenv("WORKFLOW_JOBS_CACHE_SECONDS", "15"))
_jobs_payload_cache: dict[str, tuple[float, str]] = {}


def _jobs_cache_get(key: str) -> str | None:
    entry = _jobs_payload_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _jobs_cache_put(key: str, payload: str) -> None:
    if len(_jobs_payload_cache) > 1024:
        now = time.monotonic()
        for stale in [k for k, v in _jobs_payload_cache.items() if v[0] <= now]:
            _jobs_payload_cache.pop(stale, None)
    _jobs_payload_cache[key] = (time.monotonic() + _JOBS_PAYLOAD_CACHE_SECONDS, payload)


def _jobs_cache_clear() -> None:
    _jobs_payload_cache.clear()

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
) -> Response:
    if trigger_source is not None and trigger_source not in ("MANUAL", "SCHEDULE", "RERUN"):
        raise HTTPException(status_code=422, detail="triggerSource 仅支持 MANUAL/SCHEDULE/RERUN")
    cache_key = f"executions:{limit}:{definition_id}:{schedule_id}:{trigger_source}"
    cached = _jobs_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    data = service.list_executions(
        limit=limit,
        definition_id=definition_id,
        schedule_id=schedule_id,
        trigger_source=trigger_source,
    )
    payload = json.dumps({"code": 200, "success": True, "data": data, "msg": "success"}, ensure_ascii=False, default=str)
    _jobs_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


@router.get("/executions/{execution_id}", responses={404: {"description": "请求的资源不存在"}})
async def get_execution(execution_id: str) -> Response:
    cache_key = f"execution:{execution_id}"
    cached = _jobs_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    execution = await service.get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="工作流执行记录不存在")
    payload = json.dumps({"code": 200, "success": True, "data": execution, "msg": "success"}, ensure_ascii=False, default=str)
    _jobs_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


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


@router.get("/jobs")
async def list_jobs(
    actor: CurrentActor,
    name: Annotated[str | None, Query(max_length=128)] = None,
    status: str | None = Query(None, pattern="^(启用|暂停)$"),
    task_type: Annotated[str | None, Query(alias="taskType")] = None,
) -> Response:
    cache_key = f"jobs:{actor.user_id}:{actor.is_admin}:{name}:{status}:{task_type}"
    cached = _jobs_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    items = await job_service.list_jobs(actor, name=name, status=status, task_type=task_type)
    payload = json.dumps(
        {"code": 200, "success": True, "data": {"items": items, "total": len(items)}, "msg": "success"},
        ensure_ascii=False,
        default=str,
    )
    _jobs_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


readonly_router.get("/jobs", response_model=ApiResponse)(list_jobs)


# SSE 心跳周期须小于 nginx proxy_read_timeout（默认 60s），防代理掐空闲连接
_SSE_HEARTBEAT_SECONDS = 15.0


@router.get("/jobs/events")
async def stream_job_events() -> StreamingResponse:
    """任务/执行变更推送（SSE）：控制面表变化即下发 jobs-changed 事件。

    鉴权沿用路由组依赖（cookie 会话同源自动携带，EventSource 无法自定义头）。
    客户端断开由生成器取消触发 finally 退订；无订阅者时后端监视协程停转。
    """
    queue = job_event_hub.subscribe()

    async def event_stream():
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"event: jobs-changed\ndata: {data}\n\n"
        finally:
            job_event_hub.unsubscribe(queue)

    # X-Accel-Buffering: no —— nginx 默认缓冲代理响应，会攒住 SSE 流
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs", response_model=ApiResponse)
async def create_job(request: JobCreateRequest, actor: CurrentActor) -> ApiResponse:
    _jobs_cache_clear()
    _validate_resource_selectors(actor, request.model_dump())
    try:
        job = await job_service.create_job(actor, request.model_dump(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=job, msg="任务已创建")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, actor: CurrentActor) -> Response:
    cache_key = f"job:{actor.user_id}:{actor.is_admin}:{job_id}"
    cached = _jobs_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    try:
        detail = await job_service.get_job_detail(actor, job_id)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    payload = json.dumps({"code": 200, "success": True, "data": detail, "msg": "success"}, ensure_ascii=False, default=str)
    _jobs_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


@router.post("/jobs/{job_id}/trigger", response_model=ApiResponse)
async def trigger_job(job_id: str, actor: CurrentActor) -> ApiResponse:
    _jobs_cache_clear()
    try:
        execution = await job_service.trigger_job(actor, job_id)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    return ApiResponse(data=execution, msg="任务已触发")


@router.put("/jobs/{job_id}/state", response_model=ApiResponse)
async def update_job_state(
    job_id: str, request: ScheduleStateRequest, actor: CurrentActor
) -> ApiResponse:
    _jobs_cache_clear()
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
    _jobs_cache_clear()
    try:
        ok = await job_service.delete_job(actor, job_id)
    except WorkflowJobError as exc:
        raise _job_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ApiResponse(data={"id": job_id}, msg="任务已删除")
