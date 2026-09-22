"""Account scope is enforced on all credentials and only trusted internal graph calls."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI

from application.auth import AuthApplication, get_auth_application
from biz.dependencies.auth import require_authenticated_user
from biz.schemas.auth import AuthProfile, UserProfile
from config.auth import AuthSettings
from service.business_access import business_graph_app
from service.platform_access import PlatformActor

BUSINESS_ENDPOINTS = [
    "/kg-construction/expert-direct-relations/query",
    "/kg-construction/expert-indirect-relations/demo/structured-result",
    "/kg-construction/expert-cooperation-achievements/query",
    "/kg-service/expert-colleague-relation",
    "/kg-construction/expert-alumni-relations/query",
    "/kg-construction/expert-paper-cooperation-relations/structured-result",
    "/kg-service/key-enterprise-relation",
    "/kg-service/industry-node-top-events",
    "/kg-construction/industry-chain-panorama/query",
]


def make_app(*, restricted=True, user_id="limited", portal=False):
    settings = replace(
        AuthSettings.from_env(),
        enabled=True,
        business_only_user_ids=("limited",),
        portal_cookie_login_enabled=portal,
    )
    context = SimpleNamespace(token_source="oauth", access_token="token", session_id="session")
    application = SimpleNamespace(
        settings=settings,
        service=SimpleNamespace(
            profile=lambda _: SimpleNamespace(
                user=SimpleNamespace(id=user_id if restricted else "other")
            )
        ),
        resolve_bearer=AsyncMock(return_value=context),
        get_session=AsyncMock(return_value=context),
        create_session_from_access_token=AsyncMock(return_value=context),
        record_operation=AsyncMock(),
    )
    app = FastAPI()
    app.dependency_overrides[get_auth_application] = lambda: application

    async def endpoint():
        return {"ok": True}

    for path, methods in [
        ("/auth/me", ["GET"]),
        ("/auth/refresh", ["POST"]),
        ("/graph-search/spaces", ["GET"]),
        ("/graph-search/nodes/{node_id:path}", ["GET"]),
        ("/graph-search/subgraph/{node_id:path}", ["GET"]),
        ("/graph-search/paths/search", ["POST"]),
        ("/entity-search/entities", ["GET"]),
        ("/platform-overview", ["GET"]),
        ("/admin/members/limited/admin", ["PUT"]),
        ("/kg-construction/expert-direct-relations/query", ["POST", "DELETE"]),
        ("/kg-construction/expert-direct-relations/query-extra", ["POST"]),
    ]:
        app.add_api_route(
            "/api/v1" + path,
            endpoint,
            methods=methods,
            dependencies=[Depends(require_authenticated_user)],
        )
    for path in BUSINESS_ENDPOINTS[1:]:
        app.add_api_route(
            "/api/v1" + path,
            endpoint,
            methods=["POST"],
            dependencies=[Depends(require_authenticated_user)],
        )
    return app, settings


@pytest.mark.parametrize("path", BUSINESS_ENDPOINTS)
async def test_all_nine_business_queries_remain_accessible(path):
    app, _ = make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer token"},
    ) as client:
        assert (await client.post("/api/v1" + path)).status_code == 200


@pytest.mark.parametrize("credential", ["bearer", "session", "portal"])
async def test_scope_applies_to_all_authenticated_credentials(credential):
    app, settings = make_app(portal=credential == "portal")
    headers = {"Authorization": "Bearer token"} if credential == "bearer" else {}
    cookies = {}
    if credential != "bearer":
        cookies[
            settings.session_cookie_name
            if credential == "session"
            else settings.portal_token_cookie_name
        ] = "token"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
        cookies=cookies,
    ) as client:
        for path in ["/auth/me", "/graph-search/spaces"]:
            assert (await client.get("/api/v1" + path)).status_code == 200
        assert (
            await client.post("/api/v1/kg-construction/expert-direct-relations/query")
        ).status_code == 200
        for path in [
            "/entity-search/entities",
            "/platform-overview",
            "/graph-search/nodes/person_x",
        ]:
            assert (await client.get("/api/v1" + path)).status_code == 403
        assert (await client.put("/api/v1/admin/members/limited/admin")).status_code == 403
        assert (
            await client.delete("/api/v1/kg-construction/expert-direct-relations/query")
        ).status_code == 403
        assert (
            await client.post("/api/v1/kg-construction/expert-direct-relations/query-extra")
        ).status_code == 403


async def test_other_user_access_is_unchanged():
    app, _ = make_app(restricted=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer token"},
    ) as client:
        assert (await client.get("/api/v1/entity-search/entities")).status_code == 200


async def test_internal_business_queries_work_without_exposing_general_graph_api():
    app, _ = make_app()
    for internal in [False, True]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=business_graph_app(app) if internal else app),
            base_url="http://test",
            headers={"Authorization": "Bearer token", "techkg.business_graph_call": "true"},
        ) as client:
            assert (await client.get("/api/v1/graph-search/nodes/person_x")).status_code == (
                200 if internal else 403
            )
            assert (await client.post("/api/v1/graph-search/paths/search")).status_code == (
                200 if internal else 403
            )
            assert (await client.get("/api/v1/entity-search/entities")).status_code == 403


def test_config_defaults_and_profile_admin_cap(monkeypatch):
    monkeypatch.delenv("PLATFORM_BUSINESS_ONLY_USER_IDS", raising=False)
    assert AuthSettings.from_env().business_only_user_ids == ()
    monkeypatch.setenv("PLATFORM_BUSINESS_ONLY_USER_IDS", " limited, , other ")
    settings = AuthSettings.from_env()
    assert settings.business_only_user_ids == ("limited", "other")
    profile = AuthProfile(
        user=UserProfile(id="limited", username="limited", nickname="Limited"), portal_is_admin=True
    )
    application = object.__new__(AuthApplication)
    application.settings = settings
    application._dev_admin_user_id = None
    application.service = SimpleNamespace(profile=lambda _: profile)
    monkeypatch.setattr(
        "application.auth.actor_from_profile",
        lambda *a, **kw: PlatformActor(
            user_id="limited",
            username="limited",
            display_name="limited",
            email="",
            is_admin=True,
            portal_is_admin=True,
        ),
    )
    result = application.profile(None)
    assert result.model_dump(by_alias=True)["businessOnly"] is True
    assert result.is_admin is False
    assert result.portal_is_admin is True
    assert result.platform_permissions == ["business:read"]
    assert application.platform_actor(None).is_admin is False
