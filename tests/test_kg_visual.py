"""Tests for the ECharts knowledge graph visual demo."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_kg_visual_page_served():
    response = client.get("/kg-visual")

    assert response.status_code == 200
    assert "知识图谱可视化" in response.text
    assert "const API = '/api/v1/kg-visual';" in response.text


def test_kg_visual_graph_crud_flow():
    response = client.delete("/api/v1/kg-visual/graph")
    assert response.status_code == 200
    assert response.json()["data"] == {"nodes": [], "links": []}

    response = client.post(
        "/api/v1/kg-visual/graph/node",
        json={
            "id": "A",
            "name": "",
            "category": "实体",
            "properties": {"来源": "测试"},
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["nodes"][0]["name"] == "A"

    response = client.post(
        "/api/v1/kg-visual/graph/node",
        json={"id": "B", "name": "节点B", "category": "实体", "properties": {}},
    )
    assert response.status_code == 200

    response = client.post(
        "/api/v1/kg-visual/graph/link",
        json={
            "source": "A",
            "target": "B",
            "relation": "关联",
            "properties": {"权重": 1},
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["links"][0]["relation"] == "关联"

    response = client.put(
        "/api/v1/kg-visual/graph/node/A",
        json={"properties": {"状态": "已更新"}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["nodes"][0]["properties"]["状态"] == "已更新"

    response = client.delete("/api/v1/kg-visual/graph/node/A/property/状态")
    assert response.status_code == 200
    assert "状态" not in response.json()["data"]["nodes"][0]["properties"]


def test_kg_visual_example_graph():
    response = client.get("/api/v1/kg-visual/graph/example")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["nodes"]) == 8
    assert len(data["links"]) == 8
    assert {node["category"] for node in data["nodes"]} >= {"人物", "作品"}
