"""kg-open 对外查询接口测试。

不连接真实 TRSGraph / 目录库：目录与图客户端在模块级打桩，
覆盖路由注册、入参校验与三个接口的响应契约（含悬挂边端点置 null）。
"""

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

BASE_URL = "/api/v1/kg-open"

FAKE_CATALOG: dict[str, Any] = {
    "entityTypes": [{"name": "Paper", "displayName": "论文", "description": "", "properties": []}],
    "relationTypes": [
        {
            "name": "AUTHORED_BY",
            "displayName": "撰写",
            "description": "",
            "properties": [],
            "sourceType": "Paper",
            "targetType": "Person",
        }
    ],
}


def test_kg_open_routes_registered() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v1/kg-open/schema" in paths
    assert "/api/v1/kg-open/entity-types/{name}/entities" in paths
    assert "/api/v1/kg-open/relation-types/{name}/edges" in paths


def test_rejects_non_identifier_type_name() -> None:
    response = client.get(f"{BASE_URL}/entity-types/坏名字/entities")
    assert response.status_code == 400
    assert "不合法的类型名" in response.json()["detail"]


def test_rejects_limit_above_maximum() -> None:
    response = client.get(f"{BASE_URL}/entity-types/Paper/entities?limit=501")
    # 项目将参数校验异常统一包装为 HTTP 200 + 业务 code 422。
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 422
    assert body["success"] is False


def test_rejects_offset_above_maximum() -> None:
    response = client.get(f"{BASE_URL}/relation-types/CITES/edges?offset=10000001")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 422
    assert body["success"] is False


def test_entities_contract_and_relation_types(monkeypatch) -> None:
    from biz.handler import kg_open
    from infra.graph_db.models import GraphNode

    monkeypatch.setattr(kg_open, "_catalog", lambda session, space: FAKE_CATALOG)

    class FakeClient:
        def paged_nodes_by_label(self, label: str, *, limit: int, offset: int):
            return [
                GraphNode(
                    id="paper_0001",
                    labels=["Paper"],
                    properties={"name": "量子综述", "title": "量子综述"},
                )
            ]

        def label_count(self, label: str) -> int:
            return 1

    monkeypatch.setattr(kg_open, "_get_client", lambda space=None: FakeClient())

    response = client.get(f"{BASE_URL}/entity-types/Paper/entities?limit=10")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entityType"] == "Paper"
    assert data["total"] == 1
    assert data["relationTypes"] == ["AUTHORED_BY"]
    entity = data["entities"][0]
    assert entity["id"] == "paper_0001"
    assert entity["type"] == "Paper"
    assert entity["name"] == "量子综述"
    assert entity["properties"]["title"] == "量子综述"


def test_unknown_entity_type_returns_404(monkeypatch) -> None:
    from biz.handler import kg_open

    monkeypatch.setattr(
        kg_open, "_catalog", lambda session, space: {"entityTypes": [], "relationTypes": []}
    )
    response = client.get(f"{BASE_URL}/entity-types/Unknown/entities")
    assert response.status_code == 404
    assert "实体类型不存在" in response.json()["detail"]


def test_edges_fill_endpoints_and_mark_dangling_null(monkeypatch) -> None:
    from biz.handler import kg_open
    from infra.graph_db.models import GraphEdge, GraphPagedResult

    monkeypatch.setattr(kg_open, "_catalog", lambda session, space: FAKE_CATALOG)

    class FakeClient:
        def get_edges_by_type(self, edge_type: str, *, limit: int, offset: int):
            # REST page.total 实测对部分边类型恒为 0，total 应改用 SHOW STATS 口径。
            return GraphPagedResult(
                items=[
                    GraphEdge(
                        id='"paper_0001"->"paper_ref_missing"@0',
                        type="AUTHORED_BY",
                        source_id='"paper_0001"',
                        target_id="paper_ref_missing",
                        properties={"confidence": 0.9},
                    )
                ],
                total=1,
                limit=limit,
                offset=offset,
            )

        def stats_snapshot(self):
            return {"tags": {}, "edges": {"AUTHORED_BY": 184}}

        def execute_read(self, query: str):
            # TRS 定制 Nebula 的 FETCH 必须带 YIELD；端点缺失的 VID 不返回行。
            assert "FETCH PROP ON *" in query
            assert "YIELD vertex AS v" in query
            return SimpleNamespace(
                records=[
                    {
                        "v": {
                            "id": "paper_0001",
                            "labels": ["Paper"],
                            "properties": {"name": "量子综述"},
                        }
                    }
                ]
            )

    monkeypatch.setattr(kg_open, "_get_client", lambda space=None: FakeClient())

    response = client.get(f"{BASE_URL}/relation-types/AUTHORED_BY/edges?limit=10")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["relationType"] == "AUTHORED_BY"
    assert data["total"] == 184
    edge = data["edges"][0]
    assert edge["source"] == "paper_0001"
    assert edge["target"] == "paper_ref_missing"
    assert edge["properties"] == {"confidence": 0.9}
    assert edge["sourceEntity"]["id"] == "paper_0001"
    assert edge["sourceEntity"]["name"] == "量子综述"
    assert edge["targetEntity"] is None


def test_schema_endpoint_merges_catalog_with_stats(monkeypatch) -> None:
    from biz.handler import kg_open

    monkeypatch.setattr(kg_open, "_catalog", lambda session, space: FAKE_CATALOG)

    class FakeClient:
        def stats_snapshot(self):
            return {"tags": {"Paper": 42}, "edges": {"AUTHORED_BY": 7}}

    monkeypatch.setattr(kg_open, "_get_client", lambda space=None: FakeClient())

    response = client.get(f"{BASE_URL}/schema")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entityTypes"][0]["count"] == 42
    assert data["relationTypes"][0]["count"] == 7
