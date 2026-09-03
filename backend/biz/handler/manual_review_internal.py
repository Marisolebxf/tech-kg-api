"""Graph-build to manual-review service contract."""

from fastapi import APIRouter, Depends, Header, HTTPException

from biz.dependencies.review_service_auth import require_graph_service
from biz.schemas.common import ApiResponse
from biz.schemas.manual_review_integration import ExecutionEventRequest, ReviewRequiredRequest
from service.manual_review_domain import ReviewConflictError, ReviewValidationError
from service.manual_review_production import manual_review_service

router = APIRouter(prefix="/internal/manual-reviews", tags=["manual-review-internal"])


def fail(exc):
    if isinstance(exc, KeyError):
        raise HTTPException(404, "人工处理任务不存在")
    if isinstance(exc, ReviewConflictError):
        raise HTTPException(409, str(exc))
    if isinstance(exc, ReviewValidationError):
        raise HTTPException(422, str(exc))
    raise exc


@router.post("/review-required", response_model=ApiResponse, status_code=201, responses={422: {"description": "请求无法处理"}})
async def review_required(
    body: ReviewRequiredRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    service_name: str = Depends(require_graph_service),
):
    if idempotency_key != body.eventId:
        raise HTTPException(422, "Idempotency-Key 必须等于 eventId")
    try:
        return ApiResponse(
            data=manual_review_service.create_review_required(body.model_dump(), service_name)
        )
    except Exception as exc:
        fail(exc)


@router.get("/{review_id}/correction", response_model=ApiResponse)
async def get_correction(review_id: str, _: str = Depends(require_graph_service)):
    try:
        return ApiResponse(data=manual_review_service.correction(review_id))
    except Exception as exc:
        fail(exc)


@router.post("/{review_id}/execution-events", response_model=ApiResponse, responses={422: {"description": "请求无法处理"}})
async def execution_event(
    review_id: str,
    body: ExecutionEventRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    _: str = Depends(require_graph_service),
):
    if idempotency_key != body.eventId:
        raise HTTPException(422, "Idempotency-Key 必须等于 eventId")
    try:
        return ApiResponse(data=manual_review_service.execution_event(review_id, body.model_dump()))
    except Exception as exc:
        fail(exc)
