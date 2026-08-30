"""Schema 脚本上传 + LLM 安全校验 SSE 端点集成测试（CI 跑，LLM 被 mock）。"""

from __future__ import annotations

import json
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


class _FakeLLM:
    def __init__(self, response: str | None) -> None:
        self._response = response

    def synthesize(self, prompt: str, max_tokens: int = 2048) -> str | None:
        return self._response


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
    yield engine, storage
    app.dependency_overrides.pop(get_workflow_session, None)
    engine.dispose()


def _set_llm(monkeypatch, response: str | None) -> _FakeLLM:
    fake = _FakeLLM(response)
    monkeypatch.setattr("service.schema_management.get_llm_client", lambda: fake)
    return fake


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: ") :]))
    return events


async def _verify(client: AsyncClient, schema_id: str, user_id: str, filename: str, data: bytes):
    return await client.post(
        f"/api/v1/schema-management/schemas/{schema_id}/script/verify",
        headers={"X-User-Id": user_id},
        files={"script": (filename, data, "text/x-python")},
    )


async def _list_expert(client: AsyncClient) -> dict:
    listing = await client.get(
        "/api/v1/schema-management/schemas",
        params={"kind": "entity", "pageSize": 100, "includeDetails": True},
    )
    return next(item for item in listing.json()["data"]["items"] if item["name"] == "Expert")


BENIGN_SCRIPT = b"def transform(row):\n    return row\n"
DANGEROUS_SCRIPT = b"import os\nos.system('rm -rf /')\n"


@pytest.mark.asyncio
async def test_verify_success_saves_script(schema_api, monkeypatch) -> None:
    _set_llm(monkeypatch, '{"safe": true, "issues": [], "summary": "安全"}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        response = await _verify(client, expert["id"], "schema-admin", "expert.py", BENIGN_SCRIPT)
        assert response.status_code == 200
        events = _parse_sse(response.text)

    types = [e["type"] for e in events]
    assert types[-1] == "success"
    stages = [e.get("stage") for e in events if e["type"] == "progress"]
    assert stages == ["syntax", "llm", "saving"]
    success_event = next(e for e in events if e["type"] == "success")
    assert success_event["script"]["filename"] == "expert.py"
    assert success_event["script"]["sizeBytes"] == len(BENIGN_SCRIPT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        content = await client.get(
            f"/api/v1/schema-management/schemas/{expert['id']}/script/content"
        )
        assert content.status_code == 200
        assert content.json()["data"]["content"].startswith("def transform")


@pytest.mark.asyncio
async def test_verify_unsafe_not_saved(schema_api, monkeypatch) -> None:
    _set_llm(
        monkeypatch,
        '{"safe": false, "issues": ["使用 os.system"], "summary": "危险脚本"}',
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        response = await _verify(client, expert["id"], "schema-admin", "evil.py", DANGEROUS_SCRIPT)
        assert response.status_code == 200
        events = _parse_sse(response.text)

    types = [e["type"] for e in events]
    assert "success" not in types
    assert types[-1] == "error"
    err = events[-1]
    assert err["stage"] == "llm"
    assert err["issues"] == ["使用 os.system"]


@pytest.mark.asyncio
async def test_verify_llm_unavailable(schema_api, monkeypatch) -> None:
    monkeypatch.setattr("service.schema_management.get_llm_client", lambda: None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        response = await _verify(client, expert["id"], "schema-admin", "expert.py", BENIGN_SCRIPT)
        assert response.status_code == 200
        events = _parse_sse(response.text)

    err = events[-1]
    assert err["type"] == "error"
    assert err["stage"] == "llm"
    assert "LLM 安全校验服务不可用" in err["message"]


@pytest.mark.asyncio
async def test_verify_syntax_error(schema_api, monkeypatch) -> None:
    _set_llm(monkeypatch, '{"safe": true, "issues": [], "summary": "ok"}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        response = await _verify(client, expert["id"], "schema-admin", "bad.py", b"def broken(:\n")
        assert response.status_code == 200
        events = _parse_sse(response.text)

    err = events[-1]
    assert err["type"] == "error"
    assert err["stage"] == "syntax"
    assert "语法错误" in err["message"]


@pytest.mark.asyncio
async def test_verify_ignores_forged_user_header_for_authenticated_admin(
    schema_api, monkeypatch
) -> None:
    _set_llm(monkeypatch, '{"safe": true, "issues": [], "summary": "ok"}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        response = await _verify(client, expert["id"], "user-a", "expert.py", BENIGN_SCRIPT)
        assert response.status_code == 200
        events = _parse_sse(response.text)

    assert events[-1]["type"] == "success"


@pytest.mark.asyncio
async def test_verify_schema_not_found_returns_404(schema_api, monkeypatch) -> None:
    _set_llm(monkeypatch, '{"safe": true, "issues": [], "summary": "ok"}')
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _verify(
            client, "nonexistent-id", "schema-admin", "expert.py", BENIGN_SCRIPT
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_script_content_404_when_no_script(schema_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        response = await client.get(
            f"/api/v1/schema-management/schemas/{expert['id']}/script/content"
        )
        assert response.status_code == 404
