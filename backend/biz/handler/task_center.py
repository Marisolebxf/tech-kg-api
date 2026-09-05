"""任务中心、数据源增量和自动建图策略 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from application.workflow_operations import workflow_operations_application
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.workflow_operations import TriggerGraphBuildRequest, UpdatePolicyRequest

router = APIRouter(prefix="/task-center", tags=["task-center"])
service = workflow_operations_application.service


@router.get("/overview")
async def get_overview() -> ApiResponse:
    return ApiResponse(data=service.task_overview())


@router.get("/batches")
async def list_batches() -> ApiResponse:
    items = service.repo.list_batches()
    return ApiResponse(data={"items": items, "total": len(items)})


@router.get("/tasks")
async def list_tasks(
    request: Request,
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
    cached = get_cache.try_get("task-center:tasks", request)
    if cached is not None:
        return cached
    return get_cache.store(
        "task-center:tasks",
        request,
        ApiResponse(
            data=service.list_tasks(
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
        ).model_dump(),
    )


@router.get("/tasks/{task_id}", responses={404: {"description": "请求的资源不存在"}})
async def get_task(task_id: str) -> ApiResponse:
    try:
        return ApiResponse(data=service.get_task(task_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc


@router.get("/data-sources/health")
async def source_health() -> ApiResponse:
    health = service.repo.source_health()
    temporal = await service.temporal_health() if hasattr(service, "temporal_health") else None
    if temporal:
        health = [item for item in health if item["id"] != "temporal"] + [
            {"id": "temporal", "name": "Temporal", "type": "Workflow", "domain": "调度", **temporal}
        ]
    return ApiResponse(data={"items": health, "total": len(health)})


@router.get("/data-sources/updates")
async def source_updates(
    domain: str | None = None,
    since: str | None = None,
    until: str | None = None,
    page: int = 1,
    page_size: int = Query(default=50, alias="pageSize"),
) -> ApiResponse:
    items = service.repo.list_source_updates(domain, since, until)
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
async def get_update_policy() -> ApiResponse:
    return ApiResponse(data=service.repo.get_setting("update_policy"))


@router.put("/update-policy")
async def save_update_policy(request: UpdatePolicyRequest) -> ApiResponse:
    result = await service.save_update_policy(request.model_dump())
    return ApiResponse(data=result, msg="自动建图更新策略已保存")


@router.post("/trigger")
async def trigger_graph_build(request: TriggerGraphBuildRequest) -> ApiResponse:
    result = await service.trigger_graph_build(request.model_dump())
    get_cache.invalidate("task-center:tasks")
    return ApiResponse(data=result, msg="图谱构建任务已创建")
