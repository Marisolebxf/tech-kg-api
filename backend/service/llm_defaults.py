"""Business model preferences and public defaults, independent of edit permission."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.business_access import BusinessClient
from db_model.config_ownership import ConfigOwnership
from db_model.llm_config import LlmConfig
from db_model.llm_default import BusinessLlmDefault
from service.config_ownership import assigned_config_business, ensure_config_access


def config_business(session: Session, config_id: str) -> str | None:
    policy = session.get(ConfigOwnership, ("llm", config_id))
    return policy.business_id if policy else None


def public_default(session: Session) -> LlmConfig | None:
    rows = list(session.scalars(select(LlmConfig).where(LlmConfig.is_default.is_(True))))
    if len(rows) > 1 or any(config_business(session, row.id) for row in rows):
        raise HTTPException(409, "现有公共默认模型归属冲突，请管理员检查迁移")
    return rows[0] if rows else None


def resolve_default_config(
    session: Session, business_id: str | None = None, config_id: str | None = None
) -> LlmConfig | None:
    if business_id:
        business = session.get(BusinessClient, business_id)
        if business is None or not business.enabled:
            raise HTTPException(403, "所属业务不存在或已停用")
    selected = config_id
    if not selected and business_id:
        preference = session.get(BusinessLlmDefault, business_id)
        selected = preference.config_id if preference else None
    row = session.get(LlmConfig, selected) if selected else public_default(session)
    if selected and row is None:
        raise HTTPException(409, "已选择的语言模型不存在，请重新设置")
    if row is None:
        return None
    owner_business = config_business(session, row.id)
    if owner_business and owner_business != business_id:
        raise HTTPException(403, "语言模型不属于当前业务")
    if row.status == "停用":
        raise HTTPException(409, "已选择的语言模型已停用，请重新设置")
    if not row.api_key:
        raise HTTPException(409, "已选择的语言模型未配置 API Key")
    return row


def default_referenced(session: Session, config_id: str) -> bool:
    row = session.get(LlmConfig, config_id)
    return bool(
        (row and row.is_default)
        or session.scalar(
            select(BusinessLlmDefault.business_id)
            .where(BusinessLlmDefault.config_id == config_id)
            .limit(1)
        )
    )


def guard_default_removal(session: Session, config_id: str) -> None:
    # Serialize against preference changes targeting this model.
    row = session.scalar(
        select(LlmConfig)
        .where(LlmConfig.id == config_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    reference = session.scalar(
        select(BusinessLlmDefault.business_id)
        .where(BusinessLlmDefault.config_id == config_id)
        .with_for_update()
        .execution_options(populate_existing=True)
        .limit(1)
    )
    if (row and row.is_default) or reference:
        raise HTTPException(409, "模型正被公共默认或业务默认引用，请先切换默认模型")


def set_default_for_actor(session: Session, actor, config_id: str) -> None:
    business_id = assigned_config_business(session, actor)
    ensure_config_access(session, actor, "llm", config_id)
    if business_id:
        # Business row exists even before its first preference; locks concurrent first inserts.
        session.scalar(
            select(BusinessClient)
            .where(BusinessClient.client_id == business_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        rows = [
            session.scalar(
                select(LlmConfig)
                .where(LlmConfig.id == config_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ]
    else:
        # Stable ordering serializes concurrent switches of the public default.
        rows = list(
            session.scalars(
                select(LlmConfig)
                .order_by(LlmConfig.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
    row = next((row for row in rows if row and row.id == config_id), None)
    if row is None:
        raise HTTPException(404, "LLM 配置不存在")
    if row.status == "停用":
        raise HTTPException(409, "停用的语言模型不能设为默认")
    if row.status == "异常":
        raise HTTPException(409, "异常的语言模型不能设为默认，请先恢复连接")
    if not row.api_key:
        raise HTTPException(409, "未配置 API Key 的语言模型不能设为默认")
    if business_id is None:
        if config_business(session, config_id) is not None:
            raise HTTPException(403, "公共默认只能选择公共语言模型")
        for item in rows:
            item.is_default = item.id == config_id
    else:
        preference = session.scalar(
            select(BusinessLlmDefault)
            .where(BusinessLlmDefault.business_id == business_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if preference is None:
            session.add(BusinessLlmDefault(business_id=business_id, config_id=config_id))
        else:
            preference.config_id = config_id
    session.commit()


def referencing_business_names(session: Session, config_ids: list[str]) -> dict[str, list[str]]:
    """各配置被哪些业务设为默认（业务名，缺失业务行时回退 client_id），供占用提示使用。"""
    if not config_ids:
        return {}
    rows = session.execute(
        select(BusinessLlmDefault.config_id, BusinessClient.name, BusinessLlmDefault.business_id)
        .outerjoin(BusinessClient, BusinessClient.client_id == BusinessLlmDefault.business_id)
        .where(BusinessLlmDefault.config_id.in_(config_ids))
    ).all()
    names: dict[str, list[str]] = {}
    for config_id, name, business_id in rows:
        names.setdefault(config_id, []).append(name or business_id)
    return names


def release_business_default_references(
    session: Session, actor, config_id: str, *, force: bool = False
) -> None:
    """删除/停用公共模型前处理业务默认绑定。

    业务把某公共模型设为默认后，该模型对管理员既不可删也不可停（旧口径），提示还失真。
    新口径：管理员 force 确认后解除全部业务绑定（业务回退公共默认），随后删除/停用与解绑同一事务提交；
    未 force 时 409 报真实占用方。公共默认本体仍不可删/停（默认必须恒有一条）；
    业务自有模型不走管理员强制通道，仍由业务自行切换默认。
    """
    row = session.scalar(
        select(LlmConfig)
        .where(LlmConfig.id == config_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise HTTPException(404, "LLM 配置不存在")
    if row.is_default:
        raise HTTPException(409, "公共默认模型不能删除或停用：请先将其他模型设为默认")
    preferences = list(
        session.scalars(
            select(BusinessLlmDefault)
            .where(BusinessLlmDefault.config_id == config_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if not preferences:
        return
    if config_business(session, config_id) is not None:
        raise HTTPException(409, "业务自有模型请由该业务先切换默认模型")
    names = referencing_business_names(session, [config_id]).get(config_id, [])
    if not (force and actor.is_admin and not actor.business_only):
        raise HTTPException(
            409,
            f"该模型是业务「{'、'.join(names)}」的默认模型，请先让对应业务切换默认模型",
        )
    for preference in preferences:
        session.delete(preference)


def decorate_defaults(session: Session, actor, configs: list[dict]) -> list[dict]:
    ids = actor.developer_business_ids
    business_id = ids[0] if not actor.is_admin and len(ids) == 1 else None
    business = session.get(BusinessClient, business_id) if business_id else None
    business_active = bool(business and business.enabled)
    if not business_active:
        business_id = None
    preference = session.get(BusinessLlmDefault, business_id) if business_id else None
    public = public_default(session)
    effective_id = preference.config_id if preference else public.id if public else None
    references = set(session.scalars(select(BusinessLlmDefault.config_id)))
    # 占用方业务名只给管理员（前端强制删除/停用的确认弹窗要用）；业务侧无需知道别家占用
    referenced_by = (
        referencing_business_names(session, [item["id"] for item in configs])
        if actor.is_admin
        else {}
    )
    source = "business" if preference else "public"
    return [
        {
            **item,
            "isDefault": item["id"] == effective_id,
            "defaultSource": source,
            "defaultReferenced": bool(
                item["id"] in references or (public and public.id == item["id"])
            ),
            "defaultReferencedBy": referenced_by.get(item["id"], []),
            "canSetDefault": bool(
                item.get("status") != "停用"
                and item.get("hasApiKey")
                and (
                    (business_active and business_id)
                    or (actor.is_admin and item.get("visibility") == "public")
                )
            ),
        }
        for item in configs
    ]
