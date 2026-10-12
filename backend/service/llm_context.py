"""Trusted, request-local business selection for model calls."""

from contextvars import ContextVar

from fastapi import HTTPException

selected_llm_business: ContextVar[str | None] = ContextVar("selected_llm_business", default=None)
request_llm_settings: ContextVar[dict | None] = ContextVar("request_llm_settings", default=None)


def resolve_request_llm_settings():
    """Keep one request on the same model even when its business default changes mid-call."""
    from service.llm_config import resolve_llm_settings

    snapshot = request_llm_settings.get()
    if snapshot is not None and "settings" in snapshot:
        return snapshot["settings"]
    settings = resolve_llm_settings(business_id=selected_llm_business.get())
    if snapshot is not None:
        snapshot["settings"] = settings
    return settings


def request_llm_business(actor, space: str) -> str | None:
    from infra.mysql import session_scope
    from service.business_access_control import rbac_enabled, space_registration

    if not rbac_enabled():
        return None
    with session_scope() as session:
        registration = space_registration(session, space)
    space_business = (
        registration.client_id if registration and not registration.is_shared_production else None
    )
    selected = actor.context_business_id or space_business
    if actor.context_business_id and space_business and selected != space_business:
        raise HTTPException(403, "模型业务与当前图空间不一致")
    if selected:
        if not actor.is_admin and selected not in actor.business_ids:
            raise HTTPException(403, "无权使用其他业务的默认模型")
        return selected
    if actor.is_admin:
        return None
    # 公共空间没有明确业务时，只在唯一归属下使用业务默认；否则使用公共默认。
    # 不因模型业务不明确而阻断本来有权访问的普通业务查询。
    return actor.business_ids[0] if len(actor.business_ids) == 1 else None
