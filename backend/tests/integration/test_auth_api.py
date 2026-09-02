from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from application.auth import AuthApplication, get_auth_application
from biz.dependencies.auth import require_authenticated_user
from biz.handler.auth import router as auth_router
from config.auth import AuthSettings
from infra.redis import MemoryJsonStore


class _FakeUserCenter:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings

    def build_login_url(self, state: str) -> str:
        return f"https://sso.test/uc/sso/login?state={state}"

    async def exchange_code(self, code: str, *, state: str | None = None) -> dict[str, Any]:
        assert state
        return {
            "access_token": f"access-{code}",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        }

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        return {
            "access_token": "access-refreshed",
            "refresh_token": refresh_token,
            "expires_in": 3600,
        }

    async def check_token(self, access_token: str) -> dict[str, Any]:
        return {"access_token": access_token, "exp": 4_102_444_800}

    async def get_permission_info(
        self,
        access_token: str,
        *,
        org_id: int | None = None,
        include_role_menu: bool = True,
    ) -> dict[str, Any]:
        return {
            "userInfo": {
                "id": 139,
                "username": "test",
                "nickname": "普通用户",
                "userType": 1,
            },
            "allPermissions": {
                "roles": [{"id": 1, "name": "管理员", "code": "admin", "type": 1}],
                "permissions": ["overview:read"],
                "menus": [
                    {
                        "id": 1,
                        "name": "系统管理",
                        "children": [{"id": 2, "name": "角色管理", "children": None}],
                    }
                ],
            },
            "appPermissions": {"roles": [], "permissions": [], "menus": []},
            "orgPermissions": {"roles": [], "permissions": None, "menus": None},
            "roleMenuList": [],
            "orgs": [],
        }

    async def logout(self, access_token: str) -> bool:
        return True


def _test_app() -> FastAPI:
    settings = replace(
        AuthSettings.from_env(),
        enabled=True,
        client_id="techkg",
        client_secret="secret",
        session_backend="memory",
        cookie_secure=False,
        cookie_path="/",
        frontend_url="https://kg.test/bkg_zp",
    )
    application = AuthApplication(
        settings=settings,
        store=MemoryJsonStore(),
        user_center=_FakeUserCenter(settings),
    )
    app = FastAPI()
    app.dependency_overrides[get_auth_application] = lambda: application
    app.include_router(auth_router, prefix="/api/v1")
    protected = APIRouter(dependencies=[Depends(require_authenticated_user)])

    @protected.get("/protected")
    async def protected_endpoint() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(protected, prefix="/api/v1")
    return app


def _portal_cookie_test_app() -> FastAPI:
    settings = replace(
        AuthSettings.from_env(),
        enabled=True,
        client_id="techkg",
        client_secret="secret",
        session_backend="memory",
        cookie_secure=False,
        cookie_path="/",
        portal_cookie_login_enabled=True,
        portal_token_cookie_name="access_token",
    )
    application = AuthApplication(
        settings=settings,
        store=MemoryJsonStore(),
        user_center=_FakeUserCenter(settings),
    )
    app = FastAPI()
    app.dependency_overrides[get_auth_application] = lambda: application
    app.include_router(auth_router, prefix="/api/v1")
    return app


