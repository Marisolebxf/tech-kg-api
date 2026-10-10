"""资源归属工具：配置类资源按 owner 隔离的通用逻辑。"""

from __future__ import annotations

from fastapi import HTTPException

from service.platform_access import PlatformActor


def selected_business_id(actor: PlatformActor, *, required: bool = True) -> str:
    from db_model.business_access import BusinessClient
    from infra.mysql import session_scope
    from service.business_access_control import ensure_space_access, space_registration

    selected = actor.context_business_id
    with session_scope() as session:
        if actor.context_graph_space:
            ensure_space_access(actor, actor.context_graph_space, "read")
            space = space_registration(session, actor.context_graph_space)
            space_business = space.client_id if space and not space.is_shared_production else None
            if space_business:
                if selected and selected != space_business:
                    raise HTTPException(403, "配置业务与当前图空间归属不一致")
                selected = space_business
        if not selected and not actor.is_admin and len(actor.developer_business_ids) == 1:
            selected = actor.developer_business_ids[0]
        if selected:
            if not actor.is_admin and selected not in actor.developer_business_ids:
                raise HTTPException(403, "无权访问所选业务配置")
            row = session.get(BusinessClient, selected)
            if row is None or not row.enabled:
                raise HTTPException(403, "所选业务不存在或已停用")
        elif required:
            raise HTTPException(400, "请先选择配置所属业务")
    return selected


def validate_owner_update(
    actor: PlatformActor, data: dict, *, current_owner: str | None = None
) -> None:
    """仅管理员的明确编辑允许改变已有配置归属。"""
    from service.business_access_control import rbac_enabled

    if not rbac_enabled() or "owner" not in data:
        return
    if not actor.is_admin:
        data.pop("owner", None)
        return
    owner = data["owner"] or ""
    if owner == current_owner:
        return
    if not owner.startswith("business:"):
        raise HTTPException(400, "请选择配置所属业务")
    from dataclasses import replace

    selected_business_id(replace(actor, context_business_id=owner.removeprefix("business:")))


def resource_owner_filter(actor: PlatformActor) -> str | None:
    """列表过滤值：管理员返回 None（不过滤），普通用户返回自身 user_id。"""
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        if not actor.can_develop:
            raise HTTPException(403, "仅开发维护可访问业务配置")
        selected = selected_business_id(actor, required=not actor.is_admin)
        return f"business:{selected}" if selected else None
    return None if actor.is_admin else actor.user_id


def ensure_owner_access(actor: PlatformActor, owner: str) -> None:
    """校验 actor 可操作该资源：管理员放行，普通用户仅限自己的资源。"""
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        # 资源保持原业务归属，用户的其他业务授权不能改变它。
        # 请求或任务明确指定业务时，进一步限制为该业务。
        if actor.is_admin and not actor.business_only:
            if actor.context_business_id or actor.context_graph_space:
                selected = selected_business_id(actor, required=False)
                if selected and owner != f"business:{selected}":
                    raise HTTPException(
                        403, "配置不属于当前业务；请在公共空间取消业务筛选后核实旧配置归属"
                    )
            return
        if not actor.can_develop or not owner.startswith("business:"):
            raise HTTPException(403, "无权访问其他业务配置")
        business = owner.removeprefix("business:")
        if business not in actor.developer_business_ids:
            raise HTTPException(403, "无权访问其他业务配置")
        if actor.context_business_id or actor.context_graph_space:
            if selected_business_id(actor) != business:
                raise HTTPException(403, "配置不属于当前业务")
        return
    if not actor.is_admin and owner != actor.user_id:
        raise HTTPException(status_code=403, detail="无权访问他人配置")


def assigned_resource_owner(actor: PlatformActor, requested: str = "") -> str:
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        from dataclasses import replace

        if actor.is_admin and requested.startswith("business:") and not actor.context_business_id:
            actor = replace(actor, context_business_id=requested.removeprefix("business:"))
        return f"business:{selected_business_id(actor)}"
    scope = resource_owner_filter(actor)
    return scope if scope is not None else requested or actor.user_id
