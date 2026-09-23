"""Server-owned business and graph-space authorization. No frontend identity is trusted."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from db_model.business_access import BusinessClient, BusinessGraphSpace, BusinessMember
from infra.mysql import session_scope

if TYPE_CHECKING:
    from service.platform_access import PlatformActor


def rbac_enabled() -> bool:
    return os.getenv("BUSINESS_RBAC_ENABLED", "false").lower() in {"true", "1", "yes", "on"}


def resolve_membership(user_id: str) -> tuple[str, str]:
    if not rbac_enabled():
        return "", "user"
    try:
        with session_scope() as session:
            row = session.execute(
                select(BusinessMember.client_id, BusinessMember.role)
                .join(BusinessClient, BusinessMember.client_id == BusinessClient.client_id)
                .where(BusinessMember.user_id == user_id, BusinessClient.enabled.is_(True))
            ).first()
            if row:
                return row.client_id, row.role if row.role in {"user", "developer"} else "user"
    except SQLAlchemyError as exc:
        raise HTTPException(503, "业务权限表不可用，请先完成数据库初始化") from exc
    return "", "user"


def _space_allowed(actor: PlatformActor, row: BusinessGraphSpace, action: str) -> bool:
    if action not in {"read", "write", "review"}:
        return False
    if actor.business_only:
        return action == "read" and (
            row.is_shared_production
            or bool(actor.business_id and row.client_id == actor.business_id)
        )
    if actor.is_admin:
        return True
    if not row.is_shared_production and not (
        actor.business_id and row.client_id == actor.business_id
    ):
        return False
    if action == "read":
        return True
    if not actor.can_develop:
        return False
    return action != "review" or not row.is_shared_production


def ensure_space_access(actor: PlatformActor, space: str | None, action: str = "read") -> None:
    if not rbac_enabled():
        return
    if not space:
        from service.graph_space import default_graph_space

        space = default_graph_space()
    if action not in {"read", "write", "review"}:
        raise HTTPException(403, "不支持的空间操作")
    if actor.is_admin and not actor.business_only:
        return
    try:
        with session_scope() as session:
            row = session.get(BusinessGraphSpace, space)
            if row is not None and _space_allowed(actor, row, action):
                return
    except SQLAlchemyError as exc:
        raise HTTPException(503, "无法校验图空间权限") from exc
    raise HTTPException(403, "无权对该图空间执行此操作")


def allowed_space_names(actor: PlatformActor, action: str = "read") -> list[str]:
    if actor.is_admin and not actor.business_only:
        from service.graph_space import GraphSpaceService

        with session_scope() as session:
            return list(GraphSpaceService(session)._all_spaces())
    try:
        with session_scope() as session:
            rows = session.scalars(select(BusinessGraphSpace)).all()
            return sorted(row.space_name for row in rows if _space_allowed(actor, row, action))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "无法读取图空间权限") from exc


def space_items(actor: PlatformActor) -> list[dict]:
    names = allowed_space_names(actor)
    with session_scope() as session:
        rows = {row.space_name: row for row in session.scalars(select(BusinessGraphSpace))}
        result = []
        for name in names:
            row = rows.get(name)
            admin = actor.is_admin and not actor.business_only
            result.append(
                {
                    "name": name,
                    "bound": True,
                    "mine": bool(row and actor.business_id and row.client_id == actor.business_id),
                    "clientId": row.client_id if row else None,
                    "isSharedProduction": bool(row and row.is_shared_production),
                    "readAllowed": True,
                    "writeAllowed": admin or bool(row and _space_allowed(actor, row, "write")),
                    "reviewAllowed": admin or bool(row and _space_allowed(actor, row, "review")),
                }
            )
        return result


def resource_owner_ids(actor: PlatformActor) -> list[str] | None:
    if actor.is_admin and not actor.business_only:
        return None
    if not actor.business_id:
        return []
    with session_scope() as session:
        return list(
            session.scalars(
                select(BusinessMember.user_id).where(BusinessMember.client_id == actor.business_id)
            )
        )


def owner_in_business(actor: PlatformActor, owner: str) -> bool:
    owners = resource_owner_ids(actor)
    return owners is None or owner in owners


def ensure_resource_owner(actor: PlatformActor, owner: str) -> None:
    if not actor.can_develop or not owner_in_business(actor, owner):
        raise HTTPException(403, "无权维护其他业务的资源")
