"""独立 ASGI 路由测试：覆盖真实请求校验与返回契约，不连接目录库或图库。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from biz.dependencies.kg_open_auth import KgOpenContext, require_kg_open_identity
from biz.handler import kg_open
from infra.graph_db.exceptions import GraphRequestError
from infra.workflow_mysql import get_workflow_session
from service.external_api_client import ExternalClientIdentity

BASE_URL = "/api/v1/kg-open"
CATALOG = {
    "entityTypes": [{"name": "Paper", "properties": [{"name": "title", "type": "string"}]}],
    "relationTypes": [
        {"name": "AUTHORED_BY", "sourceType": "Paper", "targetType": "Person", "properties": []}
    ],
}
VERTEX = {"id": "paper/1", "labels": ["Paper"], "properties": {"title": "量子综述"}}
EDGE = {
    "e": {"type": "AUTHORED_BY", "properties": {"confidence": 0.9}},
    "src": "paper/1",
    "dst": "missing",
    "edge_rank": 4,
}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(kg_open.router, prefix="/api/v1")
    app.dependency_overrides[require_kg_open_identity] = lambda: KgOpenContext(
        ExternalClientIdentity("partner"), "shared", True
    )
    app.dependency_overrides[get_workflow_session] = lambda: object()

    # 与 main.py 的统一参数错误响应保持一致。
    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"code": 422, "success": False, "data": None, "msg": "参数错误"})

    monkeypatch.setattr(kg_open, "_catalog", lambda session, space: deepcopy(CATALOG))

    class Client:
        def execute_read(self, query, **kwargs):
            return SimpleNamespace(
                records=[EDGE]
                if "LOOKUP ON `AUTHORED_BY`" in query or query.startswith("GO ")
                else [{"v": VERTEX}]
            )

        def stats_snapshot(self):
            return {"tags": {"Paper": 42}, "edges": {"AUTHORED_BY": 184}}

    monkeypatch.setattr(kg_open, "_get_client", lambda space: Client())
    with TestClient(app) as test_client:
        yield test_client


def test_three_routes_registered(client):
    assert len(kg_open.router.routes) == 3
    assert client.get(BASE_URL + "/schema").json()["data"]["entityTypes"][0]["count"] == 42


@pytest.mark.parametrize(
    "path", ["/entity-types/坏名字/entities", "/entity-types/Paper;DROP/entities"]
)
def test_rejects_non_identifier_type_name(client, path):
    assert client.get(BASE_URL + path).status_code == 400


@pytest.mark.parametrize("query", ["limit=501", "offset=10000001", "limit=0"])
def test_rejects_bad_pagination(client, query):
    response = client.get(BASE_URL + "/entity-types/Paper/entities?" + query)
    assert response.status_code == 200
    assert response.json()["code"] == 422 and not response.json()["success"]


def test_entities_contract_and_fixed_space(client):
    response = client.get(
        BASE_URL + "/entity-types/Paper/entities?space=private",
        headers={"X-Graph-Space": "private"},
    )
    data = response.json()["data"]
    assert data["space"] == "shared"
    assert data["total"] == 42 and data["totalIsEstimate"]
    assert data["relationTypes"] == ["AUTHORED_BY"]
    assert data["entities"][0]["name"] == "量子综述"
    assert data["entities"][0]["types"] == ["Paper"]
    assert data["hasMore"] is False and data["nextCursor"] == ""


def test_unknown_entity_type_returns_404(client):
    assert client.get(BASE_URL + "/entity-types/Unknown/entities").status_code == 404


def test_edges_preserve_parallel_edge_key_and_dangling_endpoint(client):
    data = client.get(BASE_URL + "/relation-types/AUTHORED_BY/edges").json()["data"]
    edge = data["edges"][0]
    assert (edge["source"], edge["target"], edge["rank"]) == ("paper/1", "missing", 4)
    assert edge["sourceEntity"]["id"] == "paper/1" and edge["targetEntity"] is None
    assert edge["properties"]["confidence"] == 0.9
    assert data["total"] == 184


def test_schema_without_stats_and_index_failure(client, monkeypatch):
    class NoStats:
        def stats_snapshot(self):
            raise GraphRequestError("no any stats info", status_code=400)

        def execute_read(self, query, **kwargs):
            raise GraphRequestError("There is no index to use", status_code=400)

    monkeypatch.setattr(kg_open, "_get_client", lambda space: NoStats())
    data = client.get(BASE_URL + "/schema").json()["data"]
    assert data["statsAvailable"] is False and data["entityTypes"][0]["count"] == -1
    assert client.get(BASE_URL + "/entity-types/Paper/entities").status_code == 503
