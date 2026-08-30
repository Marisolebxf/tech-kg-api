"""资源归属工具：配置类资源按 owner 隔离的通用逻辑。"""

from __future__ import annotations

from fastapi import HTTPException

from service.platform_access import PlatformActor


def resource_owner_filter(actor: PlatformActor) -> str | None:
    """列表过滤值：管理员返回 None（不过滤），普通用户返回自身 user_id。"""
    return None if actor.is_admin else actor.user_id


def ensure_owner_access(actor: PlatformActor, owner: str) -> None:
    """校验 actor 可操作该资源：管理员放行，普通用户仅限自己的资源。"""
    if not actor.is_admin and owner != actor.user_id:
        raise HTTPException(status_code=403, detail="无权访问他人配置")
