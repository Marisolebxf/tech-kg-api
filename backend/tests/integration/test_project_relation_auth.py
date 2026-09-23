from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.auth import get_auth_application
from biz.dependencies import project_relation_auth as auth
from biz.dependencies.auth import require_authenticated_user
from biz.handler import project_relation as handler
from biz.schemas.project_relation import ProjectRelationPage
from service.auth import AuthenticationError
from service.external_api_client import ExternalClientError, ExternalClientIdentity

PATH = "/api/v1/kg-service/project-relations/query"


@pytest.fixture
async def auth_client(monkeypatch):
    app = FastAPI()
    app.include_router(handler.router, prefix="/api/v1")
    application = SimpleNamespace(
        settings=SimpleNamespace(
            enabled=True,
            session_cookie_name="techkg_session",
            portal_cookie_login_enabled=False,
            business_only_user_ids=(),
        ),
        resolve_bearer=AsyncMock(return_value=object()),
        get_session=AsyncMock(return_value=SimpleNamespace(token_source="oauth")),
        platform_actor=Mock(return_value=object()),
    )
    app.dependency_overrides[get_auth_application] = lambda: application
    authenticate = Mock(return_value=ExternalClientIdentity("partner-a"))
    monkeypatch.setattr(auth, "authenticate_client", authenticate)
    monkeypatch.setattr(handler, "get_trs_graph_client", lambda: object())
    monkeypatch.setattr(
        handler.ProjectRelationApplication,
        "query",
        lambda self, body: ProjectRelationPage(pageSize=body.pageSize),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, authenticate, application


async def test_api_key_succeeds_without_user_auth(auth_client):
    client, authenticate, application = auth_client
    response = await client.post(
        PATH, json={}, headers={"X-Client-Id": "partner-a", "X-API-Key": "test-key"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    authenticate.assert_called_once_with("partner-a", "test-key")
    application.resolve_bearer.assert_not_called()
    application.platform_actor.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [
        [("X-Client-Id", "partner-a")],
        [("X-API-Key", "key")],
        [("X-Client-Id", "a"), ("X-Client-Id", "b"), ("X-API-Key", "key")],
        [("X-Client-Id", "a"), ("X-API-Key", "key"), ("X-API-Key", "key2")],
    ],
)
async def test_incomplete_or_duplicate_headers_fail(auth_client, headers):
    client, authenticate, application = auth_client
    response = await client.post(PATH, json={}, headers=headers)
    assert response.status_code == 401
    authenticate.assert_not_called()
    application.resolve_bearer.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 503])
async def test_failed_api_key_never_falls_back_to_bearer(auth_client, status):
    client, authenticate, application = auth_client
    authenticate.side_effect = ExternalClientError("认证失败", status)
    response = await client.post(
        PATH,
        json={},
        headers={
            "X-Client-Id": "partner-a",
            "X-API-Key": "wrong-key",
            "Authorization": "Bearer valid-user-token",
        },
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    application.resolve_bearer.assert_not_called()


async def test_without_api_key_preserves_user_bearer_auth(auth_client):
    client, authenticate, application = auth_client
    response = await client.post(PATH, json={}, headers={"Authorization": "Bearer user-token"})
    assert response.status_code == 200
    authenticate.assert_not_called()
    application.resolve_bearer.assert_awaited_once_with("user-token")
    application.platform_actor.assert_called_once()


async def test_without_api_key_preserves_session_cookie(auth_client):
    client, authenticate, application = auth_client
    client.cookies.set("techkg_session", "existing-session")
    response = await client.post(PATH, json={})
    assert response.status_code == 200
    authenticate.assert_not_called()
    application.get_session.assert_awaited_once_with("existing-session")


async def test_anonymous_and_invalid_bearer_still_rejected(auth_client):
    client, authenticate, application = auth_client
    assert (await client.post(PATH, json={})).status_code == 401
    application.resolve_bearer.side_effect = AuthenticationError("访问令牌不存在")
    response = await client.post(PATH, json={}, headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    authenticate.assert_not_called()


async def test_real_app_validation_envelope(monkeypatch):
    from main import app

    monkeypatch.setitem(
        app.dependency_overrides,
        auth.require_project_relation_identity,
        lambda: ExternalClientIdentity("partner-a"),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(PATH, json={"pageSize": 201})
    assert response.status_code == 200
    assert response.json()["code"] == 422
    assert response.json()["success"] is False


def test_registered_route_has_machine_auth_without_global_user_guard():
    from biz.router.register import register_routers

    app = FastAPI()
    register_routers(app)
    route = next(route for route in app.routes if getattr(route, "path", None) == PATH)

    def calls(dependant):
        return [dependant.call] + [
            call for child in dependant.dependencies for call in calls(child)
        ]

    dependencies = calls(route.dependant)
    assert auth.require_project_relation_identity in dependencies
    assert require_authenticated_user not in dependencies


async def test_business_user_cannot_bypass_default_space_authorization(auth_client, monkeypatch):
    from fastapi import HTTPException

    client, _, _ = auth_client
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")

    def deny(*args):
        raise HTTPException(403, "无权访问默认私有空间")

    monkeypatch.setattr("service.business_access_control.ensure_space_access", deny)
    response = await client.post(PATH, json={}, headers={"Authorization": "Bearer user-token"})
    assert response.status_code == 403


@pytest.mark.parametrize("shared", [False, True, None])
async def test_machine_key_requires_explicit_shared_production(auth_client, monkeypatch, shared):
    from contextlib import contextmanager

    client, _, application = auth_client
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")

    @contextmanager
    def session():
        yield SimpleNamespace(
            get=lambda *args: (
                None if shared is None else SimpleNamespace(is_shared_production=shared)
            )
        )

    monkeypatch.setattr("infra.mysql.session_scope", session)
    response = await client.post(
        PATH, json={}, headers={"X-Client-Id": "partner-a", "X-API-Key": "test-key"}
    )
    assert response.status_code == (200 if shared else 403)
    application.platform_actor.assert_not_called()
