"""登录续期和主动退出的并发回归；不连接真实用户中心或数据库。"""

import asyncio
import time
from dataclasses import replace
from typing import Any

import pytest

from config.auth import AuthSettings
from infra.redis import MemoryJsonStore
from infra.user_center import UserCenterError
from service.auth import AuthContext, AuthenticationError, AuthService


class ManualClockStore(MemoryJsonStore):
    def __init__(self) -> None:
        super().__init__()
        self.now = 2_000_000_000.0

    def _now(self) -> float:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


class RecoveryUserCenter:
    def __init__(self) -> None:
        self.checked: list[str] = []
        self.revoked: list[str] = []
        self.refresh_count = 0
        self.check_expires_at: int | None = None
        self.omit_check_expiry = False
        self.refresh_started: asyncio.Event | None = None
        self.refresh_release: asyncio.Event | None = None
        self.refresh_error: UserCenterError | None = None

    def build_login_url(self, state: str) -> str:
        return f"https://sso.test/login?state={state}"

    async def exchange_code(self, code: str, *, state: str | None = None) -> dict[str, Any]:
        assert state
        return {
            "access_token": f"oauth-{code}",
            "refresh_token": "refresh-before",
            "expires_in": 7200,
        }

    async def check_token(self, access_token: str) -> dict[str, Any]:
        self.checked.append(access_token)
        if self.omit_check_expiry:
            return {}
        return {"exp": self.check_expires_at or int(time.time()) + 7200}

    async def get_user_by_token(self, access_token: str) -> dict[str, Any]:
        # 门户提权校验（_refresh_portal_role）走 /user/get-by-token 原官网角色接口；
        # 返回与 get_permission_info 一致的非管理员身份（无 gkxUser → portal_is_admin=False）。
        return {"id": 139, "status": 0}

    async def get_permission_info(self, access_token: str) -> dict[str, Any]:
        return {
            "userInfo": {"id": 139, "username": "test", "nickname": "测试成员"},
            "allPermissions": {"roles": [], "permissions": ["overview:read"], "menus": []},
        }

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        self.refresh_count += 1
        if self.refresh_started is not None:
            self.refresh_started.set()
        if self.refresh_release is not None:
            await self.refresh_release.wait()
        if self.refresh_error is not None:
            raise self.refresh_error
        return {
            "access_token": "access-after",
            "refresh_token": "refresh-after",
            "expires_in": 7200,
        }

    async def logout(self, access_token: str) -> bool:
        self.revoked.append(access_token)
        return True


def recovery_settings(**changes: Any) -> AuthSettings:
    defaults = {
        "enabled": True,
        "client_id": "test-client",
        "client_secret": "test-secret",
        "session_backend": "memory",
        "session_cookie_name": "techkg_session",
        "portal_token_cookie_name": "portal_access_token",
        "portal_cookie_login_enabled": False,
        "session_ttl_seconds": 1800,
        "cookie_secure": False,
        "cookie_samesite": "lax",
        "cookie_path": "/",
        "frontend_url": "https://kg.test/bkg_zp",
        "bootstrap_first_admin": False,
        "initial_admin_user_ids": (),
    }
    return replace(AuthSettings.from_env(), **(defaults | changes))


async def stored_context(service: AuthService, **changes: Any) -> AuthContext:
    values = {
        "access_token": "access-before",
        "refresh_token": "refresh-before",
        "expires_at": int(time.time()) + 7200,
        "permission_info": await service.user_center.get_permission_info("access-before"),
        "session_id": "session-under-test",
        "token_source": "oauth",
    }
    context = AuthContext(**(values | changes))
    await service.store.set_json(
        f"{service.SESSION_KEY_PREFIX}{context.session_id}",
        context.to_record(),
        service.settings.session_ttl_seconds,
    )
    return context


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"refresh_token": "old-refresh"}, "oauth"),
        ({"refresh_token": ""}, "unknown"),
        ({"token_source": "portal"}, "portal"),
        ({"token_source": "bearer"}, "bearer"),
    ],
)
def test_token_source_survives_record_roundtrip(record: dict[str, Any], expected: str) -> None:
    context = AuthContext.from_record(record, session_id="existing")
    assert context.token_source == expected
    assert (
        AuthContext.from_record(context.to_record(), session_id="existing").token_source == expected
    )


async def test_active_session_survives_original_deadline_but_idle_session_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ManualClockStore()
    monkeypatch.setattr("service.auth.time.time", lambda: store.now)
    service = AuthService(recovery_settings(), store, RecoveryUserCenter())
    context = await stored_context(service)
    for _ in range(3):
        store.advance(1700)
        assert (await service.get_session(context.session_id)).session_id == context.session_id
    store.advance(1801)
    with pytest.raises(AuthenticationError, match="登录已过期"):
        await service.get_session(context.session_id)


