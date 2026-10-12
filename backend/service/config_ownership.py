"""Server-owned public/business authorization for MySQL and language models."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from biz.dependencies.shared_configs import ensure_shared_config_manage, ensure_shared_config_read
from db_model.business_access import BusinessClient
from db_model.config_ownership import ConfigOwnership
from service.platform_access import PlatformActor


def assigned_config_business(session: Session, actor: PlatformActor) -> str | None:
    ensure_shared_config_read(actor)
    if actor.is_admin:
        return None
    ids = actor.developer_business_ids
    if len(ids) != 1:
        raise HTTPException(403, "开发人员必须且只能绑定一个业务后创建配置")
    business = session.get(BusinessClient, ids[0])
    if business is None or not business.enabled:
        raise HTTPException(403, "所属业务不存在或已停用")
    return business.client_id


def _businesses(session: Session, ids: set[str]) -> dict[str, BusinessClient]:
    if not ids:
        return {}
    return {
        row.client_id: row
        for row in session.scalars(select(BusinessClient).where(BusinessClient.client_id.in_(ids)))
    }


def _allowed(actor: PlatformActor, business_id: str | None, businesses: dict) -> bool:
    if actor.is_admin and not actor.business_only:
        return True
    if not actor.can_develop:
        return False
    if business_id is None:
        return True
    business = businesses.get(business_id)
    return bool(business and business.enabled and business_id in actor.developer_business_ids)


def ensure_config_access(
    session: Session,
    actor: PlatformActor,
    kind: str,
    config_id: str,
    *,
    manage: bool = False,
) -> None:
    ensure_shared_config_read(actor)
    policy = session.get(ConfigOwnership, (kind, config_id))
    business_id = policy.business_id if policy else None
    businesses = _businesses(session, {business_id} if business_id else set())
    if not _allowed(actor, business_id, businesses):
        raise HTTPException(403, "无权访问其他业务配置")
    if (
        not actor.is_admin
        and business_id is not None
        and actor.context_business_id
        and actor.context_business_id != business_id
    ):
        raise HTTPException(403, "配置不属于当前业务")
    if manage and business_id is None:
        ensure_shared_config_manage(actor)


def visible_configurations(
    session: Session, actor: PlatformActor, kind: str, configs: list[dict]
) -> list[dict]:
    ensure_shared_config_read(actor)
    if not configs:
        return []
    ids = [item["id"] for item in configs]
    policies = {
        row.config_id: row.business_id
        for row in session.scalars(
            select(ConfigOwnership).where(
                ConfigOwnership.config_kind == kind, ConfigOwnership.config_id.in_(ids)
            )
        )
    }
    businesses = _businesses(session, {value for value in policies.values() if value})
    result = []
    for item in configs:
        business_id = policies.get(item["id"])
        if not _allowed(actor, business_id, businesses):
            continue
        business = businesses.get(business_id)
        result.append(
            {
                **item,
                "visibility": "business" if business_id is not None else "public",
                "businessId": business_id,
                "businessName": business.name if business else business_id or "",
                "canManage": actor.is_admin or business_id is not None,
            }
        )
    return result


def config_output(session: Session, actor: PlatformActor, kind: str, data: dict) -> dict:
    visible = visible_configurations(session, actor, kind, [data])
    if not visible:
        raise HTTPException(403, "无权访问其他业务配置")
    return visible[0]


def guard_default_change(actor: PlatformActor, data: dict, current: dict | None = None) -> None:
    """Keep the existing admin-only default control, including create/update paths."""
    if "is_default" not in data or data["is_default"] is None:
        return
    if bool(data["is_default"]) != bool((current or {}).get("isDefault", False)):
        ensure_shared_config_manage(actor)
