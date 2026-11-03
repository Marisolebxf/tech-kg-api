"""门户主导登录的入口和浏览器会话，使用独立 ASGI 应用。"""

import time
from dataclasses import replace
from http.cookies import SimpleCookie
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.auth import AuthApplication, get_auth_application
from biz.auth_cookies import AuthSessionMiddleware
from biz.handler.auth import router as auth_router
from config.auth import AuthSettings
from infra.redis import MemoryJsonStore
from service.auth import AuthContext
from tests.unit.test_session_recovery import RecoveryUserCenter

COOKIE = "techkg_session"
PORTAL_COOKIE = "portal_access_token"
MARKER = f"{COOKIE}_portal_logout"


class PortalUserCenter(RecoveryUserCenter):
    def build_login_url(self, state: str) -> str:
        raise AssertionError("门户模式不能发起本系统 OAuth 登录")

    async def exchange_code(self, code: str, *, state: str | None = None) -> dict[str, Any]:
        raise AssertionError("门户模式不能交换 OAuth 授权码")

    async def get_permission_info(self, access_token: str) -> dict[str, Any]:
        user_id = 202 if access_token == "portal-after" else 101
        return {
            "userInfo": {"id": user_id, "username": f"user-{user_id}", "nickname": "测试用户"},
            "allPermissions": {"roles": [], "permissions": ["overview:read"], "menus": []},
        }

    async def get_user_by_token(self, access_token: str) -> dict[str, Any]:
        return {"id": 202 if access_token == "portal-after" else 101, "status": 0}


def make_portal_app(monkeypatch: pytest.MonkeyPatch, **changes: Any):
    settings = replace(
        AuthSettings.from_env(),
        **(
            {
                "enabled": True,
                "login_mode": "portal",
                "portal_login_url": "/portal/",
                "portal_cookie_login_enabled": True,
                "portal_token_cookie_name": PORTAL_COOKIE,
                "session_cookie_name": COOKIE,
                "session_backend": "memory",
                "cookie_secure": False,
                "cookie_path": "/",
                "cookie_samesite": "lax",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "business_only_user_ids": (),
            }
            | changes
        ),
    )
    store = MemoryJsonStore()
    user_center = PortalUserCenter()
    application = AuthApplication(settings=settings, store=store, user_center=user_center)
    # 只测试认证链路，不访问独立的业务成员数据库。
    monkeypatch.setattr(application, "profile", application.service.profile)
    app = FastAPI()
    app.add_middleware(AuthSessionMiddleware)
    app.dependency_overrides[get_auth_application] = lambda: application
    app.include_router(auth_router, prefix="/api/v1")
    return app, application, store, user_center


def response_cookies(response) -> SimpleCookie:
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)
    return cookies


