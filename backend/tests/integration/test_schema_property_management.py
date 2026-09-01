"""Schema 属性管理（增删 + 目录级软删 + 管理员只读）集成测试。"""

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
def property_api(monkeypatch):
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
    monkeypatch.delenv("SCHEMA_ALLOW_SYSTEM_DELETE", raising=False)
    monkeypatch.setenv("SCHEMA_AUTO_PROVENANCE", "false")

    def set_actor(user_id: str, is_admin: bool) -> None:
        actor = _actor(user_id, is_admin)
        app.dependency_overrides[require_platform_actor] = lambda: actor

    set_actor("admin-1", True)
    yield engine, set_actor
    app.dependency_overrides.pop(get_workflow_session, None)
    app.dependency_overrides.pop(require_platform_actor, None)
    engine.dispose()


async def _create_entity(client: AsyncClient, *, name: str = "Widget") -> dict:
    response = await client.post(
        "/api/v1/schema-management/schemas/entities",
        json={
            "schemaKey": name.lower(),
            "name": name,
            "label": name,
            "description": "",
            "properties": [
                {"name": "widget_id", "dataType": "string", "required": True},
            ],
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _detail(client: AsyncClient, schema_id: str) -> dict:
    response = await client.get(f"/api/v1/schema-management/schemas/{schema_id}")
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_add_property_success(property_api, monkeypatch: pytest.MonkeyPatch) -> None:
    _, set_actor = property_api

    def fake_alter_ddl(kind: str, name: str, prop: dict) -> dict:
        return {
            "statement": f"ALTER {'TAG' if kind == 'entity' else 'EDGE'} {name} ADD ({prop['name']} {prop['data_type']});",
            "status": "succeeded",
            "error": None,
            "executed_at": "2026-08-31T12:00:00",
        }

    monkeypatch.setattr("service.schema_management.run_alter_add_ddl", fake_alter_ddl)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64", "required": False},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["property"]["name"] == "rank"
        assert data["property"]["locked"] is False
        assert "ALTER TAG Widget ADD (rank int64)" in data["ddlStatement"]
        assert data["ddlStatus"] == "succeeded"

        detail = await _detail(client, entity["id"])
        names = [p["name"] for p in detail["properties"]]
        assert "rank" in names
        # 新属性 position 在尾部
        assert names[-1] == "rank"


@pytest.mark.asyncio
async def test_add_property_duplicate_conflict(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr(
        "service.schema_management.run_alter_add_ddl",
        lambda kind, name, prop: {
            "statement": "ALTER ...",
            "status": "succeeded",
            "error": None,
            "executed_at": None,
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        payload = {"name": "rank", "dataType": "int64"}
        first = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties", json=payload
        )
        assert first.status_code == 201
        second = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties", json=payload
        )
        assert second.status_code == 409
        # 与注入的公共必选属性重名也 409
        required_name = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "create_time", "dataType": "string"},
        )
        assert required_name.status_code == 409


@pytest.mark.asyncio
async def test_system_schema_non_admin_forbidden(property_api) -> None:
    _, set_actor = property_api
    set_actor("user-a", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get(
            "/api/v1/schema-management/schemas",
            params={"kind": "entity", "pageSize": 100, "includeDetails": True},
        )
        expert = next(item for item in listing.json()["data"]["items"] if item["name"] == "Expert")
        assert expert["canManageProperties"] is False

        response = await client.post(
            f"/api/v1/schema-management/schemas/{expert['id']}/properties",
            json={"name": "extra", "dataType": "string"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_owner_non_admin_forbidden(property_api, monkeypatch: pytest.MonkeyPatch) -> None:
    _, set_actor = property_api
    monkeypatch.setattr(
        "service.schema_management.run_alter_add_ddl",
        lambda kind, name, prop: {
            "statement": "ALTER ...",
            "status": "succeeded",
            "error": None,
            "executed_at": None,
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_actor("user-a", False)
        entity = await _create_entity(client)

        set_actor("user-b", False)
        response = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        assert response.status_code == 403

        set_actor("admin-1", True)
        response = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_add_property_ddl_failure_rolls_back_catalog(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr(
        "service.schema_management.run_alter_add_ddl",
        lambda kind, name, prop: {
            "statement": "ALTER ...",
            "status": "failed",
            "error": "SemanticError",
            "executed_at": None,
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        assert response.status_code == 502
        # 目录行已回滚：属性不存在
        detail = await _detail(client, entity["id"])
        assert "rank" not in [p["name"] for p in detail["properties"]]


@pytest.mark.asyncio
async def test_delete_property_semantics(property_api, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr(
        "service.schema_management.run_alter_add_ddl",
        lambda kind, name, prop: {
            "statement": "ALTER ...",
            "status": "succeeded",
            "error": None,
            "executed_at": None,
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )

        # 必选属性不可删除
        required_delete = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/id"
        )
        assert required_delete.status_code == 409

        # 不存在 → 404
        missing = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/nope"
        )
        assert missing.status_code == 404

        before = await _detail(client, entity["id"])
        before_count = before["propertyCount"] if "propertyCount" in before else None
        assert before_count is None  # detail 带 properties 列表，非 propertyCount

        deleted = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"deleted": True, "propertyName": "rank"}

        # 列表过滤已删属性
        after = await _detail(client, entity["id"])
        assert "rank" not in [p["name"] for p in after["properties"]]

        # 列表（非 detail）的 propertyCount 同步过滤
        listing = await client.get(
            "/api/v1/schema-management/schemas",
            params={"kind": "entity", "pageSize": 100},
        )
        row = next(item for item in listing.json()["data"]["items"] if item["id"] == entity["id"])
        assert row["propertyCount"] == len(after["properties"])

        # 再次删除已删属性 → 404
        again = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert again.status_code == 404

        # 软删后可复活（同名重新添加成功）
        resurrect = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "string"},
        )
        assert resurrect.status_code == 201
        detail = await _detail(client, entity["id"])
        rank = next(p for p in detail["properties"] if p["name"] == "rank")
        assert rank["dataType"] == "string"


@pytest.mark.asyncio
async def test_stats_excludes_deleted_properties(property_api) -> None:
    _, _set_actor = property_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 删除一个系统 schema 的非必选属性后，overview 的 propertyFields 应减少
        overview_before = await client.get("/api/v1/schema-management/overview")
        before = overview_before.json()["data"]["propertyFields"]

        listing = await client.get(
            "/api/v1/schema-management/schemas",
            params={"kind": "entity", "pageSize": 100, "includeDetails": True},
        )
        expert = next(item for item in listing.json()["data"]["items"] if item["name"] == "Expert")
        deletable = next(p["name"] for p in expert["properties"] if not p["locked"])
        deleted = await client.delete(
            f"/api/v1/schema-management/schemas/{expert['id']}/properties/{deletable}"
        )
        assert deleted.status_code == 200

        overview_after = await client.get("/api/v1/schema-management/overview")
        after = overview_after.json()["data"]["propertyFields"]
        assert after == before - 1
