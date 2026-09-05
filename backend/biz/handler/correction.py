"""普通用户提交修正、管理员审核与同步 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from biz.dependencies.auth import CurrentActor, CurrentAdmin
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.correction import (
    CorrectionCreateRequest,
    CorrectionRetryRequest,
    CorrectionReviewRequest,
    CorrectionUpdateRequest,
)
from biz.schemas.text_rules import IDENTIFIER_QUERY_PATTERN, KEYWORD_QUERY_PATTERN
from infra.mysql import get_session
from service.correction import CorrectionService

router = APIRouter(prefix="/corrections", tags=["corrections"])


def _service(session: Session) -> CorrectionService:
    return CorrectionService(session)


def _raise_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail="人工修正记录不存在") from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail="无权访问该人工修正记录") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.get("")
def list_corrections(
    actor: CurrentActor,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    scope: Annotated[str, Query(pattern="^(mine|all)$")] = "mine",
    status: Annotated[str | None, Query(max_length=64)] = None,
    statuses: Annotated[str | None, Query(max_length=64, pattern=KEYWORD_QUERY_PATTERN)] = None,
    target_type: Annotated[
        str | None,
        Query(alias="targetType", max_length=64, pattern=IDENTIFIER_QUERY_PATTERN),
    ] = None,
    keyword: Annotated[str | None, Query(max_length=64, pattern=KEYWORD_QUERY_PATTERN)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> Response:
    cached = get_cache.try_get("correction:list", request)
    if cached is not None:
        return cached
    return get_cache.store(
        "correction:list",
        request,
        ApiResponse(
            data=_service(session).list(
                actor,
                all_users=scope == "all",
                status=status,
                statuses=tuple(
                    item.strip() for item in (statuses or "").split(",") if item.strip()
                ),
                target_type=target_type,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
        ).model_dump(),
    )


@router.post("", status_code=201)
def create_correction(
    request: CorrectionCreateRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    result = ApiResponse(
        data=_service(session).create(request.model_dump(), actor),
        msg="人工修正申请已提交",
    )
    get_cache.invalidate("correction:list")
    return result


@router.get("/{correction_id}")
def get_correction(
    correction_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        return ApiResponse(data=_service(session).get(correction_id, actor))
    except (KeyError, PermissionError, ValueError) as exc:
        _raise_error(exc)


@router.patch("/{correction_id}")
def update_correction(
    correction_id: str,
    request: CorrectionUpdateRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        result = ApiResponse(
            data=_service(session).update(
                correction_id,
                request.model_dump(exclude_unset=True),
                actor,
            ),
            msg="人工修正记录已更新",
        )
        get_cache.invalidate("correction:list")
        return result
    except (KeyError, PermissionError, ValueError) as exc:
        _raise_error(exc)


@router.delete("/{correction_id}")
def cancel_correction(
    correction_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        result = ApiResponse(
            data=_service(session).cancel(correction_id, actor),
            msg="人工修正申请已撤销",
        )
        get_cache.invalidate("correction:list")
        return result
    except (KeyError, PermissionError, ValueError) as exc:
        _raise_error(exc)


@router.post("/{correction_id}/review")
def review_correction(
    correction_id: str,
    request: CorrectionReviewRequest,
    admin: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        result = ApiResponse(
            data=_service(session).decide(
                correction_id,
                request.decision,
                request.note,
                admin,
            ),
            msg="审核结果已保存",
        )
        get_cache.invalidate("correction:list")
        return result
    except (KeyError, ValueError) as exc:
        _raise_error(exc)


@router.post("/{correction_id}/retry")
def retry_correction(
    correction_id: str,
    request: CorrectionRetryRequest,
    admin: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        result = ApiResponse(
            data=_service(session).retry(correction_id, request.note, admin),
            msg="已加入同步重试队列",
        )
        get_cache.invalidate("correction:list")
        return result
    except (KeyError, ValueError) as exc:
        _raise_error(exc)