@pytest.mark.parametrize("entry", ["/portal/", "https://portal.example.test/portal/?view=home"])
async def test_portal_login_url_does_not_start_oauth_or_access_session_store(
    monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    app, _, store, _ = make_portal_app(monkeypatch, portal_login_url=entry)

    async def unexpected_store_access(*args, **kwargs):
        raise AssertionError("门户登录入口不应读写 OAuth state 或会话存储")

    for method in ("get_json", "set_json", "pop_json"):
        monkeypatch.setattr(store, method, unexpected_store_access)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(MARKER, "previous-logout", domain="test.local")
        response = await client.get(
            "/api/v1/auth/login-url", params={"next": "//untrusted.example.test/path"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["url"] == entry
        assert response.json()["data"]["mode"] == "portal"
        assert response.headers["cache-control"] == "no-store"
        assert response_cookies(response)[MARKER]["max-age"] == "0"
        assert f"{COOKIE}_oauth_state" not in response_cookies(response)
        assert client.cookies.get(MARKER) is None


@pytest.mark.parametrize("mode", ["portal", "oauth"])
async def test_login_config_is_read_only(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    app, _, store, _ = make_portal_app(monkeypatch, login_mode=mode)

    async def unexpected_store_access(*args, **kwargs):
        raise AssertionError("预加载登录方式不能访问会话或 OAuth state")

    for method in ("get_json", "set_json", "pop_json"):
        monkeypatch.setattr(store, method, unexpected_store_access)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(MARKER, "previous-logout", domain="test.local")
        response = await client.get("/api/v1/auth/login-config")
        assert response.status_code == 200
        assert response.json()["data"] == {"mode": mode}
        assert response.headers["cache-control"] == "no-store"
        assert "set-cookie" not in response.headers
        assert client.cookies.get(MARKER) == "previous-logout"


@pytest.mark.parametrize(
    "changes", [{"portal_login_url": ""}, {"portal_cookie_login_enabled": False}]
)
async def test_incomplete_portal_configuration_fails_without_oauth_fallback(
    monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any]
) -> None:
    app, _, _, _ = make_portal_app(monkeypatch, **changes)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        response = await client.get("/api/v1/auth/login-url")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert f"{COOKIE}_oauth_state" not in response_cookies(response)


async def test_portal_mode_rejects_oauth_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _, _, _ = make_portal_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        response = await client.get(
            "/api/v1/auth/callback", params={"code": "unused", "state": "unused"}
        )
    assert response.status_code == 404
    assert COOKIE not in response_cookies(response)


async def test_explicit_portal_login_unblocks_same_shared_token_after_local_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _, user_center = make_portal_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(PORTAL_COOKIE, "portal-before", domain="test.local")
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        assert logout.json()["data"]["remoteRevoked"] is False
        assert client.cookies.get(MARKER)
        assert client.cookies.get(PORTAL_COOKIE) == "portal-before"
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        assert client.cookies.get(MARKER)
        login = await client.get("/api/v1/auth/login-url")
        assert login.status_code == 200
        assert client.cookies.get(MARKER) is None
        assert (await client.get("/api/v1/auth/me")).status_code == 200
    assert user_center.revoked == []


async def test_portal_cookie_account_switch_replaces_old_local_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _, user_center = make_portal_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(PORTAL_COOKIE, "portal-before", domain="test.local")
        first = await client.get("/api/v1/auth/me")
        assert first.status_code == 200
        assert str(first.json()["data"]["user"]["id"]) == "101"
        old_session = client.cookies.get(COOKIE)
        client.cookies.set(PORTAL_COOKIE, "portal-after", domain="test.local")
        second = await client.get("/api/v1/auth/me")
        assert second.status_code == 200
        assert str(second.json()["data"]["user"]["id"]) == "202"
        assert client.cookies.get(COOKIE) != old_session
        assert "portal-after" not in second.headers.get("set-cookie", "")
    assert user_center.checked == ["portal-before", "portal-after"]


async def test_missing_portal_cookie_rejects_an_existing_local_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _, _ = make_portal_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(PORTAL_COOKIE, "portal-before", domain="test.local")
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        assert client.cookies.get(COOKIE)
        client.cookies.delete(PORTAL_COOKIE)
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("source", ["oauth", "unknown"])
async def test_portal_mode_revalidates_non_portal_sessions(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    app, application, store, user_center = make_portal_app(monkeypatch)
    context = AuthContext(
        access_token="portal-before",
        refresh_token="legacy-refresh" if source == "oauth" else "",
        permission_info=await user_center.get_permission_info("portal-before"),
        expires_at=int(time.time()) + 7200,
        session_id="legacy-session",
        token_source=source,
    )
    await store.set_json(
        f"{application.service.SESSION_KEY_PREFIX}{context.session_id}",
        context.to_record(),
        1800,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(COOKIE, context.session_id, domain="test.local")
        client.cookies.set(PORTAL_COOKIE, "portal-before", domain="test.local")
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert client.cookies.get(COOKIE) != context.session_id
    assert user_center.checked == ["portal-before"]
    assert user_center.refresh_count == 0


async def test_portal_exchange_sets_session_cookie_on_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门户兑换出的新会话在非 2xx 响应上也必须下发 Cookie。

    回归：中间件原先仅在 status<400 时写回会话 Cookie——静默重建发生在
    409/5xx 业务响应上时 Set-Cookie 被吞，浏览器持续丢会话、反复静默重建
    （2026-10-27 人工审核跳登录排查）。
    """
    from fastapi import HTTPException

    from biz.dependencies.auth import CurrentUser

    app, _, _, _ = make_portal_app(monkeypatch)

    @app.get("/api/v1/_test/conflict")
    async def _conflict(user: CurrentUser) -> None:
        raise HTTPException(status_code=409, detail="业务冲突")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(PORTAL_COOKIE, "portal-before", domain="test.local")
        response = await client.get("/api/v1/_test/conflict")
    assert response.status_code == 409
    cookies = response_cookies(response)
    assert COOKIE in cookies, "非 2xx 响应也必须下发门户兑换出的新会话 Cookie"
