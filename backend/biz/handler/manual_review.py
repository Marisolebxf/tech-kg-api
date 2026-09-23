"""人工审核队列、详情和处置 API。"""

from __future__ import annotations

import json
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from biz.dependencies.review_identity import get_review_identity
from biz.schemas.common import ApiResponse
from biz.schemas.manual_review_production import (
    CancelRequest,
    DirectDecideRequest,
    DraftRequest,
    EvidenceCompleteRequest,
    EvidenceUploadRequest,
    ExtractFailuresRerunRequest,
    SubmitRequest,
    TransferRequest,
    VersionRequest,
)
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
)
from service.manual_review_production import manual_review_service as production_service

REVIEW_TASK_NOT_FOUND = "人工处理任务不存在"

ReviewIdentityDep = Annotated[ReviewIdentity, Depends(get_review_identity)]
router = APIRouter(prefix="/manual-reviews", tags=["manual-review"])
# 队列查询是重查询（500 并发下 DB/身份解析排队，压测用例 05 吞吐瓶颈），
# 做短 TTL 响应缓存。审核动作（认领/提交/重跑等写接口）不经过此缓存、
# 自带行级冲突校验，队列视图最多滞后 TTL——动作正确性不受影响。
# TTL 环境变量 REVIEW_QUEUE_CACHE_SECONDS 可调，0=关闭。
_QUEUE_CACHE_SECONDS = float(os.getenv("REVIEW_QUEUE_CACHE_SECONDS", "15"))
_queue_payload_cache: dict[str, tuple[float, str]] = {}


def _queue_cache_get(key: str) -> str | None:
    entry = _queue_payload_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _queue_cache_put(key: str, payload: str) -> None:
    if len(_queue_payload_cache) > 512:
        now = time.monotonic()
        for stale in [k for k, v in _queue_payload_cache.items() if v[0] <= now]:
            _queue_payload_cache.pop(stale, None)
    _queue_payload_cache[key] = (time.monotonic() + _QUEUE_CACHE_SECONDS, payload)


# 平台总览「人工审核」卡片对普通用户只读开放：仅队列查询；处理/认领等仍走管理端路由组。
readonly_router = APIRouter(prefix="/manual-reviews", tags=["manual-review-readonly"])


def _queue_cache_clear() -> None:
    _queue_payload_cache.clear()


def _cache_scope(identity: ReviewIdentity, case_id: str | None = None) -> str:
    try:
        spaces = identity.review_spaces()
        if spaces is not None and case_id is not None:
            production_service.authorize_case(case_id, identity)
        return json.dumps(
            [identity.user_id, sorted(identity.roles), sorted(identity.domains), spaces],
            ensure_ascii=False,
        )
    except Exception as exc:
        _raise_production_error(exc)


def _raise_production_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(404, REVIEW_TASK_NOT_FOUND)
    if isinstance(exc, ReviewForbiddenError):
        raise HTTPException(403, str(exc))
    if isinstance(exc, ReviewConflictError):
        raise HTTPException(409, str(exc))
    if isinstance(exc, ReviewValidationError):
        raise HTTPException(422, str(exc))
    raise exc


