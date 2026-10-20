"""人工审核队列、详情和处置 API。"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from biz.dependencies.review_identity import get_review_identity
from biz.schemas.common import ApiResponse
from biz.schemas.manual_review_production import (
    CancelRequest,
    DeleteCasesRequest,
    DirectDecideRequest,
    DraftRequest,
    EvidenceCompleteRequest,
    EvidenceUploadRequest,
    ExtractFailuresRerunRequest,
    SubmitRequest,
    TransferRequest,
    VersionRequest,
)
from service.business_access_control import rbac_enabled
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
# 翻页提速（对齐实体列表 entity_search 的 100 条块缓存）：页请求对齐到所在
# 100 条块计算并缓存，页只是块内切片，同块的相邻页不再各查一次库；块计算用
# asyncio.Task 共享在飞结果——同一块并发翻页只放一个请求查库，其余等同一结果
# （RBAC 开启时响应缓存禁用，但在飞去重依然成立：首个现算，其余共享）。
REVIEW_QUEUE_BLOCK_SIZE = 100
_queue_block_tasks: dict[str, asyncio.Task] = {}


def _queue_cache_get(key: str) -> str | None:
    # Case ownership may be corrected directly in SQL. A space-scope cache key
    # cannot detect a moved case, even when the caller's scope is unchanged.
    if rbac_enabled():
        return None
    entry = _queue_payload_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _queue_cache_put(key: str, payload: str) -> None:
    if rbac_enabled():
        return
    if len(_queue_payload_cache) > 512:
        now = time.monotonic()
        for stale in [k for k, v in _queue_payload_cache.items() if v[0] <= now]:
            _queue_payload_cache.pop(stale, None)
    _queue_payload_cache[key] = (time.monotonic() + _QUEUE_CACHE_SECONDS, payload)


# 保留总览队列入口契约；真实审核权限仍由 get_review_identity 校验。
readonly_router = APIRouter(prefix="/manual-reviews", tags=["manual-review-readonly"])


def _queue_cache_clear() -> None:
    _queue_payload_cache.clear()


def _cache_scope(identity: ReviewIdentity, case_id: str | None = None) -> str:
    try:
        spaces = identity.review_view_spaces()
        if spaces is not None and case_id is not None:
            # 读路径缓存键按查看档校验（共享空间只读可见）；写端点不走此缓存
            production_service.authorize_case_view(case_id, identity)
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


def _queue_envelope(data: dict) -> str:
    return json.dumps(
        {"code": 200, "success": True, "data": data, "msg": "success"},
        ensure_ascii=False,
        default=str,
    )


def _queue_block_key(scope_key: str, filters: dict, block_offset: int) -> str:
    return "queue-block:" + scope_key + json.dumps(filters, ensure_ascii=False) + f":{block_offset}"


async def _compute_queue_block(
    identity, scope_key: str, filters: dict, block_offset: int
) -> tuple[str, bool]:
    """现算一个 100 条块（list_cases 挪线程池，不再阻塞事件循环）并写响应缓存。

    同键并发请求共享在飞的 asyncio.Task：只有一个请求查库，其余等同一结果。
    返回 (payload, 是否缓存命中)。
    """
    key = _queue_block_key(scope_key, filters, block_offset)
    cached = _queue_cache_get(key)
    if cached is not None:
        return cached, True

    async def run() -> tuple[str, bool]:
        data = await asyncio.to_thread(
            production_service.list_cases,
            {
                **filters,
                "page": block_offset // REVIEW_QUEUE_BLOCK_SIZE + 1,
                "page_size": REVIEW_QUEUE_BLOCK_SIZE,
            },
            identity,
        )
        payload = _queue_envelope(data)
        _queue_cache_put(key, payload)
        return payload, False

    task = _queue_block_tasks.get(key)
    if task is None:
        task = asyncio.ensure_future(run())
        _queue_block_tasks[key] = task

        def _pop(_task: asyncio.Task) -> None:
            _queue_block_tasks.pop(key, None)

        task.add_done_callback(_pop)
    return await task


async def _load_queue_page(
    identity, scope_key: str, filters: dict, *, page: int, page_size: int
) -> tuple[str, bool]:
    """页请求 → 所在 100 条块的切片；跨块页补拉下一块拼接（对齐实体列表分页）。"""
    offset = (page - 1) * page_size
    block_offset = offset // REVIEW_QUEUE_BLOCK_SIZE * REVIEW_QUEUE_BLOCK_SIZE
    payload, hit = await _compute_queue_block(identity, scope_key, filters, block_offset)
    data = json.loads(payload)["data"]
    start = offset - block_offset
    items = data["items"][start : start + page_size]
    if start + page_size > REVIEW_QUEUE_BLOCK_SIZE and offset + len(items) < data["total"]:
        following, following_hit = await _compute_queue_block(
            identity, scope_key, filters, block_offset + REVIEW_QUEUE_BLOCK_SIZE
        )
        items.extend(json.loads(following)["data"]["items"][: page_size - len(items)])
        hit = hit and following_hit
    data.update(items=items, page=page, pageSize=page_size)
    return _queue_envelope(data), hit


@router.get("/production/queue", response_model=ApiResponse)
async def production_queue(
    identity: ReviewIdentityDep,
    queue: str | None = None,
    status: str | None = Query(
        None,
        description="状态精确过滤（与表格徽标 1:1）：OPEN=待处理/RERUNNING=重跑中/RESOLVED=已完成等；"
        "RERUN_FAILED=重跑失败是只读推导态（库内不落值），按重跑执行概要圈定，"
        "RESOLVED/RERUNNING 也会剔除推导为重跑失败的案",
    ),
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
    graph_space: str | None = Query(
        None,
        alias="graphSpace",
        max_length=64,
        description="按图空间过滤；不传=当前账号全部可审核空间",
    ),
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
    selected_space = getattr(identity.platform_actor, "context_graph_space", "")
    if selected_space:
        if graph_space and graph_space != selected_space:
            raise HTTPException(403, "请求空间与当前图空间不一致")
        graph_space = selected_space
    # list_cases 只读这些过滤键（page/page_size 由块加载器按块对齐注入）
    filters = {
        "queue": queue,
        "status": status,
        "status_group": status_group,
        "kind": kind,
        "risk": risk,
        "domain": domain,
        "template_id": template_id,
        "assignee_id": assignee_id,
        "graph_space": graph_space,
        "category": category,
        "keyword": keyword,
        "updated_within": updated_within,
        "sort": sort,
    }
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 50), 1), 200)
    try:
        if page_size <= REVIEW_QUEUE_BLOCK_SIZE:
            payload, hit = await _load_queue_page(
                identity, _cache_scope(identity), filters, page=page, page_size=page_size
            )
        else:
            # 超过块大小的页大小直接现算（前端页大小上限 100，正常不会走到）
            data = await asyncio.to_thread(
                production_service.list_cases,
                {**filters, "page": page, "page_size": page_size},
                identity,
            )
            payload, hit = _queue_envelope(data), False
    except Exception as exc:
        _raise_production_error(exc)
    return Response(
        payload,
        media_type="application/json",
        headers={"X-Review-Queue-Cache": "HIT" if hit else "MISS"},
    )


readonly_router.get("/production/queue", response_model=ApiResponse)(production_queue)


@router.get("/production/{case_id}")
async def production_detail(case_id: str, identity: ReviewIdentityDep) -> Response:
    cache_key = f"case_detail:{case_id}:" + _cache_scope(identity, case_id)
    cached = _queue_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    try:
        # get_case 的 T_LINK 富化含同步图/ES 查询（秒级），挪线程池避免占住事件循环
        payload = json.dumps(
            {
                "code": 200,
                "success": True,
                "data": await asyncio.to_thread(production_service.get_case, case_id, identity),
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
        # T_LINK 裁决含同步图写入，挪线程池避免占住事件循环
        return ApiResponse(
            data=await asyncio.to_thread(
                production_service.submit,
                case_id,
                body.version,
                body.actionId,
                body.result,
                body.note,
                identity,
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/direct-decide", response_model=ApiResponse)
async def direct_decide_case(case_id: str, body: DirectDecideRequest, identity: ReviewIdentityDep):
    """kg.custom.steps T_DIRECT 案例两步决策：accept 直接写图，reject 丢弃。"""
    _queue_cache_clear()
    try:
        # accept 直写图（同步图写入），挪线程池避免占住事件循环
        return ApiResponse(
            data=await asyncio.to_thread(
                production_service.direct_decide,
                case_id,
                body.version,
                body.accepted,
                body.note,
                identity,
                body.candidate,
            )
        )
    except Exception as exc:
        _raise_production_error(exc)


@router.post("/production/{case_id}/refresh-candidates", response_model=ApiResponse)
async def refresh_case_candidates(case_id: str, body: VersionRequest, identity: ReviewIdentityDep):
    """T_LINK 受控刷新未决候选：按案件图空间重跑召回+打分，零写图（MR-CAND B）。

    失效候选剔除也算变更（version+1+审计）；并发刷新/提交由 version CAS 拦截。
    """
    _queue_cache_clear()
    try:
        # 重跑召回是同步图查询（秒级），挪线程池避免占住事件循环
        return ApiResponse(
            data=await asyncio.to_thread(
                production_service.refresh_candidates,
                case_id,
                body.version,
                identity,
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


@router.post("/production/batch-delete", response_model=ApiResponse)
async def batch_delete_cases(body: DeleteCasesRequest, identity: ReviewIdentityDep):
    """批量物理删除未处理 case：逐条复用单删门控（review_admin / 空间校验 / 终态不可删）。

    单条被拒（已处理、不存在、无权限）只跳过该条不阻断整批，结果聚合返回；
    requested 为去重后的请求数。
    """
    _queue_cache_clear()
    case_ids = list(dict.fromkeys(body.caseIds))
    deleted = 0
    skipped: list[dict[str, str]] = []
    for case_id in case_ids:
        try:
            production_service.delete_case(case_id, identity)
            deleted += 1
        except KeyError:
            skipped.append({"id": case_id, "reason": REVIEW_TASK_NOT_FOUND})
        except Exception as exc:
            # 业务拒绝（终态 409 / 权限 403）与意外异常均按条跳过并带回原因，
            # 避免一条坏记录拖垮整批
            skipped.append({"id": case_id, "reason": str(exc) or exc.__class__.__name__})
    return ApiResponse(
        data={"requested": len(case_ids), "deleted": deleted, "skipped": skipped},
        msg=f"已删除 {deleted} 条、跳过 {len(skipped)} 条",
    )


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
