"""渗透 B4：外部按属性搜索只允许已建索引的属性，业务回环不受限；错误不回显内部指标。"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from biz.dependencies.auth import require_platform_actor
from biz.handler import graph_search
from infra import rate_limit
from infra.graph_db.exceptions import GraphConnectionError, GraphRequestError, public_graph_error
from service.business_access import business_graph_app


class FakeClient:
    def __init__(self):
        self.find_calls = []
        self.index_queries = 0

    def execute_read(self, query, params=None, *, timeout=None):
        assert query == "SHOW TAG INDEXES"
        self.index_queries += 1
        return SimpleNamespace(
            records=[
                {"Index Name": "ix_paper", "By Tag": "Paper", "Columns": []},
                {"Index Name": "paper_title", "By Tag": "Paper", "Columns": ["title", "year"]},
                {"Index Name": "person_org", "By Tag": "Person", "Columns": ["scholar_org"]},
            ]
        )

    def find_nodes(self, labels, properties, *, limit=100, offset=0):
        self.find_calls.append((labels, properties))
        return SimpleNamespace(items=[])


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_BACKEND", "memory")
    monkeypatch.delenv("RATE_LIMIT_GRAPH_NODE_SEARCH", raising=False)
    rate_limit.reset_memory_counters()
    graph_search._indexed_props_cache.clear()
    client = FakeClient()
    monkeypatch.setattr(graph_search, "_get_client", lambda space=None: client)
    monkeypatch.setattr(graph_search, "_ensure_space_access", lambda actor, space: None)
    app = FastAPI()
    app.include_router(graph_search.router, prefix="/api/v1")
    app.dependency_overrides[require_platform_actor] = lambda: SimpleNamespace(
        user_id="u1", is_admin=False
    )
    yield app, client
    graph_search._indexed_props_cache.clear()
    rate_limit.reset_memory_counters()


async def _search(app, body, *, internal=False, label="Paper"):
    transport = httpx.ASGITransport(app=business_graph_app(app) if internal else app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.post(
            "/api/v1/graph-search/nodes/search",
            params={"label": label, "space": "dev", "limit": 3},
            json=body,
        )


async def test_unindexed_property_rejected_before_graph_scan(fake):
    app, client = fake
    response = await _search(app, {"doi": "10.1000/i777-doi-00"})
    assert response.status_code == 400
    assert "doi" in response.json()["detail"]
    assert "title" in response.json()["detail"]
    assert client.find_calls == []


async def test_leading_index_column_allowed_and_index_list_cached(fake):
    app, client = fake
    assert (await _search(app, {"title": "x"})).status_code == 200
    assert (await _search(app, {"title": "y"})).status_code == 200
    assert client.index_queries == 1
    # 复合索引的非首列单独过滤仍会全扫
    assert (await _search(app, {"year": 2020})).status_code == 400
    assert len(client.find_calls) == 2


@pytest.mark.parametrize("body", [{"title": {"$ne": 1}}, {"title": [1]}, {"bad-name": "x"}])
async def test_non_scalar_or_malformed_filters_rejected(fake, body):
    app, client = fake
    assert (await _search(app, body)).status_code == 400
    assert client.find_calls == []


async def test_internal_business_loopback_keeps_existing_behaviour(fake):
    app, client = fake
    assert (
        await _search(app, {"name_zh": "张三"}, internal=True, label="Person")
    ).status_code == 200
    assert client.find_calls == [(["Person"], {"name_zh": "张三"})]
    assert client.index_queries == 0


async def test_external_search_is_rate_limited(fake, monkeypatch):
    app, _ = fake
    monkeypatch.setenv("RATE_LIMIT_GRAPH_NODE_SEARCH", "2/60")
    for _ in range(2):
        assert (await _search(app, {"title": "x"})).status_code == 200
    assert (await _search(app, {"title": "x"})).status_code == 429


@pytest.mark.parametrize(
    "exc,status,forbidden",
    [
        (
            GraphRequestError(
                "POST /api/v1/query/read -> 500: Query execution failed: use space failed: "
                "Used memory hits the high watermark(0.800000) of total system memory",
                status_code=500,
            ),
            503,
            ("watermark", "/api/v1/query/read", "0.8"),
        ),
        (GraphConnectionError("Request failed: POST http://10.0.0.5:8090/x"), 503, ("10.0.0.5",)),
        (
            GraphRequestError(
                "POST /api/v1/query/read -> 400: SyntaxError: near `RETURN'", status_code=400
            ),
            400,
            ("/api/v1/query/read",),
        ),
    ],
)
def test_public_graph_error_hides_internal_details(exc, status, forbidden):
    message, code = public_graph_error(exc)
    assert code == status
    for fragment in forbidden:
        assert fragment not in message
