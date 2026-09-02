"""Schema 平台喂数抽取触发 API 集成测试（403 / 409 / 201，mock execute_definition）。"""

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
        from io import BytesIO

        return BytesIO(self.objects[(bucket, object_key)])

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
def extract_api(monkeypatch):
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
    monkeypatch.setattr("service.schema_management._validate_datasource_exists", lambda ds_id: None)
    # 脚本上传的工作流注册走 fake，避免写真实控制库
    monkeypatch.setattr(
        "service.workflow_operations.workflow_operations_service.create_python_definition",
        lambda *args, **kwargs: {"id": "schema-widget"},
    )

    executions: list[dict] = []

    async def fake_execute_definition(definition, payload, workflow_id=None, persist_task=False):
        executions.append(
            {
                "definition": definition,
                "payload": payload,
                "persist_task": persist_task,
            }
        )
        return {
            "id": "exec-1",
            "workflowId": "wf-1",
            "runId": None,
            "status": "RUNNING",
            "message": "ok",
        }

    monkeypatch.setattr(
        "service.workflow_operations.workflow_operations_service.execute_definition",
        fake_execute_definition,
    )

    def set_actor(user_id: str, is_admin: bool) -> None:
        actor = _actor(user_id, is_admin)
        app.dependency_overrides[require_platform_actor] = lambda: actor

    set_actor("admin-1", True)
    yield engine, set_actor, executions, storage
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


async def _bind_sources(client: AsyncClient, schema_id: str) -> None:
    response = await client.put(
        f"/api/v1/schema-management/schemas/{schema_id}/sources",
        json={
            "sources": [{"datasourceId": "MYSQL-1", "databaseName": "gkx", "tableName": "scholar"}]
        },
    )
    assert response.status_code == 200


async def _upload_script(client: AsyncClient, schema_id: str) -> None:
    response = await client.put(
        f"/api/v1/schema-management/schemas/{schema_id}/script",
        files={
            "script": (
                "widget.py",
                b"def workflow(payload):\n    return {'entities': []}\n",
                "text/x-python",
            )
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_extract_requires_script_and_sources(extract_api) -> None:
    _, _set_actor, executions, _storage = extract_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)

        # 无脚本无来源 → 409
        no_script = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/extract")
        assert no_script.status_code == 409
        assert "脚本" in no_script.json()["detail"]

        # 有脚本无来源 → 409
        await _upload_script(client, entity["id"])
        no_sources = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/extract")
        assert no_sources.status_code == 409
        assert "来源表" in no_sources.json()["detail"]

        # 有脚本有来源 → 201
        await _bind_sources(client, entity["id"])
        triggered = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/extract",
            json={"batchSize": 100},
        )
        assert triggered.status_code == 201
        data = triggered.json()["data"]
        assert data == {"executionId": "exec-1", "workflowId": "wf-1", "status": "RUNNING"}

    assert len(executions) == 1
    definition, payload, persist_task = (
        executions[0]["definition"],
        executions[0]["payload"],
        executions[0]["persist_task"],
    )
    assert definition["workflowType"] == "kg.schema.extract"
    assert definition["id"] == "schema-extract-widget"
    assert persist_task is True  # 任务中心可见
    assert payload["schemaId"] == entity["id"]
    assert payload["batchSize"] == 100
    assert payload["graphSpace"]


@pytest.mark.asyncio
async def test_extract_permissions(extract_api) -> None:
    _, set_actor, executions, _storage = extract_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_actor("user-a", False)
        entity = await _create_entity(client)
        await _upload_script(client, entity["id"])
        await _bind_sources(client, entity["id"])

        set_actor("user-b", False)
        forbidden = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/extract")
        assert forbidden.status_code == 403

        set_actor("admin-1", True)
        allowed = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/extract")
        assert allowed.status_code == 201

    assert len(executions) == 1


@pytest.mark.asyncio
async def test_extract_schema_not_found(extract_api) -> None:
    _, _set_actor, executions, _storage = extract_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/schema-management/schemas/missing/extract")
        assert response.status_code == 404
    assert executions == []


