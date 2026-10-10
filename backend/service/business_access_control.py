"""Server-owned business and graph-space authorization. No frontend identity is trusted."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessMembership,
    BusinessMembershipState,
    BusinessSpacePolicy,
)
from infra.mysql import session_scope

if TYPE_CHECKING:
    from service.platform_access import PlatformActor


def rbac_enabled() -> bool:
    return os.getenv("BUSINESS_RBAC_ENABLED", "false").lower() in {"true", "1", "yes", "on"}


def membership_grants(session, user_id: str):
    from service.platform_access import BusinessMembershipGrant

    source = BusinessMembership if session.get(BusinessMembershipState, user_id) else BusinessMember
    rows = session.execute(
        select(source.client_id, source.role, BusinessClient.name)
        .join(BusinessClient, source.client_id == BusinessClient.client_id)
        .where(source.user_id == user_id, BusinessClient.enabled.is_(True))
        .order_by(source.client_id)
    )
    return tuple(BusinessMembershipGrant(r.client_id, r.role if r.role in {"user", "developer"} else "user", r.name) for r in rows)


def resolve_memberships(user_id: str):
    if not rbac_enabled():
        return ()
    try:
        with session_scope() as session:
            return membership_grants(session, user_id)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "业务权限表不可用，请先完成数据库初始化") from exc


def resolve_membership(user_id: str) -> tuple[str, str]:
    """多业务用户不向旧调用方返回任意首项，防止把任务归入错误业务。"""
    grants = resolve_memberships(user_id)
    return (grants[0].client_id, grants[0].role) if len(grants) == 1 else ("", "user")


def with_memberships(actor):
    grants = resolve_memberships(actor.user_id)
    single = grants[0] if len(grants) == 1 else None
    return replace(actor, memberships=grants, business_id=single.client_id if single else "",
                   business_role=single.role if single else "user")


def business_summaries(actor) -> list[dict[str, str]]:
    if rbac_enabled() and actor.is_admin and not actor.business_only:
        try:
            with session_scope() as session:
                return [{"clientId": row.client_id, "name": row.name, "role": "admin"}
                        for row in session.scalars(select(BusinessClient).where(BusinessClient.enabled.is_(True)).order_by(BusinessClient.client_id))]
        except SQLAlchemyError as exc:
            raise HTTPException(503, "无法读取授权业务目录") from exc
    return [{"clientId": grant.client_id, "name": grant.name, "role": grant.role}
            for grant in actor.memberships or ()]


@dataclass(frozen=True)
class SpaceRegistration:
    space_name: str
    client_id: str | None
    is_shared_production: bool
    business_name: str = ""
    business_enabled: bool = True


def space_registrations(session) -> dict[str, SpaceRegistration]:
    businesses = {r.client_id: r for r in session.scalars(select(BusinessClient))}
    rows = {r.space_name: r for r in session.scalars(select(BusinessGraphSpace))}
    policies = {r.space_name: r for r in session.scalars(select(BusinessSpacePolicy))}
    result = {}
    for name in rows.keys() | policies.keys():
        old, policy = rows.get(name), policies.get(name)
        public = policy.visibility == "public" if policy else bool(old.is_shared_production)
        client_id = policy.client_id if policy and policy.visibility == "business" else (
            None if policy or public else old.client_id)
        business = businesses.get(client_id)
        result[name] = SpaceRegistration(name, client_id, public,
            business.name if business else "", bool(business and business.enabled) if client_id else True)
    return result


def space_registration(session, space: str):
    return space_registrations(session).get(space)


def _space_allowed(actor: PlatformActor, row: BusinessGraphSpace, action: str) -> bool:
    if action not in {"read", "write", "review", "review_view"}:
        return False
    if actor.business_only:
        return action == "read" and row.is_shared_production
    if actor.is_admin:
        return True
    if not row.is_shared_production and not (
        getattr(row, "business_enabled", True) and row.client_id in actor.developer_business_ids
    ):
        return False
    if action == "read":
        return True
    if not actor.can_develop:
        return False
    if action == "review_view":
        # 查看档：开发维护对共享生产空间的人工审核可见（只读）；
        # 操作档 review 仍排除共享空间，仅业务空间可审。
        return True
    return not row.is_shared_production


def ensure_space_access(actor: PlatformActor, space: str | None, action: str = "read") -> None:
    if not rbac_enabled():
        return
    if not space:
        from service.graph_space import default_graph_space

        space = default_graph_space()
    if action not in {"read", "write", "review", "review_view"}:
        raise HTTPException(403, "不支持的空间操作")
    if actor.is_admin and not actor.business_only:
        return
    try:
        with session_scope() as session:
            row = space_registration(session, space)
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
            rows = space_registrations(session).values()
            return sorted(row.space_name for row in rows if _space_allowed(actor, row, action))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "无法读取图空间权限") from exc


def space_items(actor: PlatformActor) -> list[dict]:
    names = allowed_space_names(actor)
    with session_scope() as session:
        rows = space_registrations(session)
        result = []
        for name in names:
            row = rows.get(name)
            admin = actor.is_admin and not actor.business_only
            result.append(
                {
                    "name": name,
                    "bound": True,
                    # 原配置页用 mine 筛选可显示行；新模式表示已授权，不能作为写权限。
                    "mine": True,
                    "clientId": row.client_id if row else None,
                    "businessName": row.business_name if row else "",
                    "groupKind": "public" if row and row.is_shared_production else "business" if row and row.client_id else "unassigned",
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
    if not actor.developer_business_ids:
        return []
    with session_scope() as session:
        return list(
            session.scalars(
                select(BusinessMembership.user_id).where(BusinessMembership.client_id.in_(actor.developer_business_ids))
            )
        )


def owner_in_business(actor: PlatformActor, owner: str) -> bool:
    owners = resource_owner_ids(actor)
    return owners is None or owner in owners


def ensure_resource_owner(actor: PlatformActor, owner: str) -> None:
    if not actor.can_develop or not owner_in_business(actor, owner):
        raise HTTPException(403, "无权维护其他业务的资源")
