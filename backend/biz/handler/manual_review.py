"""人工审核队列、详情和处置 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from application.workflow_operations import workflow_operations_application
from biz.schemas.common import ApiResponse
from biz.schemas.workflow_operations import (
    RetryRequest,
    ReviewActionRequest,
    ReviewResultRequest,
    RevokeRequest,
)

router = APIRouter(prefix="/manual-reviews", tags=["manual-review"])
service = workflow_operations_application.service


@router.get("", response_model=ApiResponse)
def list_reviews(
    status: str | None = None,
    domain: str | None = None,
    category: str | None = None,
    batch_id: str | None = Query(default=None, alias="batchId"),
    start_time: str | None = Query(default=None, alias="startTime"),
    end_time: str | None = Query(default=None, alias="endTime"),
    keyword: str | None = None,
    page: int = 1,
    page_size: int = Query(default=50, alias="pageSize"),
) -> ApiResponse:
    return ApiResponse(
        data=service.list_reviews(
            status=status,
            domain=domain,
            category=category,
            batch_id=batch_id,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{review_id}", response_model=ApiResponse)
def get_review(review_id: str) -> ApiResponse:
    try:
        return ApiResponse(data=service.get_review(review_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.get("/{review_id}/flow", response_model=ApiResponse)
def get_review_flow(review_id: str) -> ApiResponse:
    try:
        review = service.get_review(review_id)
        return ApiResponse(
            data={"id": review_id, "flow": review.get("flow", []), "task": review.get("task")}
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.post("/{review_id}/actions", response_model=ApiResponse)
async def handle_review(review_id: str, request: ReviewActionRequest) -> ApiResponse:
    try:
        result = await service.handle_review(review_id, request.model_dump())
        return ApiResponse(data=result, msg="人工处理结果已提交")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{review_id}/result", response_model=ApiResponse)
def modify_result(review_id: str, request: ReviewResultRequest) -> ApiResponse:
    try:
        return ApiResponse(
            data=service.modify_review_result(review_id, request.model_dump()), msg="任务结果已修改"
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.post("/{review_id}/retry", response_model=ApiResponse)
async def retry_review(review_id: str, request: RetryRequest) -> ApiResponse:
    try:
        return ApiResponse(
            data=await service.retry_review(review_id, request.payload), msg="重试工作流已下发"
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.post("/{review_id}/revoke", response_model=ApiResponse)
def revoke_review(review_id: str, request: RevokeRequest) -> ApiResponse:
    try:
        return ApiResponse(
            data=service.revoke_review(review_id, request.reason, request.handler),
            msg="人工任务已撤销",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc
