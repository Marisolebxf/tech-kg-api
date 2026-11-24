"""渗透 B5：批量 NLP 接口须有条数/长度上限与按用户额度，超额 429。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from biz.dependencies.auth import require_platform_actor
from biz.handler import common_capability
from infra import rate_limit


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_BACKEND", "memory")
    monkeypatch.delenv("RATE_LIMIT_COMMON_CAPABILITIES", raising=False)
    rate_limit.reset_memory_counters()
    calls = []
    monkeypatch.setattr(
        common_capability.application,
        "batch_extract_relations",
        lambda texts, method="rule": calls.append(len(texts)) or {"count": len(texts)},
    )
    monkeypatch.setattr(
        common_capability.application,
        "extract_relations",
        lambda text, method="rule": calls.append(1) or {"relations": []},
    )
    app = FastAPI()
    app.include_router(common_capability.router, prefix="/api/v1")
    user = {"id": "u1"}
    app.dependency_overrides[require_platform_actor] = lambda: SimpleNamespace(user_id=user["id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, calls, user
    rate_limit.reset_memory_counters()


async def test_batch_rejects_more_than_fifty_texts(client):
    http, calls, _ = client
    response = await http.post(
        "/api/v1/common-capabilities/relation-extraction/batch",
        json={"texts": ["任正非创立了华为技术有限公司"] * 1000},
    )
    assert response.status_code == 422
    assert calls == []


async def test_batch_rejects_oversized_text(client):
    http, calls, _ = client
    response = await http.post(
        "/api/v1/common-capabilities/relation-extraction/batch",
        json={"texts": ["长" * (common_capability.MAX_TEXT_CHARS + 1)]},
    )
    assert response.status_code == 422
    assert calls == []


async def test_quota_counts_texts_per_user_and_returns_429(client, monkeypatch):
    http, calls, user = client
    monkeypatch.setenv("RATE_LIMIT_COMMON_CAPABILITIES", "60/60")
    url = "/api/v1/common-capabilities/relation-extraction/batch"
    assert (await http.post(url, json={"texts": ["a"] * 50})).status_code == 200
    blocked = await http.post(url, json={"texts": ["a"] * 20})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert calls == [50]
    # 额度按用户隔离
    user["id"] = "u2"
    assert (await http.post(url, json={"texts": ["a"] * 20})).status_code == 200


async def test_single_extraction_is_charged_too(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setenv("RATE_LIMIT_COMMON_CAPABILITIES", "2/60")
    url = "/api/v1/common-capabilities/relation-extraction"
    for _ in range(2):
        assert (await http.post(url, json={"text": "马云创立了阿里巴巴"})).status_code == 200
    assert (await http.post(url, json={"text": "马云创立了阿里巴巴"})).status_code == 429
