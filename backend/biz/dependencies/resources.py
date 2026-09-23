"""资源归属工具：配置类资源按 owner 隔离的通用逻辑。"""

from __future__ import annotations

from fastapi import HTTPException

from service.platform_access import PlatformActor


def resource_owner_filter(actor: PlatformActor) -> str | None:
    """列表过滤值：管理员返回 None（不过滤），普通用户返回自身 user_id。"""
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        if actor.is_admin and not actor.business_only:
            return None
        if not actor.can_develop:
            raise HTTPException(403, "仅开发维护可访问业务配置")
        return f"business:{actor.business_id}"
    return None if actor.is_admin else actor.user_id


def ensure_owner_access(actor: PlatformActor, owner: str) -> None:
    """校验 actor 可操作该资源：管理员放行，普通用户仅限自己的资源。"""
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        scope = resource_owner_filter(actor)
        if scope is not None and owner != scope:
            raise HTTPException(403, "无权访问其他业务配置")
        return
    if not actor.is_admin and owner != actor.user_id:
        raise HTTPException(status_code=403, detail="无权访问他人配置")


def assigned_resource_owner(actor: PlatformActor, requested: str = "") -> str:
    scope = resource_owner_filter(actor)
    return scope if scope is not None else requested or actor.user_id
