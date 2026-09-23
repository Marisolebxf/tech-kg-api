"""Write guards for legacy business endpoints targeting the default graph."""

from fastapi import HTTPException

from biz.dependencies.auth import CurrentActor
from service.business_access_control import ensure_space_access, rbac_enabled


def require_default_space_writer(actor: CurrentActor) -> None:
    if rbac_enabled():
        if not actor.can_develop:
            raise HTTPException(403, "仅开发维护或管理员可以修改业务数据")
        ensure_space_access(actor, None, "write")
    elif not actor.is_admin:
        raise HTTPException(403, "仅全局管理员可以执行该操作")


def require_default_annotation_writer(actor: CurrentActor) -> None:
    if rbac_enabled():
        require_default_space_writer(actor)
