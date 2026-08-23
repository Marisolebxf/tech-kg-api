"""普通用户提交修正、管理员审核与同步 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from biz.dependencies.auth import CurrentActor, CurrentAdmin
from biz.schemas.common import ApiResponse
from biz.schemas.correction import (
    CorrectionCreateRequest,
    CorrectionRetryRequest,
    CorrectionReviewRequest,
    CorrectionUpdateRequest,
)
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


@router.get("", response_model=ApiResponse)
def list_corrections(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
    status: str | None = None,
    statuses: str | None = None,
    target_type: str | None = Query(default=None, alias="targetType"),
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> ApiResponse:
    return ApiResponse(
        data=_service(session).list(
            actor,
            all_users=scope == "all",
            status=status,
            statuses=tuple(item.strip() for item in (statuses or "").split(",") if item.strip()),
            target_type=target_type,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse, status_code=201)
def create_correction(
    request: CorrectionCreateRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(
        data=_service(session).create(request.model_dump(), actor),
        msg="人工修正申请已提交",
    )


@router.get("/{correction_id}", response_model=ApiResponse)
def get_correction(
    correction_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        return ApiResponse(data=_service(session).get(correction_id, actor))
    except (KeyError, PermissionError, ValueError) as exc:
        _raise_error(exc)


@router.patch("/{correction_id}", response_model=ApiResponse)
def update_correction(
    correction_id: str,
    request: CorrectionUpdateRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        return ApiResponse(
            data=_service(session).update(
                correction_id,
                request.model_dump(exclude_unset=True),
                actor,
            ),
            msg="人工修正记录已更新",
        )
    except (KeyError, PermissionError, ValueError) as exc:
        _raise_error(exc)


@router.delete("/{correction_id}", response_model=ApiResponse)
def cancel_correction(
    correction_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        return ApiResponse(
            data=_service(session).cancel(correction_id, actor),
            msg="人工修正申请已撤销",
        )
    except (KeyError, PermissionError, ValueError) as exc:
        _raise_error(exc)


@router.post("/{correction_id}/review", response_model=ApiResponse)
def review_correction(
    correction_id: str,
    request: CorrectionReviewRequest,
    admin: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        return ApiResponse(
            data=_service(session).decide(
                correction_id,
                request.decision,
                request.note,
                admin,
            ),
            msg="审核结果已保存",
        )
    except (KeyError, ValueError) as exc:
        _raise_error(exc)


@router.post("/{correction_id}/retry", response_model=ApiResponse)
def retry_correction(
    correction_id: str,
    request: CorrectionRetryRequest,
    admin: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        return ApiResponse(
            data=_service(session).retry(correction_id, request.note, admin),
            msg="已加入同步重试队列",
        )
    except (KeyError, ValueError) as exc:
        _raise_error(exc)
