"""Schema 属性管理（新增 + 硬删除 + 管理员只读）集成测试。"""

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
    # 硬删除前置 guard 默认放行（无运行中抽取任务）；具体用例覆盖
    monkeypatch.setattr(
        "service.schema_management.find_running_extraction", lambda definition: None
    )

    def set_actor(user_id: str, is_admin: bool) -> None:
        actor = _actor(user_id, is_admin)
        app.dependency_overrides[require_platform_actor] = lambda: actor

    set_actor("admin-1", True)
    yield engine, set_actor
    app.dependency_overrides.pop(get_workflow_session, None)
    app.dependency_overrides.pop(require_platform_actor, None)
    engine.dispose()


def _fake_add_ddl(kind: str, name: str, prop: dict, graph_space: str | None = None) -> dict:
    return {
        "statement": f"ALTER {'TAG' if kind == 'entity' else 'EDGE'} {name} ADD ({prop['name']} {prop['data_type']});",
        "status": "succeeded",
        "error": None,
        "executed_at": "2026-09-02T00:00:00",
    }


def _patch_drop(
    monkeypatch: pytest.MonkeyPatch,
    columns: list[str] | None,
    *,
    status: str = "succeeded",
    error: str | None = None,
) -> None:
    """patch 图库列存在性检查与 DROP DDL。columns=None 模拟对象不存在。"""

    monkeypatch.setattr(
        "service.schema_management.describe_schema_columns",
        lambda kind, name, graph_space=None: columns,
    )
    monkeypatch.setattr(
        "service.schema_management.run_alter_drop_ddl",
        lambda kind, name, prop, graph_space=None: {
            "statement": f"ALTER {'TAG' if kind == 'entity' else 'EDGE'} {name} DROP ({prop});",
            "status": status,
            "error": error,
            "executed_at": "2026-09-02T00:00:00" if status == "succeeded" else None,
        },
    )


async def _create_entity(
    client: AsyncClient, *, name: str = "Widget", identity_key: str = ""
) -> dict:
    response = await client.post(
        "/api/v1/schema-management/schemas/entities",
        json={
            "schemaKey": name.lower(),
            "name": name,
            "label": name,
            "description": "",
            "identityKey": identity_key,
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

    def fake_alter_ddl(kind: str, name: str, prop: dict, graph_space: str | None = None) -> dict:
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
        lambda kind, name, prop, graph_space=None: {
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
        lambda kind, name, prop, graph_space=None: {
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
        lambda kind, name, prop, graph_space=None: {
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
async def test_delete_property_hard_delete_semantics(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr("service.schema_management.run_alter_add_ddl", _fake_add_ddl)
    columns = ["id", "name", "create_time", "update_time", "source_table", "widget_id", "rank"]
    _patch_drop(monkeypatch, columns)
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

        deleted = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert deleted.status_code == 200
        data = deleted.json()["data"]
        assert data["deleted"] is True
        assert data["propertyName"] == "rank"
        assert data["warnings"] == []
        assert data["ddlStatus"] == "succeeded"
        assert "ALTER TAG Widget DROP (rank)" in data["ddlStatement"]

        # 目录行已物理删除
        after = await _detail(client, entity["id"])
        assert "rank" not in [p["name"] for p in after["properties"]]

        # 列表（非 detail）的 propertyCount 同步
        listing = await client.get(
            "/api/v1/schema-management/schemas",
            params={"kind": "entity", "pageSize": 100},
        )
        row = next(item for item in listing.json()["data"]["items"] if item["id"] == entity["id"])
        assert row["propertyCount"] == len(after["properties"])

        # 再次删除已删属性 → 404（目录行已物理删除）
        again = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert again.status_code == 404

        # 硬删除后可重新新增同名属性（全新行，非复活）
        readd = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "string"},
        )
        assert readd.status_code == 201
        detail = await _detail(client, entity["id"])
        rank = next(p for p in detail["properties"] if p["name"] == "rank")
        assert rank["dataType"] == "string"


@pytest.mark.asyncio
async def test_add_delete_bump_property_revision(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr("service.schema_management.run_alter_add_ddl", _fake_add_ddl)
    _patch_drop(monkeypatch, ["widget_id", "rank"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        assert (await _detail(client, entity["id"]))["propertyRevision"] == 1

        await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        assert (await _detail(client, entity["id"]))["propertyRevision"] == 2

        response = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert response.status_code == 200
        assert (await _detail(client, entity["id"]))["propertyRevision"] == 3


@pytest.mark.asyncio
async def test_delete_property_running_task_blocked(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    _patch_drop(monkeypatch, ["widget_id", "rank"])
    monkeypatch.setattr(
        "service.schema_management.find_running_extraction",
        lambda definition: {"executionId": "EXEC-1", "name": "Widget 平台喂数抽取"},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/widget_id"
        )
        assert response.status_code == 409
        assert "任务「Widget 平台喂数抽取」正在抽取该 Schema" in response.json()["detail"]
        assert "任务中心" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_property_collects_warnings(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr("service.schema_management.run_alter_add_ddl", _fake_add_ddl)
    _patch_drop(monkeypatch, ["widget_id", "rank"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # identity_key 引用 rank：删除只警告不拦
        entity = await _create_entity(client, identity_key="rank")
        await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        response = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert response.status_code == 200
        warnings = response.json()["data"]["warnings"]
        assert warnings and any("identity_key" in item for item in warnings)


@pytest.mark.asyncio
async def test_delete_property_ddl_failure_keeps_catalog(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr("service.schema_management.run_alter_add_ddl", _fake_add_ddl)
    _patch_drop(
        monkeypatch,
        ["widget_id", "rank"],
        status="failed",
        error="SemanticError: conflicting index",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        revision_before = (await _detail(client, entity["id"]))["propertyRevision"]

        response = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert response.status_code == 502
        assert "conflicting index" in response.json()["detail"]

        # 图库 DROP 失败：目录行与修订号都不动
        detail = await _detail(client, entity["id"])
        assert "rank" in [p["name"] for p in detail["properties"]]
        assert detail["propertyRevision"] == revision_before


@pytest.mark.asyncio
async def test_delete_property_column_missing_skips_ddl(
    property_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor = property_api
    monkeypatch.setattr("service.schema_management.run_alter_add_ddl", _fake_add_ddl)
    # DESCRIBE 结果不含 rank（system schema DDL 未跑过 / 已删过）
    _patch_drop(monkeypatch, ["widget_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties",
            json={"name": "rank", "dataType": "int64"},
        )
        response = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}/properties/rank"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ddlStatus"] == "skipped"
        assert data["ddlStatement"] is None
        assert "rank" not in [
            p["name"] for p in (await _detail(client, entity["id"]))["properties"]
        ]


@pytest.mark.asyncio
async def test_stats_after_hard_delete(property_api, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _set_actor = property_api
    _patch_drop(monkeypatch, None)  # 图库对象不存在 → 跳 DDL 只删目录
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
