"""Schema 来源表绑定 API 集成测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor
from infra.s3 import StoredObject
from infra.workflow_mysql import get_workflow_session
from main import app
from script.init_schema_management import initialize_schema_management
from service.platform_access import PlatformActor


class FakeS3Storage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.bucket = "test-schema-scripts"

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> StoredObject:
        self.objects[(self.bucket, object_key)] = data
        return StoredObject(bucket=self.bucket, object_key=object_key, etag="test-etag")

    def get_object(self, bucket: str, object_key: str):
        raise NotImplementedError

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.objects.pop((bucket, object_key), None)


def _actor(user_id: str, is_admin: bool) -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=user_id,
        display_name=user_id,
        email=f"{user_id}@test",
        is_admin=is_admin,
    )


@pytest.fixture
def sources_api(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_schema_management(engine)
    storage = FakeS3Storage()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_workflow_session] = override_session
    monkeypatch.setattr("service.schema_management.get_schema_s3_storage", lambda: storage)
    monkeypatch.setenv("SCHEMA_AUTO_PROVENANCE", "false")
    # 数据源存在性校验走业务库——单测里直接放行（存在性语义单测覆盖）
    monkeypatch.setattr("service.schema_management._validate_datasource_exists", lambda ds_id: None)

    def set_actor(user_id: str, is_admin: bool) -> None:
        actor = _actor(user_id, is_admin)
        app.dependency_overrides[require_platform_actor] = lambda: actor

    set_actor("admin-1", True)
    yield engine, set_actor, monkeypatch
    app.dependency_overrides.pop(get_workflow_session, None)
    app.dependency_overrides.pop(require_platform_actor, None)
    engine.dispose()


async def _create_entity(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/schema-management/schemas/entities",
        json={
            "schemaKey": "widget",
            "name": "Widget",
            "label": "部件",
            "description": "",
            "properties": [{"name": "widget_id", "dataType": "string", "required": True}],
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.mark.asyncio
async def test_replace_sources_full_flow(sources_api) -> None:
    _, _set_actor, _ = sources_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)

        # 初始无绑定
        detail = (await client.get(f"/api/v1/schema-management/schemas/{entity['id']}")).json()[
            "data"
        ]
        assert detail["sources"] == []

        # 绑定两张来源表
        replaced = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={
                "sources": [
                    {
                        "datasourceId": "MYSQL-1",
                        "databaseName": "gkx",
                        "tableName": "scholar",
                        "pkColumn": "id",
                        "timeColumn": "update_time",
                    },
                    {
                        "datasourceId": "MYSQL-2",
                        "databaseName": "gkx_local",
                        "tableName": "paper",
                    },
                ]
            },
        )
        assert replaced.status_code == 200
        data = replaced.json()["data"]["sources"]
        assert len(data) == 2
        assert data[0]["tableName"] == "scholar"
        assert data[0]["timeColumn"] == "update_time"
        # 缺省 pk/time 列取默认值
        assert data[1]["pkColumn"] == "id"
        assert data[1]["timeColumn"] == "update_time"

        # detail 带回 sources
        detail = (await client.get(f"/api/v1/schema-management/schemas/{entity['id']}")).json()[
            "data"
        ]
        assert [s["tableName"] for s in detail["sources"]] == ["scholar", "paper"]

        # 全量替换为一张表（覆盖语义）
        replaced = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={
                "sources": [
                    {
                        "datasourceId": "MYSQL-1",
                        "databaseName": "gkx",
                        "tableName": "organization",
                        "pkColumn": "org_id",
                        "timeColumn": "modified_at",
                    }
                ]
            },
        )
        assert replaced.status_code == 200
        detail = (await client.get(f"/api/v1/schema-management/schemas/{entity['id']}")).json()[
            "data"
        ]
        assert len(detail["sources"]) == 1
        assert detail["sources"][0]["pkColumn"] == "org_id"
        assert detail["sources"][0]["timeColumn"] == "modified_at"

        # 空列表清空绑定
        cleared = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={"sources": []},
        )
        assert cleared.status_code == 200
        assert cleared.json()["data"]["sources"] == []


@pytest.mark.asyncio
async def test_replace_sources_unknown_datasource_conflict(sources_api) -> None:
    _, _set_actor, monkeypatch = sources_api

    def _missing(ds_id: str) -> None:
        from service.schema_management import SchemaConflictError

        raise SchemaConflictError(f"来源数据源不存在: {ds_id}")

    monkeypatch.setattr("service.schema_management._validate_datasource_exists", _missing)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={
                "sources": [
                    {
                        "datasourceId": "MYSQL-X",
                        "databaseName": "gkx",
                        "tableName": "scholar",
                    }
                ]
            },
        )
        assert response.status_code == 409
        assert "来源数据源不存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_replace_sources_duplicate_binding_rejected(sources_api) -> None:
    _, _set_actor, _ = sources_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={
                "sources": [
                    {"datasourceId": "MYSQL-1", "databaseName": "gkx", "tableName": "scholar"},
                    {"datasourceId": "MYSQL-1", "databaseName": "gkx", "tableName": "scholar"},
                ]
            },
        )
        # 请求体校验失败：HTTP 200 + ApiResponse code=422（全局 validation handler）
        assert response.status_code == 200
        assert response.json()["code"] == 422
        assert "来源表绑定不能重复" in response.json()["msg"] or any(
            "来源表绑定不能重复" in str(item.get("msg", ""))
            for item in (response.json().get("data") or [])
        )


@pytest.mark.asyncio
async def test_replace_sources_identifier_injection_rejected(sources_api) -> None:
    _, _set_actor, _ = sources_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={
                "sources": [
                    {
                        "datasourceId": "MYSQL-1",
                        "databaseName": "gkx; DROP TABLE x",
                        "tableName": "scholar",
                    }
                ]
            },
        )
        assert response.status_code == 200
        assert response.json()["code"] == 422


@pytest.mark.asyncio
async def test_replace_sources_permissions(sources_api) -> None:
    _, set_actor, _ = sources_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_actor("user-a", False)
        entity = await _create_entity(client)

        set_actor("user-b", False)
        forbidden = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={"sources": []},
        )
        assert forbidden.status_code == 403

        set_actor("admin-1", True)
        allowed = await client.put(
            f"/api/v1/schema-management/schemas/{entity['id']}/sources",
            json={
                "sources": [
                    {"datasourceId": "MYSQL-1", "databaseName": "gkx", "tableName": "scholar"}
                ]
            },
        )
        assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_replace_sources_schema_not_found(sources_api) -> None:
    _, _set_actor, _ = sources_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/v1/schema-management/schemas/missing-id/sources",
            json={"sources": []},
        )
        assert response.status_code == 404
