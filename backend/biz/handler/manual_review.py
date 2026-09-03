"""人工审核队列、详情和处置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from application.workflow_operations import workflow_operations_application
from biz.dependencies.review_identity import get_review_identity
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.manual_review_production import (
    ApprovalRequest,
    CancelRequest,
    CreateCaseRequest,
    DraftRequest,
    EvidenceCompleteRequest,
    EvidenceUploadRequest,
    ExecutionCompleteRequest,
    SubmitRequest,
    TransferRequest,
    VersionRequest,
)
from biz.schemas.workflow_operations import (
    RetryRequest,
    ReviewActionRequest,
    ReviewResultRequest,
    RevokeRequest,
)
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
)
from service.manual_review_production import manual_review_service as production_service

ReviewIdentityDep = Annotated[ReviewIdentity, Depends(get_review_identity)]
router = APIRouter(prefix="/manual-reviews", tags=["manual-review"])

service = workflow_operations_application.service


@router.get("", response_model=ApiResponse)
async def list_reviews(
    request: Request,
    status: str | None = None,
    domain: str | None = None,
    category: str | None = None,
    batch_id: str | None = Query(default=None, alias="batchId"),
    start_time: str | None = Query(default=None, alias="startTime"),
    end_time: str | None = Query(default=None, alias="endTime"),
    keyword: str | None = None,
    page: int = 1,
    page_size: int = Query(default=50, alias="pageSize"),
) -> Response:
    cached = get_cache.try_get("manual-review:list", request)
    if cached is not None:
        return cached
    return get_cache.store(
        "manual-review:list",
        request,
        ApiResponse(
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
        ).model_dump(),
    )


@router.get("/{review_id}", response_model=ApiResponse)
async def get_review(review_id: str) -> ApiResponse:
    try:
        return ApiResponse(data=service.get_review(review_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.get("/{review_id}/flow", response_model=ApiResponse)
async def get_review_flow(review_id: str) -> ApiResponse:
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
        get_cache.invalidate("manual-review:list")
        return ApiResponse(data=result, msg="人工处理结果已提交")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{review_id}/result", response_model=ApiResponse)
async def modify_result(review_id: str, request: ReviewResultRequest) -> ApiResponse:
    try:
        result = service.modify_review_result(review_id, request.model_dump())
        get_cache.invalidate("manual-review:list")
        return ApiResponse(data=result, msg="任务结果已修改")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.post("/{review_id}/retry", response_model=ApiResponse)
async def retry_review(review_id: str, request: RetryRequest) -> ApiResponse:
    try:
        result = await service.retry_review(review_id, request.payload)
        get_cache.invalidate("manual-review:list")
        return ApiResponse(data=result, msg="重试工作流已下发")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


@router.post("/{review_id}/revoke", response_model=ApiResponse)
async def revoke_review(review_id: str, request: RevokeRequest) -> ApiResponse:
    try:
        result = service.revoke_review(review_id, request.reason, request.handler)
        get_cache.invalidate("manual-review:list")
        return ApiResponse(data=result, msg="人工任务已撤销")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="人工处理任务不存在") from exc


def _raise_production_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(404, "人工处理任务不存在")
    if isinstance(exc, ReviewForbiddenError):
        raise HTTPException(403, str(exc))
    if isinstance(exc, ReviewConflictError):
        raise HTTPException(409, str(exc))
    if isinstance(exc, ReviewValidationError):
        raise HTTPException(422, str(exc))
    raise exc


@router.post("/internal/cases", response_model=ApiResponse)
async def create_production_case(body: CreateCaseRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data=production_service.create_case(body.model_dump(), identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.get("/production/queue", response_model=ApiResponse)
async def production_queue(
    identity: ReviewIdentityDep,
    queue: str | None = None,
    status: str | None = None,
    risk: str | None = None,
    domain: str | None = None,
    template_id: str | None = Query(None, alias="templateId"),
    assignee_id: str | None = Query(None, alias="assigneeId"),
    keyword: str | None = None,
    page: int = 1,
    page_size: int = Query(50, alias="pageSize"),
):
    try:
        return ApiResponse(data=production_service.list_cases(locals(), identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.get("/production/{case_id}", response_model=ApiResponse)
async def production_detail(case_id: str, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data=production_service.get_case(case_id, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/claim", response_model=ApiResponse)
async def claim_case(case_id: str, body: VersionRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data=production_service.claim(case_id, body.version, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/heartbeat", response_model=ApiResponse)
async def heartbeat_case(case_id: str, body: VersionRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data=production_service.heartbeat(case_id, body.version, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/release", response_model=ApiResponse)
async def release_case(case_id: str, body: VersionRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data=production_service.release(case_id, body.version, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/transfer", response_model=ApiResponse)
async def transfer_case(case_id: str, body: TransferRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(
            data=production_service.transfer(
                case_id, body.version, body.assigneeId, body.assigneeName, identity
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.put("/production/{case_id}/draft", response_model=ApiResponse)
async def save_case_draft(case_id: str, body: DraftRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(
            data=production_service.draft(case_id, body.version, body.payload, identity)
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/submit", response_model=ApiResponse)
async def submit_case(case_id: str, body: SubmitRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(
            data=production_service.submit(
                case_id, body.version, body.actionId, body.result, body.note, identity
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/approve", response_model=ApiResponse)
async def approve_case(case_id: str, body: ApprovalRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(
            data=production_service.approve(case_id, body.version, True, body.note, identity)
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/reject", response_model=ApiResponse)
async def reject_case(case_id: str, body: ApprovalRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(
            data=production_service.approve(case_id, body.version, False, body.note, identity)
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/cancel", response_model=ApiResponse)
async def cancel_case(case_id: str, body: CancelRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(
            data=production_service.cancel(case_id, body.version, body.reason, identity)
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/retry", response_model=ApiResponse)
async def retry_case(case_id: str, body: VersionRequest, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data=production_service.retry(case_id, body.version, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/executions/{execution_id}/complete", response_model=ApiResponse)
async def complete_case_execution(
    case_id: str,
    execution_id: str,
    body: ExecutionCompleteRequest,
    identity: ReviewIdentityDep,
):
    try:
        return ApiResponse(
            data=production_service.complete_execution(
                case_id, execution_id, body.success, body.error, identity
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.get("/production/{case_id}/executions", response_model=ApiResponse)
async def case_executions(case_id: str, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data={"items": production_service.executions(case_id, identity)})
    except Exception as exc:
        _raise_production_error(exc)


@router.get("/production/{case_id}/audit-logs", response_model=ApiResponse)
async def case_audit_logs(case_id: str, identity: ReviewIdentityDep):
    try:
        return ApiResponse(data={"items": production_service.logs(case_id, identity)})
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/evidence/upload-url", response_model=ApiResponse)
async def evidence_upload_url(
    case_id: str,
    body: EvidenceUploadRequest,
    identity: ReviewIdentityDep,
):
    try:
        return ApiResponse(
            data=production_service.evidence_upload(
                case_id, body.fileName, body.contentType, body.sizeBytes, body.sha256, identity
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/evidence/complete", response_model=ApiResponse)
async def evidence_complete(
    case_id: str,
    body: EvidenceCompleteRequest,
    identity: ReviewIdentityDep,
):
    try:
        return ApiResponse(
            data=production_service.evidence_complete(case_id, body.model_dump(), identity)
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/internal/process-outbox", response_model=ApiResponse)
async def process_review_outbox(identity: ReviewIdentityDep):
    try:
        from service.manual_review_domain import require_role

        require_role(identity, "review_admin")
        return ApiResponse(data=await production_service.process_outbox())
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/internal/reclaim-expired", response_model=ApiResponse)
async def reclaim_expired_claims(identity: ReviewIdentityDep):
    try:
        from service.manual_review_domain import require_role

        require_role(identity, "review_admin")
        return ApiResponse(data={"reclaimed": production_service.reclaim_expired()})
    except Exception as exc:
        _raise_production_error(exc)
