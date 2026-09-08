"""门户身份验证、缓存撤权和本地授权叠加回归，不连接真实用户中心或业务库。"""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from config.auth import AuthSettings
from db_model.base import Base
from db_model.platform_governance import AdminAuditLog, PlatformUser, PlatformUserRole
from infra.redis import MemoryJsonStore
from infra.user_center import UserCenterError
from service import platform_access
from service.auth import AuthenticationError, AuthService
from service.platform_access import (
    ADMIN_ROLE,
    PORTAL_ROLE_SNAPSHOT,
    PlatformActor,
    actor_from_profile,
    list_members,
    set_admin_role,
)


class ClockStore(MemoryJsonStore):
    now = 0

    def _now(self):
        return self.now


class PortalCenter:
    def __init__(self, role=1):
        self.user = {"id": 139, "status": 0, "gkxUser": {"role": role}}
        self.calls = 0
        self.failure = False

    async def get_permission_info(self, token):
        return {
            "userInfo": {"id": 139, "username": "admin", "nickname": "管理员", "userType": 1},
            "allPermissions": {"roles": [{"id": 1, "name": "管理员", "code": "admin"}]},
        }

    async def get_user_by_token(self, token):
        self.calls += 1
        if self.failure:
            raise UserCenterError("门户身份服务不可用", status_code=503)
        return self.user

    async def check_token(self, token):
        return {"exp": 4_102_444_800}

    def build_login_url(self, state):
        return f"https://sso.test/login?state={state}"

    async def exchange_code(self, code, *, state):
        return {"access_token": "access", "expires_in": 3600, "refresh_token": "refresh"}

    async def refresh(self, token):
        return {"access_token": "new-access", "expires_in": 3600, "refresh_token": "refresh"}


def service_for(role=1):
    settings = replace(
        AuthSettings.from_env(),
        enabled=True,
        client_id="test",
        portal_admin_enabled=True,
        portal_role_cache_ttl_seconds=60,
        bearer_cache_ttl_seconds=300,
    )
    store = ClockStore()
    center = PortalCenter(role)
    return AuthService(settings, store, center), store, center


@pytest.mark.parametrize(
    "role, expected",
    [(1, True), (0, False), (None, False), (True, False), ("1", False), (2, False)],
)
async def test_only_documented_integer_role_grants_portal_admin(role, expected):
    service, _, _ = service_for(role)
    context = await service.resolve_bearer("access")
    assert service.profile(context).portal_is_admin is expected


async def test_missing_original_website_account_is_an_ordinary_user():
    service, _, center = service_for()
    center.user["gkxUser"] = None
    context = await service.create_session_from_access_token("access")
    assert context.portal_is_admin is False


@pytest.mark.parametrize("mode", ["session", "bearer"])
async def test_portal_revocation_rechecked_after_non_sliding_role_ttl(mode):
    service, store, center = service_for()
    if mode == "session":
        context = await service.create_session_from_access_token("access")

        async def load():
            return await service.get_session(context.session_id)
    else:

        async def load():
            return await service.resolve_bearer("access")

        context = await load()
    assert context.portal_is_admin is True
    center.user["gkxUser"]["role"] = 0
    store.now = 30
    assert (await load()).portal_is_admin is True
    assert center.calls == 1
    store.now = 61
    assert (await load()).portal_is_admin is False
    assert center.calls == 2


async def test_oauth_login_and_explicit_refresh_refresh_portal_identity():
    service, _, center = service_for()
    _, _, state = await service.create_login_url("/schema")
    context, next_path = await service.complete_login("code", state)
    assert next_path == "/schema"
    assert context.portal_is_admin is True
    center.user["gkxUser"]["role"] = 0
    context = await service.refresh_session(context.session_id, context=context)
    assert context.portal_is_admin is False


async def test_existing_session_without_portal_role_is_verified_on_upgrade():
    service, store, _ = service_for()
    await store.set_json(
        service.SESSION_KEY_PREFIX + "old-session",
        {
            "access_token": "access",
            "permission_info": {"userInfo": {"id": 139}},
            "expires_at": 4_102_444_800,
        },
        1800,
    )
    assert (await service.get_session("old-session")).portal_is_admin is True


async def test_role_service_failure_never_reuses_expired_admin_identity():
    service, store, center = service_for()
    context = await service.create_session_from_access_token("access")
    store.now = 61
    center.failure = True
    with pytest.raises(AuthenticationError, match="门户身份服务不可用"):
        await service.get_session(context.session_id)


@pytest.mark.parametrize("field,value", [("id", 999), ("status", 1)])
async def test_foreign_or_disabled_identity_is_rejected(field, value):
    service, _, center = service_for()
    center.user[field] = value
    with pytest.raises(AuthenticationError):
        await service.resolve_bearer("access")


