"""Integration tests for entity binding API.

These tests require trs-graph-service running on localhost:8090.
Run with: pytest tests/test_entity_binding.py -v --tb=short
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestBindingAPI:
    def test_init_data(self, client):
        response = client.post("/api/v1/binding/init-data")
        assert response.status_code == 200
        data = response.json()
        assert "nodes_inserted" in data
        assert "edge_types_created" in data

    def test_execute_binding_talent_paper(self, client):
        response = client.post("/api/v1/binding/execute", json={"binding_type": "talent_paper"})
        assert response.status_code == 200
        data = response.json()
        assert data["binding_type"] == "talent_paper"
        assert data["total_candidates"] >= 0

    def test_execute_binding_talent_patent(self, client):
        response = client.post("/api/v1/binding/execute", json={"binding_type": "talent_patent"})
        assert response.status_code == 200
        data = response.json()
        assert data["binding_type"] == "talent_patent"

    def test_execute_binding_org_org(self, client):
        response = client.post("/api/v1/binding/execute", json={"binding_type": "org_org"})
        assert response.status_code == 200
        data = response.json()
        assert data["binding_type"] == "org_org"

    def test_get_stats(self, client):
        response = client.get("/api/v1/binding/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_confirmed" in data
        assert "total_candidates" in data

    def test_get_detail(self, client):
        response = client.get("/api/v1/binding/detail?binding_type=talent_paper")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_graph(self, client):
        response = client.get("/api/v1/binding/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data

    def test_binding_demo_page(self, client):
        response = client.get("/binding")
        assert response.status_code == 200

    def test_clear_bindings(self, client):
        response = client.delete("/api/v1/binding/clear?clear_data=false")
        assert response.status_code == 200
        data = response.json()
        assert "edges_deleted" in data
