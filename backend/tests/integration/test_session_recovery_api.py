"""浏览器 Cookie/退出/重新认证回归，使用独立 ASGI 应用和模拟用户中心。"""

import hashlib
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Depends, FastAPI, HTTPException, Response
from httpx import ASGITransport, AsyncClient

from application.auth import AuthApplication, get_auth_application
from biz.auth_cookies import AuthSessionMiddleware
from biz.dependencies.auth import require_authenticated_user
from biz.handler.auth import router as auth_router
from tests.unit.test_session_recovery import (
    ManualClockStore,
    RecoveryUserCenter,
    recovery_settings,
    stored_context,
)

COOKIE = "techkg_session"
MARKER = f"{COOKIE}_portal_logout"


def make_app(monkeypatch: pytest.MonkeyPatch, **changes: Any):
    store = ManualClockStore()
    monkeypatch.setattr("service.auth.time.time", lambda: store.now)
    user_center = RecoveryUserCenter()
    application = AuthApplication(
        settings=recovery_settings(**changes), store=store, user_center=user_center
    )
    # 本组只验证认证生命周期，成员库权限由原有测试独立覆盖。
    monkeypatch.setattr(application, "profile", application.service.profile)
    app = FastAPI()
    app.add_middleware(AuthSessionMiddleware)
    app.dependency_overrides[get_auth_application] = lambda: application
    app.include_router(auth_router, prefix="/api/v1")

    @app.get("/api/v1/direct", dependencies=[Depends(require_authenticated_user)])
    async def direct_response():
        return Response(content='{"ok":true}', media_type="application/json")

    @app.get("/api/v1/forbidden", dependencies=[Depends(require_authenticated_user)])
    async def forbidden_response():
        raise HTTPException(status_code=403, detail="无权限")

    return app, application, store, user_center


def cookies_from(response) -> SimpleCookie:
    parsed = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        parsed.load(header)
    return parsed


async def oauth_login(client: AsyncClient):
    login = await client.get("/api/v1/auth/login-url", params={"next": "/overview"})
    assert login.status_code == 200
    state = parse_qs(urlparse(login.json()["data"]["url"]).query)["state"][0]
    return await client.get("/api/v1/auth/callback", params={"code": "test", "state": state})


async def test_cookie_and_server_both_slide_past_original_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, application, store, _ = make_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        callback = await oauth_login(client)
        assert callback.status_code == 302
        session_id = client.cookies.get(COOKIE)
        original_expiry = next(
            cookie.expires for cookie in client.cookies.jar if cookie.name == COOKIE
        )
        for _ in range(3):
            store.advance(1700)
            response = await client.get("/api/v1/direct")
            assert response.status_code == 200
            cookie = cookies_from(response)[COOKIE]
            assert cookie.value == session_id
            assert cookie["max-age"] == "1800"
            assert cookie["httponly"]
            assert response.headers["cache-control"] == "no-store"
        assert store.now > original_expiry
        assert (
            next(cookie.expires for cookie in client.cookies.jar if cookie.name == COOKIE)
            > store.now
        )
        store.advance(1801)
        idle_response = await client.get("/api/v1/auth/me")
        assert idle_response.status_code == 401
        assert COOKIE not in cookies_from(idle_response)
        assert await store.get_json(f"{application.service.SESSION_KEY_PREFIX}{session_id}") is None


@pytest.mark.parametrize(("path", "status"), [("/me", 401), ("/callback", 302)])
async def test_auth_failures_and_redirects_are_never_cached(
    monkeypatch: pytest.MonkeyPatch, path: str, status: int
) -> None:
    app, _, _, _ = make_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        response = await client.get(f"/api/v1/auth{path}")
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"


async def test_prefixed_callback_error_redirect_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _, _ = make_app(monkeypatch, cookie_path="/bkg_zp")
    async with AsyncClient(
        transport=ASGITransport(app=app, root_path="/bkg_zp"),
        base_url="http://test.local/bkg_zp",
    ) as client:
        response = await client.get("/api/v1/auth/callback")
        assert response.status_code == 302
        assert response.headers["cache-control"] == "no-store"
        assert cookies_from(response)[f"{COOKIE}_oauth_state"]["path"] == "/bkg_zp"


