"""ZP-20261101-11: role/tenant isolation and connection metadata containment."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor
from biz.handler import mysql_datasource as handler
from db_model.base import Base
from db_model.business_access import BusinessClient
from db_model.config_ownership import ConfigOwnership
from db_model.mysql_datasource import MysqlDatasource
from infra.mysql import get_session
from service.platform_access import BusinessMembershipGrant, PlatformActor


def actor(*, admin=False, business="alpha", developer=True):
    return PlatformActor(
        user_id="admin" if admin else "developer",
        username="test",
        display_name="test",
        email="",
        is_admin=admin,
        business_id=business,
        business_role="developer" if developer else "user",
        context_business_id=business,
    )


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        engine,
        tables=[
            BusinessClient.__table__,
            ConfigOwnership.__table__,
            MysqlDatasource.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as session:
        session.add_all([BusinessClient(client_id=b, name=b) for b in ["alpha", "beta"]])
        for identifier, business in [
            ("PUBLIC", None),
            ("ALPHA", "alpha"),
            ("BETA", "beta"),
            ("LEGACY", "missing"),
        ]:
            session.add(
                MysqlDatasource(
                    id=identifier,
                    name=identifier,
                    host="10.25.0.12",
                    port=30306,
                    username="internal_account",
                    password="do-not-return-fragments-9876",
                    default_database="approved_db",
                    owner="historical-owner",
                    description="private deployment notes",
                    created_at=now,
                    updated_at=now,
                )
            )
            if business != "missing":
                session.add(
                    ConfigOwnership(config_kind="mysql", config_id=identifier, business_id=business)
                )
        session.commit()
    handler._config_cache_clear()
    yield factory
    handler._config_cache_clear()
    engine.dispose()


def client(factory, identity):
    app = FastAPI()

    def session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[require_platform_actor] = lambda: identity
    app.include_router(handler.router, prefix="/api/v1")
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_shared_catalog_contains_no_connection_metadata_even_after_admin_read(database):
    async with client(database, actor(admin=True)) as admin:
        response = await admin.get("/api/v1/mysql-datasources")
        assert response.status_code == 200
        assert {r["id"] for r in response.json()["data"]} == {"PUBLIC", "ALPHA", "BETA", "LEGACY"}
    async with client(database, actor()) as developer:
        response = await developer.get("/api/v1/mysql-datasources")
        rows = {r["id"]: r for r in response.json()["data"]}
        assert set(rows) == {"PUBLIC", "ALPHA"}
        for key in [
            "host",
            "port",
            "username",
            "password",
            "passwordMasked",
            "hasPassword",
            "defaultDatabase",
            "owner",
            "description",
        ]:
            assert key not in rows["PUBLIC"]
        assert rows["PUBLIC"]["canManage"] is False
        # Business developers can still edit configurations they actually manage.
        assert rows["ALPHA"]["canManage"] is True
        assert rows["ALPHA"]["host"] == "10.25.0.12"
        detail = await developer.get("/api/v1/mysql-datasources/PUBLIC")
        assert "internal_account" not in detail.text
        assert "10.25.0.12" not in detail.text


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [actor(developer=False), replace(actor(), business_only=True)])
async def test_non_maintainers_cannot_read_datasources(database, identity):
    async with client(database, identity) as user:
        assert (await user.get("/api/v1/mysql-datasources")).status_code == 403
        assert (await user.get("/api/v1/mysql-datasources/PUBLIC/databases")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["BETA", "LEGACY"])
@pytest.mark.parametrize("suffix", ["", "/databases", "/tables", "/tables/a/columns"])
async def test_cross_business_and_unreviewed_ids_denied_before_any_connection(
    database, monkeypatch, identifier, suffix
):
    calls = []
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication, "list_databases", lambda *a: calls.append(a)
    )
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication, "list_tables", lambda *a: calls.append(a)
    )
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication, "list_columns", lambda *a: calls.append(a)
    )
    async with client(database, actor()) as developer:
        result = await developer.get("/api/v1/mysql-datasources/" + identifier + suffix)
        assert result.status_code == 403
    assert calls == []


@pytest.mark.asyncio
async def test_list_honors_selected_business_even_for_multi_business_developer(database):
    identity = replace(
        actor(),
        memberships=(
            BusinessMembershipGrant("alpha", "developer"),
            BusinessMembershipGrant("beta", "developer"),
        ),
    )
    async with client(database, identity) as developer:
        rows = (await developer.get("/api/v1/mysql-datasources")).json()["data"]
        assert {r["id"] for r in rows} == {"PUBLIC", "ALPHA"}
        assert (await developer.get("/api/v1/mysql-datasources/BETA")).status_code == 403


@pytest.mark.asyncio
async def test_developer_database_selector_does_not_issue_show_databases(database, monkeypatch):
    def forbidden(*args):
        pytest.fail("Developer must not enumerate server-wide database names")

    monkeypatch.setattr(handler.MysqlDatasourceApplication, "list_databases", forbidden)
    async with client(database, actor()) as developer:
        result = await developer.get("/api/v1/mysql-datasources/PUBLIC/databases")
        assert result.json()["data"] == {"items": ["approved_db"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["tables", "tables/customer/columns"])
async def test_schema_enumeration_cannot_change_database(database, monkeypatch, suffix):
    calls = []
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication, "list_tables", lambda *a: calls.append(a) or []
    )
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication, "list_columns", lambda *a: calls.append(a) or []
    )
    async with client(database, actor()) as developer:
        path = "/api/v1/mysql-datasources/PUBLIC/" + suffix
        assert (await developer.get(path, params={"database": "other_tenant"})).status_code == 403
        assert calls == []
        assert (await developer.get(path, params={"database": "approved_db"})).status_code == 200
    assert calls and calls[0][-1] == "approved_db"


@pytest.mark.asyncio
async def test_shared_consumer_cannot_probe_before_authorization(database, monkeypatch):
    calls = []
    monkeypatch.setattr(handler, "consume_mysql_datasource_probe", lambda user: calls.append(user))
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication, "test_connection", lambda *a: calls.append(a)
    )
    async with client(database, actor()) as developer:
        assert (await developer.post("/api/v1/mysql-datasources/PUBLIC/test")).status_code == 403
    assert calls == []


@pytest.mark.asyncio
async def test_authorized_probe_checks_budget_before_calling_service(database, monkeypatch):
    calls = []
    monkeypatch.setattr(
        handler, "consume_mysql_datasource_probe", lambda user: calls.append("budget:" + user)
    )
    monkeypatch.setattr(
        handler.MysqlDatasourceApplication,
        "test_connection",
        lambda *a: calls.append("probe") or {"ok": True},
    )
    async with client(database, actor()) as developer:
        result = await developer.post("/api/v1/mysql-datasources/ALPHA/test")
        assert result.status_code == 200
    assert calls == ["budget:developer", "probe"]