async def test_local_only_mode_does_not_call_portal_identity_service():
    service, _, center = service_for()
    service.settings = replace(service.settings, portal_admin_enabled=False)
    assert (await service.resolve_bearer("access")).portal_is_admin is False
    assert center.calls == 0


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[PlatformUser.__table__, PlatformUserRole.__table__, AdminAuditLog.__table__]
    )
    with Session(engine, expire_on_commit=False) as session:

        @contextmanager
        def scope():
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

        monkeypatch.setattr(platform_access, "session_scope", scope)
        yield session
    engine.dispose()


def profile(user_id, portal_admin=False):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, username=user_id, nickname=user_id, email=""),
        portal_is_admin=portal_admin,
    )


@pytest.mark.parametrize(
    "portal_admin,local_admin", [(False, False), (True, False), (False, True), (True, True)]
)
def test_effective_role_is_union_without_permanent_local_grant(db, portal_admin, local_admin):
    db.add(PlatformUser(user_id="member", username="member"))
    if local_admin:
        db.add(PlatformUserRole(user_id="member", role_code=ADMIN_ROLE, granted_by="owner"))
    db.commit()
    actor = actor_from_profile(
        profile("member", portal_admin), initial_admin_ids=(), auth_enabled=True
    )
    assert actor.is_admin is (portal_admin or local_admin)
    assert actor.portal_is_admin is portal_admin
    assert (
        bool(db.scalar(select(PlatformUserRole.id).where(PlatformUserRole.role_code == ADMIN_ROLE)))
        is local_admin
    )
    assert list_members(db)[0]["isAdmin"] is actor.is_admin


def test_stale_portal_snapshot_never_grants_access_after_revocation(db):
    actor_from_profile(profile("member", True), initial_admin_ids=(), auth_enabled=True)
    assert db.scalar(
        select(PlatformUserRole.id).where(PlatformUserRole.role_code == PORTAL_ROLE_SNAPSHOT)
    )
    actor = actor_from_profile(profile("member", False), initial_admin_ids=(), auth_enabled=True)
    assert actor.is_admin is False
    assert list_members(db)[0]["isAdmin"] is False


def test_portal_admin_is_not_bootstrapped_into_permanent_local_admin(db):
    actor = actor_from_profile(
        profile("member", True), initial_admin_ids=(), auth_enabled=True, bootstrap_first_admin=True
    )
    assert actor.is_admin is True
    assert not db.scalar(
        select(PlatformUserRole.id).where(PlatformUserRole.role_code == ADMIN_ROLE)
    )


def test_local_grant_survives_portal_revocation_until_explicitly_removed(db):
    operator = actor_from_profile(
        profile("operator", True), initial_admin_ids=(), auth_enabled=True
    )
    actor_from_profile(profile("member", True), initial_admin_ids=(), auth_enabled=True)
    set_admin_role(db, user_id="member", enabled=True, actor=operator, immutable_admin_ids=())
    db.commit()
    assert actor_from_profile(
        profile("member", False), initial_admin_ids=(), auth_enabled=True
    ).is_admin
    result = set_admin_role(
        db, user_id="member", enabled=False, actor=operator, immutable_admin_ids=()
    )
    db.commit()
    assert result["isAdmin"] is False
    assert not actor_from_profile(
        profile("member", False), initial_admin_ids=(), auth_enabled=True
    ).is_admin


def test_revoke_local_role_does_not_revoke_portal_role(db):
    operator = actor_from_profile(
        profile("operator", True), initial_admin_ids=(), auth_enabled=True
    )
    actor_from_profile(profile("member", True), initial_admin_ids=(), auth_enabled=True)
    set_admin_role(db, user_id="member", enabled=True, actor=operator, immutable_admin_ids=())
    db.commit()
    result = set_admin_role(
        db, user_id="member", enabled=False, actor=operator, immutable_admin_ids=()
    )
    db.commit()
    assert result["isAdmin"] is True
    assert next(x for x in list_members(db) if x["userId"] == "member")["isAdmin"] is True
    with pytest.raises(ValueError, match="请在门户取消"):
        set_admin_role(db, user_id="member", enabled=False, actor=operator, immutable_admin_ids=())


def test_display_snapshot_cannot_bypass_last_local_admin_protection(db):
    actor_from_profile(
        profile("offline-portal-admin", True), initial_admin_ids=(), auth_enabled=True
    )
    db.add(PlatformUser(user_id="local-admin", username="local-admin"))
    db.add(PlatformUserRole(user_id="local-admin", role_code=ADMIN_ROLE, granted_by="owner"))
    db.commit()
    actor = PlatformActor("local-admin", "local-admin", "local-admin", "", True)
    with pytest.raises(ValueError, match="至少需要保留"):
        set_admin_role(
            db, user_id="local-admin", enabled=False, actor=actor, immutable_admin_ids=()
        )
