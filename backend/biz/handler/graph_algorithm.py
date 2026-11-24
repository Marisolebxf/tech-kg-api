"""图算法作业 API：有写权限的用户提交作业，提交人/管理员轮询与终止，结果仅 csv 展示。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from biz.dependencies.auth import CurrentActor
from biz.dependencies.selected_graph_space import bind_selected_graph_space
from biz.schemas.common import ApiResponse
from biz.schemas.graph_algorithm import AlgorithmSubmitRequest
from infra.rate_limit import RateLimit, enforce_rate_limit
from service.graph_algorithm import (
    GraphAlgorithmError,
    cancel_job,
    engine_status,
    get_job,
    get_result,
    metadata,
    submit_job,
)

router = APIRouter(
    prefix="/graph-algorithms",
    tags=["graph-algorithms"],
    dependencies=[Depends(bind_selected_graph_space)],
)


@router.get("/metadata", response_model=ApiResponse)
def read_metadata(
    actor: CurrentActor, space: str = Query(min_length=1, max_length=64)
) -> ApiResponse:
    """边类型列表 + 算法引擎状态（进入图算法面板时加载一次）。"""
    try:
        data = metadata(actor, space)
    except GraphAlgorithmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/engine", response_model=ApiResponse)
def read_engine(
    actor: CurrentActor, space: str = Query(min_length=1, max_length=64)
) -> ApiResponse:
    """算法引擎（Spark 运行器）健康状态。"""
    try:
        data = engine_status(actor, space)
    except GraphAlgorithmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.post("/jobs", response_model=ApiResponse)
async def create_job(
    payload: AlgorithmSubmitRequest, actor: CurrentActor, background_tasks: BackgroundTasks
) -> ApiResponse:
    """提交算法作业，返回 running 快照；前端轮询 GET /jobs/{jobId}。"""
    # 每用户提交配额：Spark/图库算力为全平台共享（渗透 B3）
    await enforce_rate_limit("graph-algorithm-submit", actor.user_id, RateLimit(30, 3600))
    try:
        data = await run_in_threadpool(
            submit_job,
            actor,
            payload.space,
            payload.algorithm,
            payload.labels,
            payload.params,
            has_weight=payload.has_weight,
            weight_cols=payload.weight_cols,
            encode_id=payload.encode_id,
            partition_num=payload.partition_num,
            background_tasks=background_tasks,
        )
    except GraphAlgorithmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/jobs/{job_id}", response_model=ApiResponse)
def read_job(
    actor: CurrentActor,
    job_id: str,
    space: str = Query(min_length=1, max_length=64),
) -> ApiResponse:
    """查询算法作业状态快照。"""
    try:
        data = get_job(actor, space, job_id)
    except GraphAlgorithmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/jobs/{job_id}/result", response_model=ApiResponse)
def read_job_result(
    actor: CurrentActor,
    job_id: str,
    space: str = Query(min_length=1, max_length=64),
) -> ApiResponse:
    """获取已成功作业的 csv 结果。"""
    try:
        data = get_result(actor, space, job_id)
    except GraphAlgorithmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.post("/jobs/{job_id}/cancel", response_model=ApiResponse)
def stop_job(
    actor: CurrentActor,
    job_id: str,
    space: str = Query(min_length=1, max_length=64),
) -> ApiResponse:
    """终止指定空间内的单个算法作业。"""
    try:
        data = cancel_job(actor, space, job_id)
    except GraphAlgorithmError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ApiResponse(data=data)
