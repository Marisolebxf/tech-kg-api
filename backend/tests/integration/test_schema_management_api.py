from __future__ import annotations

import json
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infra.mysql import get_session
from infra.s3 import StoredObject
from main import app
from script.init_schema_management import initialize_schema_management
from service.temporal_runtime import temporal_runtime


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

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("service.schema_management.get_schema_s3_storage", lambda: storage)

    async def start(definition, payload, workflow_id=None):
        return {
            "workflowId": workflow_id or f"test-{definition['id']}",
            "runId": "schema-run-001",
            "status": "RUNNING",
        }

    monkeypatch.setattr(temporal_runtime, "start", start)
    yield engine, storage
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()


@pytest.mark.asyncio
async def test_schema_management_full_flow(schema_api) -> None:
    _, storage = schema_api
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

        forbidden_system_script = await client.put(
            f"/api/v1/schema-management/schemas/{expert['id']}/script",
            headers={"X-User-Id": "user-a"},
            files={"script": ("expert.py", b"value = 1\n", "text/x-python")},
        )
        assert forbidden_system_script.status_code == 403

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

        entity_metadata = {
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
            data={"metadata": json.dumps(entity_metadata)},
            files={
                "script": (
                    "technology.py",
                    b"def transform(row):\n    return row\n",
                    "text/x-python",
                )
            },
        )
        assert created_entity.status_code == 201
        entity = created_entity.json()["data"]
        assert entity["canDelete"] is True
        assert entity["script"]["filename"] == "technology.py"
        assert storage.objects

        execution = await client.post(
            f"/api/v1/schema-management/schemas/{entity['id']}/execute",
            headers={"X-User-Id": "user-a"},
            json={"payload": {"technology_id": "T-001"}},
        )
        assert execution.status_code == 202
        execution_data = execution.json()["data"]
        assert execution_data["taskId"]
        assert execution_data["executionId"]
        assert execution_data["workflowId"] == "test-schema-execution"
        assert execution_data["execution"]["payload"]["schemaId"] == entity["id"]
        assert execution_data["execution"]["payload"]["sha256"] == entity["script"]["sha256"]

        relation_metadata = {
            "schemaKey": "uses-technology",
            "name": "USES_TECHNOLOGY",
            "label": "使用技术",
            "description": "专家使用某项技术",
            "sourceSchemaId": expert["id"],
            "targetSchemaId": entity["id"],
            "properties": [
                {"name": "source", "dataType": "Expert ID", "required": True},
                {"name": "target", "dataType": "Technology ID", "required": True},
            ],
        }
        created_relation = await client.post(
            "/api/v1/schema-management/schemas/relations",
            headers={"X-User-Id": "user-a"},
            data={"metadata": json.dumps(relation_metadata)},
            files={
                "script": ("relation.py", b"def transform(row):\n    return row\n", "text/x-python")
            },
        )
        assert created_relation.status_code == 201
        relation = created_relation.json()["data"]

        download = await client.get(relation["script"]["downloadUrl"])
        assert download.status_code == 200
        assert download.content.startswith(b"def transform")

        forbidden_system = await client.delete(
            f"/api/v1/schema-management/schemas/{expert['id']}",
            headers={"X-User-Id": "user-a"},
        )
        assert forbidden_system.status_code == 403

        forbidden_owner = await client.delete(
            f"/api/v1/schema-management/schemas/{relation['id']}",
            headers={"X-User-Id": "user-b"},
        )
        assert forbidden_owner.status_code == 403

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
        assert len(storage.objects) == 1


@pytest.mark.asyncio
async def test_rejects_invalid_python_script(schema_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        metadata = {
            "schemaKey": "bad-script",
            "name": "BadScript",
            "label": "错误脚本",
            "properties": [{"name": "id", "dataType": "string", "required": True}],
        }
        response = await client.post(
            "/api/v1/schema-management/schemas/entities",
            headers={"X-User-Id": "user-a"},
            data={"metadata": json.dumps(metadata)},
            files={"script": ("bad.py", b"def broken(:\n", "text/x-python")},
        )
        assert response.status_code == 400
        assert "语法错误" in response.json()["msg"]
