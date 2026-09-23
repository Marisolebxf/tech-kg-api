"""任务中心、数据源增量和自动建图策略 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from application.workflow_operations import workflow_operations_application
from biz.dependencies.auth import CurrentActor
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.workflow_operations import (
    TaskRetryRequest,
    TriggerGraphBuildRequest,
    UpdatePolicyRequest,
)
from service.business_access_control import rbac_enabled
from service.workflow_jobs import authorize_workflow_resource, workflow_resource_visible

router = APIRouter(prefix="/task-center", tags=["task-center"])
service = workflow_operations_application.service


@router.get("/overview")
async def get_overview(actor: CurrentActor) -> ApiResponse:
    return ApiResponse(
        data=service.task_overview(actor=actor) if rbac_enabled() else service.task_overview()
    )


@router.get("/batches")
async def list_batches(actor: CurrentActor) -> ApiResponse:
    items = service.repo.list_batches()
    if rbac_enabled():
        items = [item for item in items if workflow_resource_visible(actor, item)]
    return ApiResponse(data={"items": items, "total": len(items)})


@router.get("/tasks")
async def list_tasks(
    request: Request,
    actor: CurrentActor,
    stage: str | None = None,
    status: str | None = None,
    domain: str | None = None,
    kind: str | None = None,
    batch_id: str | None = Query(default=None, alias="batchId"),
    start_time: str | None = Query(default=None, alias="startTime"),
    end_time: str | None = Query(default=None, alias="endTime"),
    keyword: str | None = None,
    page: int = 1,
    page_size: int = Query(default=50, alias="pageSize"),
) -> Response:
    cached = None if rbac_enabled() else get_cache.try_get("task-center:tasks", request)
    if cached is not None:
        return cached
    result = ApiResponse(
        data=service.list_tasks(
            actor=actor if rbac_enabled() else None,
            stage=stage,
            task_status=status,
            domain=domain,
            kind=kind,
            batch_id=batch_id,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )
    if rbac_enabled():
        return Response(result.model_dump_json(), media_type="application/json")
    return get_cache.store("task-center:tasks", request, result.model_dump())


@router.get("/tasks/{task_id}", responses={404: {"description": "请求的资源不存在"}})
async def get_task(task_id: str, actor: CurrentActor) -> ApiResponse:
    persisted = service.repo.get_task(task_id)
    if persisted is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    authorize_workflow_resource(actor, persisted)
    try:
        task = await service.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    if rbac_enabled() and not actor.is_admin:
        batch = task.get("batch")
        if batch and not workflow_resource_visible(actor, batch):
            task["batch"] = None
    # chain（kg.schema.extract.chain）任务：用 Temporal 实时 get_steps 填 pipeline
    # 字段（详情页抽屉渲染）；查询失败（已结束/淘汰）返回 None 走落库 steps 回退
    step_state = await service.query_step_state(task)
    if step_state is not None:
        task["pipeline"] = step_state
    return ApiResponse(data=task)


@router.post("/tasks/{task_id}/retry", response_model=ApiResponse)
async def retry_task(task_id: str, request: TaskRetryRequest, actor: CurrentActor) -> ApiResponse:
    """失败任务重试：调 Temporal ResetWorkflowExecution，回放到失败 step 之前。"""
    persisted = service.repo.get_task(task_id)
    if persisted is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    authorize_workflow_resource(actor, persisted, "write")
    try:
        result = await service.retry_task(task_id, reason=request.reason)
        get_cache.invalidate("task-center:tasks")
        return ApiResponse(data=result, msg="任务重试已下发，workflow 正在回放")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/data-sources/updates")
async def source_updates(
    actor: CurrentActor,
    domain: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page: int = 1,
    page_size: int = Query(default=50, alias="pageSize"),
) -> ApiResponse:
    items = service.repo.list_source_updates(domain, since, until)
    if rbac_enabled():
        items = [item for item in items if workflow_resource_visible(actor, item)]
    start = (max(page, 1) - 1) * min(max(page_size, 1), 200)
    size = min(max(page_size, 1), 200)
    return ApiResponse(
        data={
            "items": items[start : start + size],
            "total": len(items),
            "page": page,
            "pageSize": size,
        }
    )


@router.get("/update-policy")
async def get_update_policy(actor: CurrentActor) -> ApiResponse:
    _require_global_admin(actor)
    return ApiResponse(data=service.repo.get_setting("update_policy"))


@router.put("/update-policy")
async def save_update_policy(request: UpdatePolicyRequest, actor: CurrentActor) -> ApiResponse:
    _require_global_admin(actor)
    payload = request.model_dump()
    if rbac_enabled():
        payload.update(actorUserId=actor.user_id, clientId=actor.business_id)
    result = await service.save_update_policy(payload, actor=actor)
    return ApiResponse(data=result, msg="自动抽取更新策略已保存")


@router.post("/trigger")
async def trigger_extractions(
    request: TriggerGraphBuildRequest, actor: CurrentActor
) -> ApiResponse:
    """立即触发全量数据抽取（D3 后原 kg.graph.build 总工作流的重指向）。"""
    _require_global_admin(actor)
    payload = request.model_dump()
    if rbac_enabled():
        payload.update(actorUserId=actor.user_id, clientId=actor.business_id)
    result = await service.trigger_extract_all(payload, actor=actor)
    get_cache.invalidate("task-center:tasks")
    return ApiResponse(data=result, msg=f"已触发 {len(result['executions'])} 个数据抽取")


def _require_global_admin(actor):
    if rbac_enabled() and not actor.is_admin:
        raise HTTPException(
            status_code=403, detail="全局更新策略及全量触发仅管理员可操作，请使用本业务构建任务"
        )
