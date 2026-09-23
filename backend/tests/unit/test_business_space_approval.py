from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.handler import business_access as api
from db_model.base import Base
from db_model.business_access import (
    BusinessClient,
    BusinessGraphSpace,
    BusinessMember,
    BusinessSpaceRequest,
)
from db_model.platform_governance import AdminAuditLog
from service.platform_access import PlatformActor

ADMIN = PlatformActor("admin", "admin", "Admin", "", True)
DEV = PlatformActor("dev", "dev", "Dev", "", False, business_id="a", business_role="developer")


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            BusinessClient.__table__,
            BusinessMember.__table__,
            BusinessGraphSpace.__table__,
            BusinessSpaceRequest.__table__,
            AdminAuditLog.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def scope():
        with factory.begin() as session:
            yield session

    monkeypatch.setattr(api, "session_scope", scope)
    with scope() as session:
        session.add(BusinessClient(client_id="a", name="A"))
    yield factory
    engine.dispose()


def test_approval_reserves_business_before_ddl_and_retries_vector_failure(database, monkeypatch):
    spaces = set()
    calls = []

    class FakeSpaceService:
        def __init__(self, session):
            self.client = self

        def list_spaces(self):
            return list(spaces)

        def create_space(self, actor, name):
            with database() as session:
                registry = session.get(BusinessGraphSpace, name)
                assert registry.client_id == "a"
                assert registry.provision_request_id
            spaces.add(name)
            calls.append("create")
            return {"vectorDbStatus": "failed"}

        def _ensure_vector_database(self, name):
            calls.append("vector")
            return "ready", ""

    monkeypatch.setattr(api, "GraphSpaceService", FakeSpaceService)
    with database.begin() as session:
        response = api.request_space(api.RequestPayload(spaceName="new_space"), DEV, session)
        request_id = response.data["id"]
    assert not spaces
    with database() as session:
        result = api.decide_request(request_id, api.DecisionPayload(approve=True), ADMIN, session)
        assert result.data["status"] == "failed"
    with database() as session:
        result = api.retry_request(request_id, ADMIN, session)
        assert result.data["status"] == "ready"
    assert calls == ["create", "vector"]
    with database() as session:
        assert session.get(BusinessGraphSpace, "new_space").client_id == "a"
        with pytest.raises(HTTPException):
            api.decide_request(request_id, api.DecisionPayload(approve=True), ADMIN, session)


def test_rejected_application_never_creates_space(database, monkeypatch):
    monkeypatch.setattr(api, "_provision", lambda *args: pytest.fail("rejection cannot create"))
    with database.begin() as session:
        request_id = api.request_space(api.RequestPayload(spaceName="rejected"), DEV, session).data[
            "id"
        ]
    with database.begin() as session:
        result = api.decide_request(request_id, api.DecisionPayload(approve=False), ADMIN, session)
        assert result.data["status"] == "rejected"
    with database() as session:
        assert session.scalar(select(BusinessGraphSpace)) is None


def test_duplicate_application_denied(database):
    with database.begin() as session:
        api.request_space(api.RequestPayload(spaceName="duplicate"), DEV, session)
    with database.begin() as session:
        with pytest.raises(HTTPException) as caught:
            api.request_space(api.RequestPayload(spaceName="duplicate"), DEV, session)
        assert caught.value.status_code == 409


def test_developer_cannot_request_without_business(database):
    no_business = PlatformActor("none", "none", "None", "", False)
    with database.begin() as session:
        with pytest.raises(HTTPException):
            api.request_space(api.RequestPayload(spaceName="unowned"), no_business, session)


@pytest.mark.asyncio
async def test_api_roles_and_server_owned_business(database):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from biz.dependencies.auth import require_platform_actor
    from infra.mysql import get_session

    app = FastAPI()
    app.include_router(api.router)
    current = [DEV]
    app.dependency_overrides[require_platform_actor] = lambda: current[0]

    def db_session():
        with database.begin() as session:
            yield session

    app.dependency_overrides[get_session] = db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path, payload in [
            ("/business-access/businesses/other", {"name": "Other"}),
            ("/business-access/members/dev", {"role": "admin", "clientId": "a"}),
            ("/business-access/spaces/production", {"isSharedProduction": True}),
        ]:
            response = await client.put(path, json=payload)
            assert response.status_code == 403
        response = await client.post(
            "/business-access/requests",
            json={
                "spaceName": "api_space",
                "clientId": "other",
                "requestedBy": "admin",
            },
        )
        assert response.status_code == 403
        response = await client.post(
            "/business-access/requests",
            json={
                "spaceName": "api_space",
                "requestedBy": "admin",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["clientId"] == "a"
        assert data["requestedBy"] == "dev"
        current[0] = PlatformActor("user", "user", "User", "", False, business_id="a")
        response = await client.post("/business-access/requests", json={"spaceName": "denied"})
        assert response.status_code == 403


def test_global_admin_can_request_for_business_without_membership(database):
    with database.begin() as session:
        result = api.request_space(
            api.RequestPayload(spaceName="admin_space", clientId="a"), ADMIN, session
        )
        assert result.data["clientId"] == "a"
        assert result.data["requestedBy"] == "admin"


@pytest.mark.asyncio
async def test_company_test_role_cannot_manage_business(database):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from biz.dependencies.auth import require_platform_actor

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_platform_actor] = lambda: PlatformActor(
        "test",
        "test",
        "Test",
        "",
        True,
        business_id="a",
        business_only=True,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put("/business-access/businesses/other", json={"name": "Other"})
        assert response.status_code == 403
