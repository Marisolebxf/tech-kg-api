"""配置资源 owner 隔离单测：列表过滤 + 跨用户访问 403。

用 SQLite 内存库 + dependency_overrides（get_session / require_platform_actor）
直接挂四个配置 router，不需要真实 MySQL / Redis。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
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


def _seed_llm(session_factory, config_id: str, owner: str) -> None:
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
            is_default=False,
            status="正常",
            created_at=now,
            updated_at=now,
        )
    )
    s.commit()
    s.close()


@pytest.mark.asyncio
async def test_list_filters_by_owner(session_factory) -> None:
    _seed_llm(session_factory, "LLM-A", USER_A)
    _seed_llm(session_factory, "LLM-B", USER_B)

    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
        resp = await client.get("/api/v1/llm-config/llm-configs")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["data"]]
        assert ids == ["LLM-A"]


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
async def test_create_sets_owner_to_actor(session_factory) -> None:
    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
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

    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
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
async def test_set_default_scoped_to_owner(session_factory) -> None:
    """A、B 各设默认互不影响：is_default 按 owner 隔离，不再全局唯一。"""
    _seed_llm(session_factory, "LLM-A1", USER_A)
    _seed_llm(session_factory, "LLM-A2", USER_A)
    _seed_llm(session_factory, "LLM-B1", USER_B)

    async with _client(_make_app(session_factory, _actor(USER_A))) as client:
        assert (
            await client.post("/api/v1/llm-config/llm-configs/LLM-A1/set-default")
        ).status_code == 200

    async with _client(_make_app(session_factory, _actor(USER_B))) as client:
        assert (
            await client.post("/api/v1/llm-config/llm-configs/LLM-B1/set-default")
        ).status_code == 200
        resp = await client.get("/api/v1/llm-config/llm-configs")
        defaults = {item["id"] for item in resp.json()["data"] if item["isDefault"]}
        assert defaults == {"LLM-B1"}

    s = session_factory()
    rows = {r.id: r.is_default for r in s.query(LlmConfig).all()}
    s.close()
    assert rows == {"LLM-A1": True, "LLM-A2": False, "LLM-B1": True}
