from __future__ import annotations

from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infra.s3 import StoredObject
from infra.workflow_mysql import get_workflow_session
from main import app
from script.init_schema_management import initialize_schema_management


class FakeBody(BytesIO):
    def iter_chunks(self, chunk_size: int):
        while chunk := self.read(chunk_size):
            yield chunk


class FakeS3Storage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.bucket = "test-schema-scripts"

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> StoredObject:
        self.objects[(self.bucket, object_key)] = data
        return StoredObject(bucket=self.bucket, object_key=object_key, etag="test-etag")

    def get_object(self, bucket: str, object_key: str) -> FakeBody:
        return FakeBody(self.objects[(bucket, object_key)])

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.objects.pop((bucket, object_key), None)


@pytest.fixture
def schema_api(monkeypatch):
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
    # 系统保护与 provenance 注入取默认行为，避免容器 env 影响断言
    monkeypatch.delenv("SCHEMA_ALLOW_SYSTEM_DELETE", raising=False)
    monkeypatch.setenv("SCHEMA_AUTO_PROVENANCE", "false")
    yield engine, storage
    app.dependency_overrides.pop(get_workflow_session, None)
    engine.dispose()


@pytest.mark.asyncio
async def test_schema_management_full_flow(schema_api, monkeypatch: pytest.MonkeyPatch) -> None:
    _, storage = schema_api
    ddl_calls: list[tuple[str, str, list[dict]]] = []

    def fake_run_ddl(kind: str, name: str, properties: list[dict]) -> dict:
        ddl_calls.append((kind, name, properties))
        return {
            "statement": f"CREATE {'TAG' if kind == 'entity' else 'EDGE'} IF NOT EXISTS {name}(...);",
            "status": "succeeded",
            "error": None,
            "executed_at": "2026-08-18T12:00:00",
        }

    monkeypatch.setattr("service.schema_management.run_schema_ddl", fake_run_ddl)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        overview = await client.get("/api/v1/schema-management/overview")
        assert overview.status_code == 200
        assert overview.json()["data"]["entityTypes"] == 14
        assert overview.json()["data"]["factRelationTypes"] == 44
        assert overview.json()["data"]["inferredRelationTypes"] == 9

        listing = await client.get(
            "/api/v1/schema-management/schemas",
            params={"kind": "entity", "pageSize": 100, "includeDetails": True},
        )
        assert listing.status_code == 200
        assert listing.json()["data"]["total"] == 14
        expert = next(item for item in listing.json()["data"]["items"] if item["name"] == "Expert")
        assert expert["properties"]

        forged_header_script = await client.put(
            f"/api/v1/schema-management/schemas/{expert['id']}/script",
            headers={"X-User-Id": "user-a"},
            files={"script": ("expert.py", b"value = 1\n", "text/x-python")},
        )
        # X-User-Id 已不参与鉴权；测试环境登录身份是全局管理员。
        assert forged_header_script.status_code == 200

        system_script = await client.put(
            f"/api/v1/schema-management/schemas/{expert['id']}/script",
            headers={"X-User-Id": "schema-admin"},
            files={
                "script": (
                    "expert.py",
                    b"def transform(row):\n    return row\n",
                    "text/x-python",
                )
            },
        )
        assert system_script.status_code == 200
        assert system_script.json()["data"]["script"]["filename"] == "expert.py"

        entity_payload = {
            "schemaKey": "technology",
            "name": "Technology",
            "label": "技术",
            "description": "用户创建的技术实体",
            "properties": [
                {
                    "name": "technology_id",
                    "dataType": "string",
                    "required": True,
                    "rule": "全局唯一",
                }
            ],
            "mappings": ["technology_profile"],
        }
        created_entity = await client.post(
            "/api/v1/schema-management/schemas/entities",
            headers={"X-User-Id": "user-a"},
            json=entity_payload,
        )
        assert created_entity.status_code == 201
        entity = created_entity.json()["data"]
        assert entity["canDelete"] is True
        assert entity["canManageProperties"] is True
        assert entity["script"] is None
        assert entity["ddlStatus"] == "succeeded"
        assert "CREATE TAG IF NOT EXISTS Technology" in entity["ddlStatement"]
        locked_names = [p["name"] for p in entity["properties"] if p.get("locked")]
        assert locked_names == ["id", "name", "create_time", "update_time", "source_table"]
        assert storage.objects  # expert.py 仍在

        relation_payload = {
            "schemaKey": "uses-technology",
            "name": "USES_TECHNOLOGY",
            "label": "使用技术",
            "description": "专家使用某项技术",
            "sourceSchemaId": expert["id"],
            "targetSchemaId": entity["id"],
            "properties": [
                {"name": "source", "dataType": "string", "required": True},
                {"name": "target", "dataType": "string", "required": True},
            ],
        }
        created_relation = await client.post(
            "/api/v1/schema-management/schemas/relations",
            headers={"X-User-Id": "user-a"},
            json=relation_payload,
        )
        assert created_relation.status_code == 201
        relation = created_relation.json()["data"]
        assert relation["ddlStatus"] == "succeeded"
        assert "CREATE EDGE IF NOT EXISTS USES_TECHNOLOGY" in relation["ddlStatement"]

        forbidden_system = await client.delete(
            f"/api/v1/schema-management/schemas/{expert['id']}",
            headers={"X-User-Id": "user-a"},
        )
        assert forbidden_system.status_code == 403

        global_admin_replace = await client.put(
            f"/api/v1/schema-management/schemas/{relation['id']}/script",
            headers={"X-User-Id": "user-b"},
            files={"script": ("relation-v2.py", b"value = 2\n", "text/x-python")},
        )
        assert global_admin_replace.status_code == 200

        referenced_entity = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}",
            headers={"X-User-Id": "user-a"},
        )
        assert referenced_entity.status_code == 409

        deleted_relation = await client.delete(
            f"/api/v1/schema-management/schemas/{relation['id']}",
            headers={"X-User-Id": "user-a"},
        )
        assert deleted_relation.status_code == 200
        deleted_entity = await client.delete(
            f"/api/v1/schema-management/schemas/{entity['id']}",
            headers={"X-User-Id": "user-a"},
        )
        assert deleted_entity.status_code == 200
        assert len(storage.objects) == 1  # expert.py

    assert ddl_calls[0][0] == "entity"
    assert ddl_calls[1][0] == "relation"


