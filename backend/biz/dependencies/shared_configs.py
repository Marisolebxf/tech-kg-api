"""Platform-shared LLM/MySQL access, independent of legacy owner metadata."""

from fastapi import HTTPException

from service.platform_access import PlatformActor


def ensure_shared_config_read(actor: PlatformActor) -> None:
    if not actor.can_develop:
        raise HTTPException(403, "仅管理员和开发人员可以查看或使用共享配置")


def ensure_shared_config_manage(actor: PlatformActor) -> None:
    if not actor.is_admin or actor.business_only:
        raise HTTPException(403, "仅管理员可以修改共享配置")
