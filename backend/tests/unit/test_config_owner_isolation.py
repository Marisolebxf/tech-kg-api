"""共享配置角色权限测试：管理员管理、开发人员只读选用、普通用户拒绝。

用 SQLite 内存库 + dependency_overrides（get_session / require_platform_actor）
直接挂四个配置 router，不需要真实 MySQL / Redis。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor
from biz.handler import embedding_config, llm_config, milvus_config, mysql_datasource
from db_model.base import Base
from db_model.embedding_config import EmbeddingConfig
from db_model.llm_config import LlmConfig
from db_model.milvus_config import MilvusConfig
from db_model.mysql_datasource import MysqlDatasource
from infra.mysql import get_session
from service.platform_access import PlatformActor

USER_A = "101"
USER_B = "202"


def _actor(user_id: str, is_admin: bool = False) -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=f"user{user_id}",
        display_name=f"用户{user_id}",
        email="",
        is_admin=is_admin,
    )


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=[
            LlmConfig.__table__,
            MysqlDatasource.__table__,
            MilvusConfig.__table__,
            EmbeddingConfig.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


def _make_app(session_factory, actor: PlatformActor) -> FastAPI:
    app = FastAPI()

    def fake_session() -> AsyncIterator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[require_platform_actor] = lambda: actor
    for module in (llm_config, mysql_datasource, milvus_config, embedding_config):
        app.include_router(module.router, prefix="/api/v1")
    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _seed_llm(session_factory, config_id: str, owner: str, *, is_default: bool = False) -> None:
    s = session_factory()
    now = datetime.utcnow()
    s.add(
        LlmConfig(
            id=config_id,
            name=f"cfg-{config_id}",
            description="",
            base_url="http://llm",
            api_key="k",
            model="m",
            owner=owner,
            is_default=is_default,
            status="正常",
            created_at=now,
            updated_at=now,
        )
    )
    s.commit()
    s.close()


@pytest.mark.asyncio
async def test_ordinary_user_cannot_list_shared_configs(session_factory) -> None:
    _seed_llm(session_factory, "LLM-A", USER_A)
    _seed_llm(session_factory, "LLM-B", USER_B)

    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
        resp = await client.get("/api/v1/llm-config/llm-configs")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_sees_all(session_factory) -> None:
    _seed_llm(session_factory, "LLM-A", USER_A)
    _seed_llm(session_factory, "LLM-B", USER_B)

    async with _client(_make_app(session_factory, _actor("admin", is_admin=True))) as client:
        resp = await client.get("/api/v1/llm-config/llm-configs")
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["data"]}
        assert ids == {"LLM-A", "LLM-B"}


@pytest.mark.asyncio
async def test_cross_user_access_forbidden(session_factory) -> None:
    _seed_llm(session_factory, "LLM-B", USER_B)

    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
        assert (await client.get("/api/v1/llm-config/llm-configs/LLM-B")).status_code == 403
        assert (await client.delete("/api/v1/llm-config/llm-configs/LLM-B")).status_code == 403
        assert (
            await client.post("/api/v1/llm-config/llm-configs/LLM-B/set-default")
        ).status_code == 403
        assert (await client.post("/api/v1/llm-config/llm-configs/LLM-B/test")).status_code == 403
        resp = await client.put("/api/v1/llm-config/llm-configs/LLM-B", json={"name": "hijack"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_records_actor_without_business_binding(session_factory) -> None:
    async with _client(_make_app(session_factory, _actor(USER_A, is_admin=True))) as client:
        resp = await client.post(
            "/api/v1/llm-config/llm-configs",
            json={"name": "mine", "baseUrl": "http://llm", "model": "m", "apiKey": "k"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["owner"] == USER_A


@pytest.mark.asyncio
async def test_update_cannot_change_owner(session_factory) -> None:
    _seed_llm(session_factory, "LLM-A", USER_A)

    async with _client(_make_app(session_factory, _actor(USER_A, is_admin=True))) as client:
        resp = await client.put("/api/v1/llm-config/llm-configs/LLM-A", json={"owner": USER_B})
        assert resp.status_code == 200
        assert resp.json()["data"]["owner"] == USER_A


@pytest.mark.asyncio
async def test_mysql_databases_requires_owner(session_factory) -> None:
    s = session_factory()
    now = datetime.utcnow()
    s.add(
        MysqlDatasource(
            id="MYSQL-B",
            name="b",
            host="h",
            port=3306,
            default_database="",
            username="u",
            password="p",
            owner=USER_B,
            is_default=False,
            status="正常",
            created_at=now,
            updated_at=now,
        )
    )
    s.commit()
    s.close()

    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
        resp = await client.get("/api/v1/mysql-datasources/MYSQL-B/databases")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_set_default_exclusive_globally(session_factory) -> None:
    """管理员看到全局列表：设默认时同类别全局互斥（00382），跨 owner 的旧默认一并取消。

    开发人员和普通用户不能设置默认。
    """
    _seed_llm(session_factory, "LLM-A1", USER_A, is_default=True)
    _seed_llm(session_factory, "LLM-A2", USER_A)
    _seed_llm(session_factory, "LLM-B1", USER_B)

    async with _client(_make_app(session_factory, _actor("admin", is_admin=True))) as client:
        assert (
            await client.post("/api/v1/llm-config/llm-configs/LLM-B1/set-default")
        ).status_code == 200
        resp = await client.get("/api/v1/llm-config/llm-configs")
        defaults = {item["id"] for item in resp.json()["data"] if item["isDefault"]}
        assert defaults == {"LLM-B1"}

    s = session_factory()
    rows = {r.id: r.is_default for r in s.query(LlmConfig).all()}
    s.close()
    assert rows == {"LLM-A1": False, "LLM-A2": False, "LLM-B1": True}


@pytest.mark.asyncio
async def test_developer_reads_all_shared_configs_and_cannot_mutate(session_factory, monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    _seed_llm(session_factory, "LLM-OLD", "legacy-admin")
    _seed_llm(session_factory, "LLM-OTHER", "business:other")
    with session_factory() as session:
        session.add(
            MysqlDatasource(
                id="MYSQL-OTHER",
                name="other",
                host="host",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                username="u",
                password="secret",
                owner="business:other",
            )
        )
        session.commit()
    developer = replace(
        _actor(USER_A),
        business_id="mine",
        business_role="developer",
        context_business_id="mine",
        context_graph_space="mine-space",
    )
    monkeypatch.setattr(
        "application.mysql_datasource.MysqlDatasourceApplication.list_databases",
        lambda self, config_id: ["source_db"],
    )
    monkeypatch.setattr(
        "application.mysql_datasource.MysqlDatasourceApplication.list_tables",
        lambda self, config_id, db: [{"name": "source_table"}],
    )
    monkeypatch.setattr(
        "application.mysql_datasource.MysqlDatasourceApplication.list_columns",
        lambda self, config_id, table, db: [{"name": "id"}],
    )
    async with _client(_make_app(session_factory, developer)) as client:
        llm = "/api/v1/llm-config/llm-configs"
        mysql = "/api/v1/mysql-datasources"
        response = await client.get(llm)
        assert {row["id"] for row in response.json()["data"]} == {"LLM-OLD", "LLM-OTHER"}
        assert (await client.get(mysql)).json()["data"][0]["id"] == "MYSQL-OTHER"
        for endpoint in [f"{llm}/LLM-OTHER", f"{mysql}/MYSQL-OTHER"]:
            assert (await client.get(endpoint)).status_code == 200
            assert (await client.put(endpoint, json={"name": "forbidden"})).status_code == 403
            assert (await client.delete(endpoint)).status_code == 403
            for operation in ["set-default", "test"]:
                assert (await client.post(f"{endpoint}/{operation}")).status_code == 403
        assert (
            await client.post(llm, json={"name": "x", "baseUrl": "http://llm", "model": "m"})
        ).status_code == 403
        assert (
            await client.post(mysql, json={"name": "x", "host": "h", "username": "u"})
        ).status_code == 403
        assert (
            await client.post(
                f"{llm}/verify", json={"baseUrl": "http://llm", "model": "m", "apiKey": "k"}
            )
        ).status_code == 403
        for suffix in ["databases", "tables", "tables/source_table/columns"]:
            assert (await client.get(f"{mysql}/MYSQL-OTHER/{suffix}")).status_code == 200
    with session_factory() as session:
        assert session.get(LlmConfig, "LLM-OTHER").owner == "business:other"
        assert session.get(MysqlDatasource, "MYSQL-OTHER").name == "other"


def test_workflow_selectors_allow_shared_configs_but_keep_graph_guard(session_factory, monkeypatch):
    from fastapi import HTTPException

    from biz.handler import workflow_system

    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    _seed_llm(session_factory, "LLM-OTHER", "business:other")
    with session_factory() as session:
        session.add(
            MysqlDatasource(
                id="MYSQL-OTHER",
                name="other",
                host="host",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                username="u",
                password="secret",
                owner="legacy-admin",
            )
        )
        session.commit()
    monkeypatch.setattr("infra.mysql.create_session", session_factory)
    developer = replace(_actor(USER_A), business_id="mine", business_role="developer")

    def guard(actor, space, action):
        assert action == "write"
        if space != "mine-space":
            raise HTTPException(403, "space denied")

    monkeypatch.setattr(workflow_system, "ensure_space_access", guard)
    selectors = {
        "llm_config_id": "LLM-OTHER",
        "mysql_datasource_id": "MYSQL-OTHER",
        "graph_space": "mine-space",
    }
    workflow_system._validate_resource_selectors(developer, selectors)
    with pytest.raises(HTTPException, match="space denied"):
        workflow_system._validate_resource_selectors(
            developer, {**selectors, "graph_space": "public"}
        )


@pytest.mark.asyncio
async def test_admin_business_context_does_not_filter_legacy_configuration(
    session_factory, monkeypatch
):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    _seed_llm(session_factory, "LLM-LEGACY", "former-admin")
    administrator = replace(
        _actor("admin", is_admin=True), context_business_id="mine", context_graph_space="mine-space"
    )
    async with _client(_make_app(session_factory, administrator)) as client:
        path = "/api/v1/llm-config/llm-configs"
        assert (await client.get(path)).json()["data"][0]["id"] == "LLM-LEGACY"
        assert (await client.get(f"{path}/LLM-LEGACY")).status_code == 200
        response = await client.put(f"{path}/LLM-LEGACY", json={"description": "updated"})
        assert response.status_code == 200
        assert response.json()["data"]["owner"] == "former-admin"
