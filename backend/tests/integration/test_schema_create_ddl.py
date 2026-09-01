"""Schema 创建 + DDL 执行集成测试（CI 跑，graph client 被 mock）。"""

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


class _FakeGraphClient:
    def __init__(self, *, raise_on_write: bool = False) -> None:
        self.writes: list[str] = []
        self._raise = raise_on_write

    def execute_write(self, query: str) -> None:
        self.writes.append(query)
        if self._raise:
            from infra.graph_db import GraphRequestError

            raise GraphRequestError("DDL 失败：语义错误")


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
    # 关闭 provenance 自动注入，DDL 断言只覆盖用户声明的属性
    monkeypatch.setenv("SCHEMA_AUTO_PROVENANCE", "false")
    monkeypatch.setattr("service.schema_ddl.time.sleep", lambda *_args, **_kw: None)
    fake_graph = _FakeGraphClient()
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: fake_graph)
    yield engine, storage, fake_graph
    app.dependency_overrides.pop(get_workflow_session, None)
    engine.dispose()


ENTITY_PAYLOAD = {
    "schemaKey": "gadget",
    "name": "Gadget",
    "label": "小工具",
    "description": "测试实体",
    "properties": [
        {"name": "gadget_id", "dataType": "string", "required": True},
        {"name": "weight", "dataType": "double", "required": False},
    ],
    "mappings": [],
}


async def _list_expert(client: AsyncClient) -> dict:
    listing = await client.get(
        "/api/v1/schema-management/schemas",
        params={"kind": "entity", "pageSize": 100, "includeDetails": True},
    )
    return next(item for item in listing.json()["data"]["items"] if item["name"] == "Expert")


@pytest.mark.asyncio
async def test_create_entity_executes_ddl(schema_api) -> None:
    _, _, fake_graph = schema_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/schema-management/schemas/entities",
            headers={"X-User-Id": "user-a"},
            json=ENTITY_PAYLOAD,
        )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ddlStatus"] == "succeeded"
    assert data["ddlError"] is None
    # 公共必选属性（id/name/create_time/update_time/source_table）注入头部 + 用户属性
    assert data["ddlStatement"] == (
        "CREATE TAG IF NOT EXISTS Gadget("
        "id string NOT NULL, name string NOT NULL, create_time string NOT NULL, "
        "update_time string NOT NULL, source_table string NOT NULL, "
        "gadget_id string NOT NULL, weight double);"
    )
    assert fake_graph.writes == [data["ddlStatement"]]


@pytest.mark.asyncio
async def test_create_entity_ddl_failure_marks_failed(schema_api) -> None:
    _, _, fake_graph = schema_api
    fake_graph._raise = True  # noqa: SLF001
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/schema-management/schemas/entities",
            headers={"X-User-Id": "user-a"},
            json=ENTITY_PAYLOAD,
        )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ddlStatus"] == "failed"
    assert data["ddlError"] is not None
    # catalog 行已落库
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        detail = await client.get(f"/api/v1/schema-management/schemas/{data['id']}")
        assert detail.status_code == 200
        assert detail.json()["data"]["ddlStatus"] == "failed"


@pytest.mark.asyncio
async def test_create_relation_executes_ddl(schema_api) -> None:
    _, _, fake_graph = schema_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        # 创建一个目标实体
        target = await client.post(
            "/api/v1/schema-management/schemas/entities",
            headers={"X-User-Id": "user-a"},
            json={
                "schemaKey": "widget",
                "name": "Widget",
                "label": "组件",
                "properties": [{"name": "widget_id", "dataType": "string", "required": True}],
            },
        )
        assert target.status_code == 201
        target_id = target.json()["data"]["id"]

        relation_payload = {
            "schemaKey": "uses-widget",
            "name": "USES_WIDGET",
            "label": "使用组件",
            "sourceSchemaId": expert["id"],
            "targetSchemaId": target_id,
            "properties": [
                {"name": "source", "dataType": "string", "required": True},
                {"name": "target", "dataType": "string", "required": True},
            ],
        }
        response = await client.post(
            "/api/v1/schema-management/schemas/relations",
            headers={"X-User-Id": "user-a"},
            json=relation_payload,
        )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["ddlStatus"] == "succeeded"
    assert "CREATE EDGE IF NOT EXISTS USES_WIDGET" in data["ddlStatement"]
    # 至少两条 DDL：一条 TAG（Widget），一条 EDGE（USES_WIDGET）
    assert any("CREATE TAG IF NOT EXISTS Widget" in w for w in fake_graph.writes)
    assert any("CREATE EDGE IF NOT EXISTS USES_WIDGET" in w for w in fake_graph.writes)


@pytest.mark.asyncio
async def test_create_rejects_bad_data_type(schema_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/schema-management/schemas/entities",
            headers={"X-User-Id": "user-a"},
            json={
                "schemaKey": "bad-type",
                "name": "BadType",
                "label": "坏类型",
                "properties": [{"name": "id", "dataType": "varchar(10)", "required": True}],
            },
        )
    # 全局异常处理器把 RequestValidationError 包成 HTTP 200 + ApiResponse(code=422)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 422
    assert body["success"] is False
    assert "data_type" in str(body["data"])