@router.get("/production/queue", response_model=ApiResponse)
async def production_queue(
    identity: ReviewIdentityDep,
    queue: str | None = None,
    status: str | None = None,
    status_group: str | None = Query(
        None,
        alias="statusGroup",
        description="状态分组：pending=待处理（非终态）；processed=已处理（RESOLVED/REJECTED/CANCELLED/EXPIRED）",
    ),
    kind: str | None = Query(
        None,
        description="对象种类：entity=只看实体；relation=只看关系；不传=都看",
    ),
    risk: str | None = None,
    domain: str | None = None,
    template_id: str | None = Query(None, alias="templateId"),
    assignee_id: str | None = Query(None, alias="assigneeId"),
    category: str | None = Query(
        None,
        description="A=入库决策 (T_DIRECT/T_LINK)；C=抽取失败重跑 (T_EXTRACT_FAIL)；不传=所有",
    ),
    keyword: str | None = None,
    updated_within: str | None = Query(
        None,
        alias="updatedWithin",
        description="按更新时间过滤：1h/24h/7d/30d；不传=不限",
    ),
    sort: str | None = Query(
        None,
        description="排序：updated_desc/updated_asc（按更新时间）；不传=默认风险+创建时间",
    ),
    page: int = 1,
    page_size: int = Query(50, alias="pageSize"),
):
    cache_key = (
        "queue:"
        + _cache_scope(identity)
        + json.dumps(
            [
                queue,
                status,
                status_group,
                kind,
                risk,
                domain,
                template_id,
                assignee_id,
                category,
                keyword,
                updated_within,
                sort,
                page,
                page_size,
            ],
            ensure_ascii=False,
        )
    )
    cached = _queue_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    try:
        payload = json.dumps(
            {
                "code": 200,
                "success": True,
                "data": production_service.list_cases(locals(), identity),
                "msg": "success",
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        _raise_production_error(exc)
    _queue_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


readonly_router.get("/production/queue", response_model=ApiResponse)(production_queue)


@router.get("/production/{case_id}")
async def production_detail(case_id: str, identity: ReviewIdentityDep) -> Response:
    cache_key = f"case_detail:{case_id}:" + _cache_scope(identity, case_id)
    cached = _queue_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    try:
        payload = json.dumps(
            {
                "code": 200,
                "success": True,
                "data": production_service.get_case(case_id, identity),
                "msg": "success",
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        _raise_production_error(exc)
    _queue_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


@router.post("/production/{case_id}/claim", response_model=ApiResponse)
async def claim_case(case_id: str, body: VersionRequest, identity: ReviewIdentityDep):
    _queue_cache_clear()
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
    _queue_cache_clear()
    try:
        return ApiResponse(data=production_service.release(case_id, body.version, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/transfer", response_model=ApiResponse)
async def transfer_case(case_id: str, body: TransferRequest, identity: ReviewIdentityDep):
    _queue_cache_clear()
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
    _queue_cache_clear()
    try:
        return ApiResponse(
            data=production_service.submit(
                case_id, body.version, body.actionId, body.result, body.note, identity
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/direct-decide", response_model=ApiResponse)
async def direct_decide_case(case_id: str, body: DirectDecideRequest, identity: ReviewIdentityDep):
    """kg.custom.steps T_DIRECT 案例两步决策：accept 直接写图，reject 丢弃。"""
    _queue_cache_clear()
    try:
        return ApiResponse(
            data=production_service.direct_decide(
                case_id, body.version, body.accepted, body.note, identity, body.candidate
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/rerun-extract-failures", response_model=ApiResponse)
async def rerun_extract_failures(body: ExtractFailuresRerunRequest, identity: ReviewIdentityDep):
    """T_EXTRACT_FAIL 抽取失败记录重跑：所选 case 按 schema 合并为新执行（重新执行）。

    单条 case 与批量勾选共用；不传 caseIds 时按 executionId 重跑该执行全部失败记录。
    """
    from service.manual_review_domain import require_role
    from service.schema_extraction import SchemaConflictError, rerun_failed_records

    require_role(
        identity,
        "reviewer",
        "data_quality_reviewer",
        "graph_governance_reviewer",
        "approver",
        "review_admin",
    )
    _queue_cache_clear()
    try:
        from service.business_access_control import rbac_enabled

        authorized_case_ids = body.caseIds
        if rbac_enabled():
            authorized_case_ids = production_service.authorize_rerun(
                identity, case_ids=body.caseIds, execution_id=body.executionId
            )
        data = await rerun_failed_records(
            case_ids=authorized_case_ids,
            execution_id=body.executionId,
            batch_size=body.batchSize,
            actor=identity.platform_actor,
        )
        return ApiResponse(data=data, msg="重跑已下发")
    except SchemaConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/cancel", response_model=ApiResponse)
async def cancel_case(case_id: str, body: CancelRequest, identity: ReviewIdentityDep):
    _queue_cache_clear()
    try:
        return ApiResponse(
            data=production_service.cancel(case_id, body.version, body.reason, identity)
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.delete("/production/{case_id}", response_model=ApiResponse)
async def delete_case(case_id: str, identity: ReviewIdentityDep):
    """物理删除未处理 case（review_admin；已终态的记录保留作历史不可删）。"""
    _queue_cache_clear()
    try:
        return ApiResponse(data=production_service.delete_case(case_id, identity))
    except Exception as exc:
        _raise_production_error(exc)


@router.get("/production/{case_id}/audit-logs")
async def case_audit_logs(case_id: str, identity: ReviewIdentityDep) -> Response:
    cache_key = f"case_audit_logs:{case_id}:" + _cache_scope(identity, case_id)
    cached = _queue_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    try:
        payload = json.dumps(
            {
                "code": 200,
                "success": True,
                "data": {"items": production_service.logs(case_id, identity)},
                "msg": "success",
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        _raise_production_error(exc)
    _queue_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


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


@router.post("/production/internal/reclaim-expired", response_model=ApiResponse)
async def reclaim_expired_claims(identity: ReviewIdentityDep):
    try:
        from service.manual_review_domain import require_role

        require_role(identity, "review_admin")
        return ApiResponse(data={"reclaimed": production_service.reclaim_expired()})
    except Exception as exc:
        _raise_production_error(exc)
