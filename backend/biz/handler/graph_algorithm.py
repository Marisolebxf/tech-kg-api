"""图算法作业 API：所有登录用户可在有权空间提交/轮询算法作业，结果仅 csv 展示。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from biz.dependencies.auth import CurrentActor
from biz.schemas.common import ApiResponse
from biz.schemas.graph_algorithm import AlgorithmSubmitRequest
from service.graph_algorithm import (
    GraphAlgorithmError,
    engine_status,
    get_job,
    get_result,
    metadata,
    submit_job,
)

router = APIRouter(prefix="/graph-algorithms", tags=["graph-algorithms"])


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
def create_job(payload: AlgorithmSubmitRequest, actor: CurrentActor) -> ApiResponse:
    """提交算法作业，返回 running 快照；前端轮询 GET /jobs/{jobId}。"""
    try:
        data = submit_job(
            actor,
            payload.space,
            payload.algorithm,
            payload.labels,
            payload.params,
            has_weight=payload.has_weight,
            weight_cols=payload.weight_cols,
            encode_id=payload.encode_id,
            partition_num=payload.partition_num,
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
