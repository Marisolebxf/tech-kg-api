"""Business management and administrator-approved graph-space provisioning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from biz.dependencies.auth import AuthApplicationDependency, CurrentAdmin, CurrentMaintainer
from biz.schemas.common import ApiResponse
from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessSpaceRequest,
)
from db_model.platform_governance import AdminAuditLog, PlatformUser
from infra.mysql import get_session, session_scope
from service.business_access_control import rbac_enabled
from service.graph_space import GraphSpaceService
from service.platform_access import list_members, set_admin_role

router = APIRouter(prefix="/business-access", tags=["business-access"])
Db = Annotated[Session, Depends(get_session)]
CLIENT_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
SPACE_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"


class BusinessPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = True


class MemberPayload(BaseModel):
    clientId: str | None = Field(default=None, pattern=CLIENT_PATTERN)
    role: Literal["user", "developer", "admin"]


class SpacePayload(BaseModel):
    clientId: str | None = Field(default=None, pattern=CLIENT_PATTERN)
    isSharedProduction: bool = False


class RequestPayload(BaseModel):
    spaceName: str = Field(pattern=SPACE_PATTERN, max_length=64)
    reason: str = Field(default="", max_length=2000)
    clientId: str | None = Field(default=None, pattern=CLIENT_PATTERN)


class DecisionPayload(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=2000)


def require_enabled() -> None:
    if not rbac_enabled():
        raise HTTPException(409, "业务权限尚未启用")


def _business(session: Session, client_id: str | None) -> BusinessClient:
    row = session.get(BusinessClient, client_id) if client_id else None
    if row is None or not row.enabled:
        raise HTTPException(400, "请选择已启用的业务")
    return row


def _audit(session: Session, actor, action: str, resource: str, detail: dict) -> None:
    session.add(
        AdminAuditLog(
            actor_id=actor.user_id,
            actor_name=actor.display_name,
            action=action,
            resource_type="business_access",
            resource_id=resource,
            detail=detail,
        )
    )


def _request_dict(row: BusinessSpaceRequest) -> dict:
    return {
        "id": row.id,
        "clientId": row.client_id,
        "spaceName": row.space_name,
        "reason": row.reason,
        "status": row.status,
        "requestedBy": row.requested_by,
        "reviewedBy": row.reviewed_by,
        "reviewNote": row.review_note,
        "lastError": row.last_error,
        "createdAt": row.created_at.isoformat(),
        "canRetry": row.status == "failed"
        or (
            row.status == "creating"
            and row.updated_at < datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
        ),
    }


@router.get("/state")
def state(actor: CurrentMaintainer, session: Db, application: AuthApplicationDependency):
    require_enabled()
    business_stmt = select(BusinessClient)
    request_stmt = select(BusinessSpaceRequest).order_by(BusinessSpaceRequest.created_at.desc())
    if not actor.is_admin:
        business_stmt = business_stmt.where(BusinessClient.client_id == actor.business_id)
        request_stmt = request_stmt.where(BusinessSpaceRequest.client_id == actor.business_id)
    businesses = [
        {"clientId": r.client_id, "name": r.name, "enabled": r.enabled}
        for r in session.scalars(business_stmt)
    ]
    members = []
    if actor.is_admin:
        memberships = {r.user_id: r for r in session.scalars(select(BusinessMember))}
        for member in list_members(
            session, initial_admin_ids=application.settings.initial_admin_user_ids
        ):
            link = memberships.get(member["userId"])
            members.append(
                {
                    **member,
                    "clientId": link.client_id if link else None,
                    "role": "admin" if member["isAdmin"] else link.role if link else "user",
                }
            )
    rows = {r.space_name: r for r in session.scalars(select(BusinessGraphSpace))}
    if actor.is_admin:
        names = sorted(set(GraphSpaceService(session)._all_spaces()) | set(rows))
    else:
        names = sorted(
            r.space_name
            for r in rows.values()
            if r.client_id == actor.business_id or r.is_shared_production
        )
    spaces = [
        {
            "name": name,
            "clientId": rows[name].client_id if name in rows else None,
            "isSharedProduction": bool(name in rows and rows[name].is_shared_production),
        }
        for name in names
    ]
    return ApiResponse(
        data={
            "businesses": businesses,
            "members": members,
            "spaces": spaces,
            "requests": [_request_dict(r) for r in session.scalars(request_stmt)],
            "currentBusinessId": actor.business_id,
        }
    )


@router.put("/businesses/{client_id}")
def save_business(client_id: str, payload: BusinessPayload, actor: CurrentAdmin, session: Db):
    import re

    require_enabled()
    if not re.fullmatch(CLIENT_PATTERN, client_id) or not payload.name.strip():
        raise HTTPException(422, "业务标识或名称不合法")
    row = session.get(BusinessClient, client_id)
    if row is None:
        row = BusinessClient(client_id=client_id)
        session.add(row)
    row.name, row.enabled = payload.name.strip(), payload.enabled
    _audit(session, actor, "SAVE_BUSINESS", client_id, payload.model_dump())
    return ApiResponse(data={"clientId": client_id})


@router.put("/members/{user_id}")
def save_member(
    user_id: str,
    payload: MemberPayload,
    actor: CurrentAdmin,
    session: Db,
    application: AuthApplicationDependency,
):
    require_enabled()
    if session.get(PlatformUser, user_id) is None:
        raise HTTPException(404, "用户不存在，请先登录一次以登记统一认证 ID")
    if payload.clientId:
        _business(session, payload.clientId)
    elif payload.role == "developer":
        raise HTTPException(400, "开发维护角色必须归属一个业务")
    try:
        set_admin_role(
            session,
            user_id=user_id,
            enabled=payload.role == "admin",
            actor=actor,
            immutable_admin_ids=application.settings.initial_admin_user_ids,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    row = session.get(BusinessMember, user_id)
    if payload.clientId:
        if row is None:
            row = BusinessMember(user_id=user_id)
            session.add(row)
        row.client_id = payload.clientId
        row.role = "developer" if payload.role == "developer" else "user"
    elif row is not None:
        session.delete(row)
    _audit(session, actor, "BIND_BUSINESS_MEMBER", user_id, payload.model_dump())
    return ApiResponse(data={"userId": user_id})


@router.put("/spaces/{space_name}")
def save_space(space_name: str, payload: SpacePayload, actor: CurrentAdmin, session: Db):
    import re

    require_enabled()
    if not re.fullmatch(SPACE_PATTERN, space_name):
        raise HTTPException(422, "图空间名称不合法")
    if payload.isSharedProduction and payload.clientId:
        raise HTTPException(400, "共享生产空间不归属单个业务")
    if payload.clientId:
        _business(session, payload.clientId)
    if space_name not in GraphSpaceService(session).client.list_spaces():
        raise HTTPException(404, "图空间不存在")
    row = session.get(BusinessGraphSpace, space_name)
    if row is not None and row.provision_request_id:
        request = session.get(BusinessSpaceRequest, row.provision_request_id)
        if request is not None and request.status in {"creating", "failed"}:
            raise HTTPException(409, "请先完成该空间的创建申请，再调整业务归属")
    if row is None:
        row = BusinessGraphSpace(space_name=space_name)
        session.add(row)
    row.client_id = payload.clientId
    row.is_shared_production = payload.isSharedProduction
    row.shared_key = "production" if payload.isSharedProduction else None
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "已存在共享生产空间，请先取消原空间的共享标记") from exc
    _audit(session, actor, "BIND_BUSINESS_SPACE", space_name, payload.model_dump())
    return ApiResponse(data={"name": space_name})


@router.post("/requests")
def request_space(payload: RequestPayload, actor: CurrentMaintainer, session: Db):
    require_enabled()
    if payload.clientId and not actor.is_admin and payload.clientId != actor.business_id:
        raise HTTPException(403, "不能为其他业务申请空间")
    client_id = payload.clientId if actor.is_admin and payload.clientId else actor.business_id
    _business(session, client_id)
    if session.get(BusinessGraphSpace, payload.spaceName) is not None:
        raise HTTPException(409, "图空间名称已登记")
    duplicate = session.scalar(
        select(BusinessSpaceRequest.id).where(
            BusinessSpaceRequest.client_id == client_id,
            BusinessSpaceRequest.space_name == payload.spaceName,
            BusinessSpaceRequest.status.in_(("pending", "creating", "failed")),
        )
    )
    if duplicate:
        raise HTTPException(409, "该图空间已有待处理申请")
    row = BusinessSpaceRequest(
        client_id=client_id,
        space_name=payload.spaceName,
        active_space_name=payload.spaceName,
        reason=payload.reason,
        requested_by=actor.user_id,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "该空间已有待处理申请") from exc
    _audit(session, actor, "REQUEST_BUSINESS_SPACE", row.id, payload.model_dump())
    return ApiResponse(data=_request_dict(row))


def _provision(request_id: str, actor) -> dict:
    # Ownership reservation is committed before DDL. A failed DDL never frees the name
    # for another business; retry can only finish this administrator-approved request.
    try:
        with session_scope() as session:
            request = session.get(BusinessSpaceRequest, request_id)
            registry = session.get(BusinessGraphSpace, request.space_name)
            if registry is None or registry.provision_request_id != request.id:
                raise HTTPException(409, "空间申请归属已变化")
            service = GraphSpaceService(session)
            if request.space_name not in service.client.list_spaces():
                result = service.create_space(actor, request.space_name)
                if result.get("vectorDbStatus") != "ready":
                    raise RuntimeError("vector database provisioning incomplete")
            else:
                status, _ = service._ensure_vector_database(request.space_name)
                if status != "ready":
                    raise RuntimeError("vector database provisioning incomplete")
        with session_scope() as session:
            request = session.get(BusinessSpaceRequest, request_id)
            request.status, request.last_error = "ready", ""
            request.active_space_name = None
            session.flush()
            return _request_dict(request)
    except Exception as exc:
        with session_scope() as session:
            request = session.get(BusinessSpaceRequest, request_id)
            request.status = "failed"
            request.last_error = "空间创建未完成，请管理员检查图服务后重试"
            session.flush()
            result = _request_dict(request)
        import logging

        logging.getLogger(__name__).warning(
            "Approved space provisioning failed: %s", type(exc).__name__
        )
        return result


@router.post("/requests/{request_id}/decision")
def decide_request(request_id: str, payload: DecisionPayload, actor: CurrentAdmin, session: Db):
    require_enabled()
    row = session.scalar(
        select(BusinessSpaceRequest).where(BusinessSpaceRequest.id == request_id).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "申请不存在")
    if row.status != "pending":
        raise HTTPException(409, "该申请已经处理")
    row.reviewed_by, row.review_note = actor.user_id, payload.note
    if not payload.approve:
        row.status = "rejected"
        row.active_space_name = None
        _audit(session, actor, "REJECT_BUSINESS_SPACE", row.id, payload.model_dump())
        return ApiResponse(data=_request_dict(row))
    _business(session, row.client_id)
    if session.get(BusinessGraphSpace, row.space_name) is not None:
        raise HTTPException(409, "空间已被登记，请检查现有空间归属")
    if row.space_name in GraphSpaceService(session).client.list_spaces():
        raise HTTPException(409, "图空间已存在，请使用现有空间绑定")
    session.add(
        BusinessGraphSpace(
            space_name=row.space_name, client_id=row.client_id, provision_request_id=row.id
        )
    )
    row.status = "creating"
    _audit(session, actor, "APPROVE_BUSINESS_SPACE", row.id, payload.model_dump())
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "空间名称已被另一申请占用") from exc
    return ApiResponse(data=_provision(request_id, actor))


@router.post("/requests/{request_id}/retry")
def retry_request(request_id: str, actor: CurrentAdmin, session: Db):
    require_enabled()
    row = session.scalar(
        select(BusinessSpaceRequest).where(BusinessSpaceRequest.id == request_id).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "申请不存在")
    expired = row.status == "creating" and row.updated_at < datetime.now(UTC).replace(
        tzinfo=None
    ) - timedelta(minutes=10)
    if row.status != "failed" and not expired:
        raise HTTPException(409, "仅失败的已批准申请可重试")
    _business(session, row.client_id)
    row.status = "creating"
    row.updated_at = datetime.now(UTC).replace(tzinfo=None)
    _audit(session, actor, "RETRY_BUSINESS_SPACE", row.id, {})
    session.commit()
    return ApiResponse(data=_provision(request_id, actor))