async def test_idle_touch_does_not_overwrite_concurrently_rotated_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryJsonStore()
    service = AuthService(recovery_settings(), store, RecoveryUserCenter())
    context = await stored_context(service)
    key = f"{service.SESSION_KEY_PREFIX}{context.session_id}"
    original_touch = store.touch

    async def touch_after_rotation(touched_key: str, ttl_seconds: int) -> bool:
        updated = context.to_record() | {"access_token": "concurrently-rotated"}
        await store.replace_json(key, updated, ttl_seconds)
        return await original_touch(touched_key, ttl_seconds)

    monkeypatch.setattr(store, "touch", touch_after_rotation)
    await service.get_session(context.session_id)
    assert (await store.get_json(key))["access_token"] == "concurrently-rotated"


async def test_concurrent_expiry_refreshes_once() -> None:
    user_center = RecoveryUserCenter()
    user_center.refresh_started = asyncio.Event()
    user_center.refresh_release = asyncio.Event()
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await stored_context(service, expires_at=int(time.time()) + 10)
    requests = [asyncio.create_task(service.get_session(context.session_id)) for _ in range(12)]
    await user_center.refresh_started.wait()
    user_center.refresh_release.set()
    results = await asyncio.gather(*requests)
    assert user_center.refresh_count == 1
    assert {result.access_token for result in results} == {"access-after"}
    assert (await service.get_session(context.session_id)).refresh_token == "refresh-after"


async def test_delayed_refresh_uses_newer_record_instead_of_rotating_again() -> None:
    user_center = RecoveryUserCenter()
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await stored_context(service, expires_at=int(time.time()) + 10)
    await service.refresh_session(context.session_id, context=context)
    result = await service.refresh_session(context.session_id, context=context)
    assert result.access_token == "access-after"
    assert user_center.refresh_count == 1


async def test_logout_during_refresh_cannot_recreate_deleted_session() -> None:
    user_center = RecoveryUserCenter()
    user_center.refresh_started = asyncio.Event()
    user_center.refresh_release = asyncio.Event()
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await stored_context(service, expires_at=int(time.time()) + 10)
    pending = asyncio.create_task(service.get_session(context.session_id))
    await user_center.refresh_started.wait()
    logged_out, revoked = await service.logout_session(context.session_id)
    assert logged_out is not None and revoked
    user_center.refresh_release.set()
    with pytest.raises(AuthenticationError, match="登录已过期"):
        await pending
    assert await service.store.get_json(f"{service.SESSION_KEY_PREFIX}{context.session_id}") is None


async def test_transient_refresh_failure_keeps_session_for_retry() -> None:
    user_center = RecoveryUserCenter()
    user_center.refresh_error = UserCenterError("暂时不可用", status_code=503)
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await stored_context(service, expires_at=int(time.time()) + 10)
    with pytest.raises(AuthenticationError) as error:
        await service.get_session(context.session_id)
    assert error.value.status_code == 503
    assert await service.store.get_json(f"{service.SESSION_KEY_PREFIX}{context.session_id}")
    user_center.refresh_error = None
    assert (await service.get_session(context.session_id)).access_token == "access-after"


@pytest.mark.parametrize(("missing_expiry", "status_code"), [(False, 401), (True, 502)])
async def test_portal_refresh_rejects_invalid_success_expiry(
    missing_expiry: bool, status_code: int
) -> None:
    user_center = RecoveryUserCenter()
    user_center.check_expires_at = int(time.time()) - 1
    user_center.omit_check_expiry = missing_expiry
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await stored_context(
        service, expires_at=int(time.time()) + 10, refresh_token="", token_source="portal"
    )
    with pytest.raises(AuthenticationError) as error:
        await service.get_session(context.session_id)
    assert error.value.status_code == status_code
    record = await service.store.get_json(f"{service.SESSION_KEY_PREFIX}{context.session_id}")
    if missing_expiry:
        assert record is not None
        assert record["expires_at"] == context.expires_at
    else:
        assert record is None


@pytest.mark.parametrize(
    ("source", "revoked"), [("oauth", True), ("portal", False), ("unknown", False)]
)
async def test_logout_revokes_only_owned_token(source: str, revoked: bool) -> None:
    user_center = RecoveryUserCenter()
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await stored_context(service, token_source=source)
    _, actual = await service.logout_session(context.session_id)
    assert actual is revoked
    assert user_center.revoked == ([context.access_token] if revoked else [])
    assert await service.logout_session(context.session_id) == (None, False)


async def test_revoked_bearer_is_not_accepted_from_permission_cache() -> None:
    class RevokingUserCenter(RecoveryUserCenter):
        async def check_token(self, access_token: str) -> dict[str, Any]:
            checked = await super().check_token(access_token)
            if access_token in self.revoked:
                raise UserCenterError("访问令牌已撤销", status_code=401)
            return checked

    user_center = RevokingUserCenter()
    service = AuthService(recovery_settings(), MemoryJsonStore(), user_center)
    context = await service.resolve_bearer("vendor-token")
    assert (await service.resolve_bearer("vendor-token")).token_source == "bearer"
    assert user_center.checked == ["vendor-token"]
    assert await service.logout(context)
    with pytest.raises(AuthenticationError, match="已撤销"):
        await service.resolve_bearer("vendor-token")
    assert user_center.checked == ["vendor-token", "vendor-token"]