@pytest.mark.parametrize("session_id", [None, "already-expired"])
async def test_logout_without_live_session_never_reauthenticates(
    monkeypatch: pytest.MonkeyPatch, session_id: str | None
) -> None:
    app, _, _, user_center = make_app(monkeypatch, portal_cookie_login_enabled=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set("portal_access_token", "portal-before", domain="test.local")
        if session_id:
            client.cookies.set(COOKIE, session_id, domain="test.local")
        for _ in range(2):
            response = await client.post("/api/v1/auth/logout")
            assert response.status_code == 200
            assert response.json()["data"]["loggedOut"]
            assert cookies_from(response)[COOKIE]["max-age"] == "0"
        assert user_center.checked == []
        assert user_center.revoked == []
        assert user_center.refresh_count == 0
        assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_portal_logout_blocks_old_token_and_late_session_but_allows_new_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, application, _, user_center = make_app(monkeypatch, portal_cookie_login_enabled=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set("portal_access_token", "portal-before", domain="test.local")
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        assert response.json()["data"]["remoteRevoked"] is False
        marker = cookies_from(response)[MARKER]
        assert marker.value == hashlib.sha256(b"portal-before").hexdigest()
        assert marker["httponly"]
        assert "portal-before" not in response.headers.get("set-cookie", "")
        assert user_center.revoked == []
        assert client.cookies.get("portal_access_token") == "portal-before"
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        # 模拟退出前启动的 SSO 请求随后返回另一份同 token 本地会话。
        late_context = await application.create_session_from_access_token("portal-before")
        client.cookies.set(COOKIE, late_context.session_id, domain="test.local")
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        client.cookies.set("portal_access_token", "portal-after", domain="test.local")
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        assert client.cookies.get(COOKIE) != late_context.session_id


async def test_expired_access_token_does_not_prevent_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, application, store, user_center = make_app(monkeypatch)
    context = await stored_context(application.service, expires_at=int(store.now) - 10)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(COOKIE, context.session_id, domain="test.local")
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        assert user_center.refresh_count == 0
        assert user_center.checked == []
        assert user_center.revoked == [context.access_token]
        assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_oauth_callback_clears_portal_logout_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _, _, user_center = make_app(monkeypatch, portal_cookie_login_enabled=True)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set("portal_access_token", "portal-before", domain="test.local")
        await client.post("/api/v1/auth/logout")
        assert client.cookies.get(MARKER)
        callback = await oauth_login(client)
        assert callback.status_code == 302
        # 前端已切换 createWebHistory(appBase)，OAuth 回跳不再拼接 hash 前缀。
        assert callback.headers["location"] == "https://kg.test/bkg_zp/overview"
        assert callback.headers["cache-control"] == "no-store"
        assert client.cookies.get(MARKER) is None
        assert (await client.get("/api/v1/auth/me")).status_code == 200
        assert user_center.checked == []


async def test_store_failure_returns_503_and_clears_browser_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, store, user_center = make_app(monkeypatch, portal_cookie_login_enabled=True)

    async def unavailable(key: str):
        raise OSError("isolated unavailable store")

    monkeypatch.setattr(store, "pop_json", unavailable)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        client.cookies.set(COOKIE, "stale-session", domain="test.local")
        client.cookies.set("portal_access_token", "portal-before", domain="test.local")
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert cookies_from(response)[COOKIE]["max-age"] == "0"
        assert client.cookies.get(COOKIE) is None
        assert client.cookies.get(MARKER)
        assert user_center.checked == []
        assert user_center.revoked == []


async def test_cookie_scope_is_preserved_on_renewal_and_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, application, _, _ = make_app(
        monkeypatch, cookie_path="/bkg_zp", cookie_secure=True, cookie_samesite="none"
    )
    context = await stored_context(application.service)
    # ingress 会移除 /bkg_zp 前缀；直接发送它转发的 Cookie 来检查后端返回的路径属性。
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test.local"
    ) as client:
        for method, endpoint in [("GET", "/api/v1/direct"), ("POST", "/api/v1/auth/logout")]:
            response = await client.request(
                method, endpoint, headers={"Cookie": f"{COOKIE}={context.session_id}"}
            )
            assert response.status_code == 200
            cookie = cookies_from(response)[COOKIE]
            assert cookie["path"] == "/bkg_zp"
            assert cookie["secure"]
            assert cookie["httponly"]
            assert cookie["samesite"] == "none"


async def test_forbidden_response_does_not_reissue_login_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _, _ = make_app(monkeypatch)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.local"
    ) as client:
        await oauth_login(client)
        response = await client.get("/api/v1/forbidden")
        assert response.status_code == 403
        assert COOKIE not in cookies_from(response)