async def _detail(client: AsyncClient, schema_id: str) -> dict:
    response = await client.get(f"/api/v1/schema-management/schemas/{schema_id}")
    assert response.status_code == 200
    return response.json()["data"]


async def _add_property(client: AsyncClient, schema_id: str, name: str = "rank") -> None:
    response = await client.post(
        f"/api/v1/schema-management/schemas/{schema_id}/properties",
        json={"name": name, "dataType": "int64"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_extract_stale_script_signal(extract_api, monkeypatch: pytest.MonkeyPatch) -> None:
    """脚本双信号：属性变更后未更新脚本 → stale；重传脚本 → 消除。下发只提示放行。"""
    _, _set_actor, _executions, _storage = extract_api
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
        await _upload_script(client, entity["id"])
        await _bind_sources(client, entity["id"])

        script = (await _detail(client, entity["id"]))["script"]
        assert script["capturedRevision"] == 1
        assert script["stale"] is False
        assert script["lastRunStatus"] == "none"

        # 属性变更（property_revision+1）后未更新脚本 → stale
        await _add_property(client, entity["id"])
        script = (await _detail(client, entity["id"]))["script"]
        assert script["stale"] is True
        assert script["staleBehind"] == 1

        # 触发抽取：提示但放行
        triggered = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/extract")
        assert triggered.status_code == 201
        assert triggered.json()["data"]["staleScript"] is True
        assert triggered.json()["data"]["staleBehind"] == 1

        # 重传脚本 → captured_revision 刷新，警告消除
        await _upload_script(client, entity["id"])
        script = (await _detail(client, entity["id"]))["script"]
        assert script["stale"] is False
        assert script["capturedRevision"] == 2

        triggered = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/extract")
        assert triggered.status_code == 201
        assert "staleScript" not in triggered.json()["data"]


@pytest.mark.asyncio
async def test_backfill_requires_script_and_sources(extract_api) -> None:
    _, _set_actor, executions, _storage = extract_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        response = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/backfill")
        assert response.status_code == 409
    assert executions == []


@pytest.mark.asyncio
async def test_backfill_clears_watermarks_and_triggers(
    extract_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _set_actor, executions, _storage = extract_api
    cleared_ids: list[list[str]] = []
    monkeypatch.setattr(
        "service.script_watermark.clear_watermarks",
        lambda ids: (cleared_ids.append(list(ids)), 2)[1],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        await _upload_script(client, entity["id"])
        await _bind_sources(client, entity["id"])

        response = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/backfill")
        assert response.status_code == 201
        data = response.json()["data"]
        assert data == {
            "executionId": "exec-1",
            "workflowId": "wf-1",
            "status": "RUNNING",
            "watermarksCleared": 2,
            "forced": False,
        }
    assert cleared_ids == [["schema-extract-widget"]]
    assert executions[-1]["persist_task"] is True  # 任务中心可见/可停
    assert executions[-1]["payload"]["triggerSource"] == "MANUAL"


@pytest.mark.asyncio
async def test_backfill_stale_requires_force(extract_api, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _set_actor, executions, _storage = extract_api
    monkeypatch.setattr(
        "service.schema_management.run_alter_add_ddl",
        lambda kind, name, prop: {
            "statement": "ALTER ...",
            "status": "succeeded",
            "error": None,
            "executed_at": None,
        },
    )
    monkeypatch.setattr("service.script_watermark.clear_watermarks", lambda ids: 0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        entity = await _create_entity(client)
        await _upload_script(client, entity["id"])
        await _bind_sources(client, entity["id"])
        await _add_property(client, entity["id"])  # revision+1 → 脚本落后

        blocked = await client.post(f"/api/v1/schema-management/schemas/{entity['id']}/backfill")
        assert blocked.status_code == 409
        assert "回填可能无效" in blocked.json()["detail"]

        forced = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/backfill", json={"force": True}
        )
        assert forced.status_code == 201
        assert forced.json()["data"]["forced"] is True

    assert len(executions) == 1  # 被拦的那次没有下发