async def test_browser_login_cookie_profile_and_logout_flow() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_test_app()),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        unauthorized = await client.get("/api/v1/protected")
        assert unauthorized.status_code == 401

        login = await client.get("/api/v1/auth/login-url", params={"next": "/schema"})
        state = parse_qs(urlparse(login.json()["data"]["url"]).query)["state"][0]
        assert client.cookies.get("techkg_session_oauth_state") == state
        callback = await client.get(
            "/api/v1/auth/callback",
            params={"code": "valid-code", "state": state},
        )

        assert callback.status_code == 302
        assert callback.headers["location"] == "https://kg.test/bkg_zp/#/schema"
        assert "HttpOnly" in callback.headers["set-cookie"]
        assert client.cookies.get("techkg_session_oauth_state") is None

        profile = await client.get("/api/v1/auth/me")
        protected = await client.get("/api/v1/protected")
        assert profile.json()["data"]["user"]["nickname"] == "普通用户"
        assert protected.json() == {"ok": True}

        security = await client.get("/api/v1/auth/security")
        logs = await client.get("/api/v1/auth/operation-logs")
        assert security.json()["data"]["passwordManagedBy"] == "统一用户中心"
        assert security.json()["data"]["passwordEditableHere"] is False
        assert logs.json()["data"]["total"] == 1
        assert logs.json()["data"]["items"][0]["action"] == "登录平台"

        refreshed = await client.post("/api/v1/auth/refresh")
        refreshed_logs = await client.get(
            "/api/v1/auth/operation-logs", params={"category": "安全"}
        )
        assert refreshed.status_code == 200
        assert refreshed_logs.json()["data"]["items"][0]["action"] == "刷新登录会话"

        logged_out = await client.post("/api/v1/auth/logout")
        assert logged_out.json()["data"]["remoteRevoked"] is True
        assert (await client.get("/api/v1/protected")).status_code == 401


async def test_vendor_bearer_token_can_call_protected_api() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_test_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer vendor-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_oauth_callback_rejects_state_from_another_browser() -> None:
    app = _test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as initiating_client:
        login = await initiating_client.get("/api/v1/auth/login-url")
        state = parse_qs(urlparse(login.json()["data"]["url"]).query)["state"][0]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as another_client:
            callback = await another_client.get(
                "/api/v1/auth/callback",
                params={"code": "valid-code", "state": state},
            )

        assert callback.status_code == 302
        assert "/#/login?" in callback.headers["location"]
        assert "techkg_session=" not in callback.headers.get("set-cookie", "")


async def test_v21_portal_cookie_is_exchanged_for_local_session() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_portal_cookie_test_app()),
        base_url="http://test",
    ) as client:
        client.cookies.set("access_token", "portal-access-token", domain="test.local")
        client.cookies.set("techkg_session", "expired-local-session", domain="test.local")
        first = await client.get("/api/v1/auth/me")

        assert first.status_code == 200
        assert first.json()["data"]["user"]["nickname"] == "普通用户"
        # jar 里同时存在手工预置的过期 session 与新 session，httpx 新版对
        # 同名 cookie 的 get 会抛 CookieConflict —— 以 set-cookie 头为准断言
        assert "techkg_session=" in first.headers["set-cookie"]
        assert "HttpOnly" in first.headers["set-cookie"]
        assert "portal-access-token" not in first.headers["set-cookie"]

        logs = await client.get("/api/v1/auth/operation-logs")
        assert logs.json()["data"]["items"][0]["action"] == "复用门户登录态"

        refreshed = await client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200

        client.cookies.delete("access_token")
        second = await client.get("/api/v1/auth/me")

    assert second.status_code == 200


async def test_portal_cookie_login_is_disabled_by_default() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_test_app()),
        base_url="http://test",
    ) as client:
        client.cookies.set("access_token", "portal-access-token")
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401


async def test_operation_logs_reject_invalid_pagination() -> None:
    app = _test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (
            await client.get(
                "/api/v1/auth/operation-logs",
                params={"page": 0},
                headers={"Authorization": "Bearer vendor-token"},
            )
        ).status_code == 422
        assert (
            await client.get(
                "/api/v1/auth/operation-logs",
                params={"pageSize": 101},
                headers={"Authorization": "Bearer vendor-token"},
            )
        ).status_code == 422


async def test_operation_logs_invalid_pagination_uses_global_api_envelope() -> None:
    from main import app as main_app

    transport = ASGITransport(app=main_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/operation-logs",
            params={"page": 0, "pageSize": 101},
        )

    assert response.status_code == 200
    assert response.json()["code"] == 422
    assert response.json()["success"] is False
