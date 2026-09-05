"""本系统的用户/全局管理员角色解析，不信任前端传入身份。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db_model.platform_governance import AdminAuditLog, PlatformUser, PlatformUserRole
from infra.mysql import session_scope

logger = logging.getLogger(__name__)

ADMIN_ROLE = "platform_admin"
USER_PERMISSIONS = ("analysis:read", "correction:submit")
ADMIN_PERMISSIONS = (
    "admin:access",
    "correction:review",
    "correction:sync",
    "member:manage",
    "schema:manage",
    "workflow:manage",
)


@dataclass(frozen=True, slots=True)
class PlatformActor:
    user_id: str
    username: str
    display_name: str
    email: str
    is_admin: bool

    @property
    def roles(self) -> list[str]:
        return ["platform_user", ADMIN_ROLE] if self.is_admin else ["platform_user"]

    @property
    def permissions(self) -> list[str]:
        values = [*USER_PERMISSIONS]
        if self.is_admin:
            values.extend(ADMIN_PERMISSIONS)
        return values


# 开发模式（认证未启用）下本进程已登记过成员表的用户：避免每请求重复 upsert。
_DEV_ACTOR_UPSERTED: set[str] = set()


def actor_from_profile(
    profile,
    *,
    initial_admin_ids: tuple[str, ...],
    auth_enabled: bool,
    bootstrap_first_admin: bool = False,
    force_admin: bool = False,
) -> PlatformActor:
    user_id = str(profile.user.id)
    bootstrap_admin = not auth_enabled or force_admin or user_id in initial_admin_ids
    if not auth_enabled and user_id in _DEV_ACTOR_UPSERTED:
        # 认证未启用的开发模式：该用户已在本进程登记过成员表，直接返回内存 Actor。
        # 否则管理端每个请求都会 upsert 同一用户行（last_seen_at），500 并发下
        # 该行成为 InnoDB 行锁热点，管理端接口吞吐被串行化在 ~800/s。
        return PlatformActor(
            user_id=user_id,
            username=profile.user.username,
            display_name=profile.user.nickname or profile.user.username,
            email=profile.user.email,
            is_admin=bootstrap_admin,
        )
    database_admin = False
    try:
        with session_scope() as session:
            _upsert_user(session, profile)
            session.flush()
            if not auth_enabled:
                # 开发模式仅首次登记成员表；真实认证路径每请求仍刷新 last_seen。
                _DEV_ACTOR_UPSERTED.add(user_id)
            if auth_enabled:
                role_id = session.scalar(
                    select(PlatformUserRole.id).where(
                        PlatformUserRole.user_id == user_id,
                        PlatformUserRole.role_code == ADMIN_ROLE,
                    )
                )
                database_admin = role_id is not None
                if bootstrap_first_admin and role_id is None:
                    first_admin_exists = bool(initial_admin_ids) or (
                        session.scalar(
                            select(PlatformUserRole.id)
                            .where(PlatformUserRole.role_code == ADMIN_ROLE)
                            .limit(1)
                            .with_for_update()
                        )
                        is not None
                    )
                    if not first_admin_exists:
                        session.add(
                            PlatformUserRole(
                                user_id=user_id,
                                role_code=ADMIN_ROLE,
                                granted_by="system-bootstrap",
                            )
                        )
                        database_admin = True
    except SQLAlchemyError:
        # 登录查询仍可使用；管理写操作会通过自己的数据库依赖明确报错。
        logger.warning("平台角色表不可用，请先执行治理表迁移", exc_info=True)
    return PlatformActor(
        user_id=user_id,
        username=profile.user.username,
        display_name=profile.user.nickname or profile.user.username,
        email=profile.user.email,
        is_admin=bootstrap_admin or database_admin,
    )


def _upsert_user(session: Session, profile) -> PlatformUser:
    user_id = str(profile.user.id)
    row = session.get(PlatformUser, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    if row is None:
        row = PlatformUser(user_id=user_id)
        session.add(row)
    row.username = profile.user.username
    row.nickname = profile.user.nickname
    row.email = profile.user.email
    row.last_seen_at = now
    return row


def list_members(
    session: Session, *, initial_admin_ids: tuple[str, ...] = ()
) -> list[dict[str, object]]:
    admin_ids = set(
        session.scalars(
            select(PlatformUserRole.user_id).where(PlatformUserRole.role_code == ADMIN_ROLE)
        )
    )
    admin_ids.update(initial_admin_ids)
    users = session.scalars(select(PlatformUser).order_by(PlatformUser.last_seen_at.desc())).all()
    return [
        {
            "userId": user.user_id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "isAdmin": user.user_id in admin_ids,
            "lastSeenAt": user.last_seen_at.isoformat() if user.last_seen_at else None,
        }
        for user in users
    ]


def set_admin_role(
    session: Session,
    *,
    user_id: str,
    enabled: bool,
    actor: PlatformActor,
    immutable_admin_ids: tuple[str, ...],
) -> dict[str, object]:
    user = session.get(PlatformUser, user_id)
    if user is None:
        raise KeyError(user_id)
    existing = session.scalar(
        select(PlatformUserRole).where(
            PlatformUserRole.user_id == user_id,
            PlatformUserRole.role_code == ADMIN_ROLE,
        )
    )
    if not enabled and user_id in immutable_admin_ids:
        raise ValueError("环境变量配置的首批管理员不能在页面中取消")
    if enabled and existing is None:
        session.add(
            PlatformUserRole(user_id=user_id, role_code=ADMIN_ROLE, granted_by=actor.user_id)
        )
    elif not enabled and existing is not None:
        persisted_admins = session.scalar(
            select(func.count())
            .select_from(PlatformUserRole)
            .where(PlatformUserRole.role_code == ADMIN_ROLE)
        )
        if persisted_admins <= 1 and not immutable_admin_ids:
            raise ValueError("至少需要保留一名全局管理员")
        session.execute(delete(PlatformUserRole).where(PlatformUserRole.id == existing.id))
    session.add(
        AdminAuditLog(
            actor_id=actor.user_id,
            actor_name=actor.display_name,
            action="GRANT_ADMIN" if enabled else "REVOKE_ADMIN",
            resource_type="platform_user",
            resource_id=user_id,
            detail={"isAdmin": enabled},
        )
    )
    return {"userId": user_id, "isAdmin": enabled}
