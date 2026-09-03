"""全局管理员成员管理 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from biz.dependencies.auth import AuthApplicationDependency, CurrentAdmin
from biz.schemas.common import ApiResponse
from biz.schemas.correction import AdminRoleUpdateRequest
from infra.mysql import get_session
from service.platform_access import list_members, set_admin_role

router = APIRouter(prefix="/admin/members", tags=["admin-members"])


@router.get("")
def get_members(
    admin: CurrentAdmin,
    application: AuthApplicationDependency,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    effective_admin_ids = (*application.settings.initial_admin_user_ids, admin.user_id)
    items = list_members(session, initial_admin_ids=effective_admin_ids)
    return ApiResponse(data={"items": items, "total": len(items)})


@router.put("/{user_id}/admin", responses={404: {"description": "请求的资源不存在"}, 409: {"description": "资源状态冲突"}})
def update_admin_role(
    user_id: str,
    request: AdminRoleUpdateRequest,
    admin: CurrentAdmin,
    application: AuthApplicationDependency,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        result = set_admin_role(
            session,
            user_id=user_id,
            enabled=request.is_admin,
            actor=admin,
            immutable_admin_ids=application.settings.initial_admin_user_ids,
        )
        return ApiResponse(data=result, msg="成员权限已更新")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="用户不存在或尚未登录过本系统") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
