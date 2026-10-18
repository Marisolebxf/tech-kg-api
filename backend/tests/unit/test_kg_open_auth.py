"""所有新增路由共用机器/用户双通道，错误密钥不回退用户身份。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.auth import get_auth_application
from biz.dependencies import kg_open_auth, project_relation_auth
from biz.handler import kg_open
from infra.workflow_mysql import get_workflow_session
from service.external_api_client import KG_OPEN_READ, ExternalClientError, ExternalClientIdentity


@pytest.fixture
async def auth_client(monkeypatch):
    app = FastAPI()
    app.include_router(kg_open.router, prefix="/api/v1")
    application = SimpleNamespace(
        settings=SimpleNamespace(
            enabled=True,
            session_cookie_name="techkg_session",
            portal_cookie_login_enabled=False,
            business_only_user_ids=(),
        ),
        resolve_bearer=AsyncMock(),
        platform_actor=Mock(),
    )
    app.dependency_overrides[get_auth_application] = lambda: application
    app.dependency_overrides[get_workflow_session] = lambda: object()
    authenticate = Mock(return_value=ExternalClientIdentity("partner"))
    monkeypatch.setattr(kg_open_auth, "authenticate_client", authenticate)
    monkeypatch.setattr(project_relation_auth, "_ensure_external_shared_space", lambda: None)
    monkeypatch.setattr(kg_open, "_catalog", lambda *a: {"entityTypes": [], "relationTypes": []})
    monkeypatch.setattr(
        kg_open, "_get_client", lambda space: SimpleNamespace(stats_snapshot=lambda: {})
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, authenticate, application


async def test_machine_auth_checks_new_scope_without_user_center(auth_client):
    client, authenticate, application = auth_client
    result = await client.get(
        "/api/v1/kg-open/schema", headers={"X-Client-Id": "partner", "X-API-Key": "key"}
    )
    assert result.status_code == 200
    authenticate.assert_called_once_with("partner", "key", required_scope=KG_OPEN_READ)
    application.resolve_bearer.assert_not_called()
    application.platform_actor.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 503])
async def test_bad_machine_credentials_never_fall_back(auth_client, status):
    client, authenticate, application = auth_client
    authenticate.side_effect = ExternalClientError("拒绝", status)
    result = await client.get(
        "/api/v1/kg-open/schema",
        headers={"X-Client-Id": "partner", "X-API-Key": "bad", "Authorization": "Bearer valid"},
    )
    assert result.status_code == status
    application.resolve_bearer.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Client-Id": "partner"},
        {"X-API-Key": "key"},
        [("X-Client-Id", "a"), ("X-Client-Id", "b"), ("X-API-Key", "key")],
    ],
)
async def test_missing_or_duplicate_headers_rejected(auth_client, headers):
    client, authenticate, _ = auth_client
    assert (await client.get("/api/v1/kg-open/schema", headers=headers)).status_code == 401
    authenticate.assert_not_called()


async def test_anonymous_rejected(auth_client):
    client, authenticate, _ = auth_client
    assert (await client.get("/api/v1/kg-open/schema")).status_code == 401
    authenticate.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/schema",
        "/entity-types/Paper/entities",
        "/relation-types/AUTHORED_BY/edges",
    ],
)
async def test_every_endpoint_has_auth_guard(auth_client, path):
    client, authenticate, _ = auth_client
    response = await client.get("/api/v1/kg-open" + path)
    assert response.status_code == 401
    authenticate.assert_not_called()