@pytest.mark.asyncio
async def test_schema_workflow_script_is_registered_and_returned(
    schema_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []

    def register(
        filename, content, function_name, definition_id, name, timeout_seconds=None, category=None
    ):
        calls.append(
            {
                "filename": filename,
                "content": content,
                "function_name": function_name,
                "definition_id": definition_id,
                "name": name,
                "timeout_seconds": timeout_seconds,
                "category": category,
            }
        )
        return {"id": definition_id}

    monkeypatch.setattr(
        "service.workflow_operations.workflow_operations_service.create_python_definition",
        register,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get(
            "/api/v1/schema-management/schemas",
            params={"kind": "entity", "pageSize": 100, "includeDetails": True},
        )
        organization = next(
            item for item in listing.json()["data"]["items"] if item["name"] == "Organization"
        )
        response = await client.put(
            f"/api/v1/schema-management/schemas/{organization['id']}/script",
            headers={"X-User-Id": "schema-admin"},
            files={
                "script": (
                    "organization.py",
                    b"def workflow(payload):\n    return payload\n",
                    "text/x-python",
                )
            },
        )

    assert response.status_code == 200
    script = response.json()["data"]["script"]
    assert script["workflowDefinitionId"] == "schema-organization"
    assert script["workflowFunctionName"] == "workflow"
    assert calls[0]["timeout_seconds"] == 3600
