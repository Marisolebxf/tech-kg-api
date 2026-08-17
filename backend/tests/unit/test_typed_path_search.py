from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from biz.handler import graph_search
from infra.graph_db.models import GraphNode

app = FastAPI()
app.include_router(graph_search.router, prefix="/api/v1")
client = TestClient(app)
ENDPOINT = "/api/v1/graph-search/paths/search"


def _payload() -> dict:
    return {
        "sourceId": "person_A",
        "targetId": "person_B",
        "steps": [
            {
                "edgeType": "AUTHORED_BY",
                "direction": "in",
                "targetLabel": "Paper",
                "targetFilters": [
                    {
                        "property": "publication_year",
                        "operator": "gte",
                        "value": "2021",
                    }
                ],
            },
            {
                "edgeType": "AUTHORED_BY",
                "direction": "out",
                "targetLabel": "Person",
            },
        ],
        "limit": 20,
        "offset": 0,
        "space": "dev",
    }


def test_typed_path_query_contains_direction_type_and_filter() -> None:
    body = graph_search.TypedPathSearchRequest(**_payload())

    query = graph_search._build_typed_path_query(body)

    assert "(n0)<-[e0:`AUTHORED_BY`]-(n1:`Paper`)" in query
    assert "(n1:`Paper`)-[e1:`AUTHORED_BY`]->(n2:`Person`)" in query
    assert 'n1.`Paper`.`publication_year` >= "2021"' in query
    assert 'id(n2) == "person_B"' in query
    assert "SKIP 0 LIMIT 20" in query


def test_typed_path_api_returns_all_path_parts(monkeypatch) -> None:
    class FakeGraphClient:
        def get_node(self, node_id):
            return GraphNode(
                id=node_id,
                labels=["Person"],
                properties={"name_zh": "专家A"},
            )

        def execute_read(self, query):
            if "count(*) AS total" in query:
                return SimpleNamespace(records=[{"total": 1}])
            return SimpleNamespace(
                records=[
                    {
                        "node_0_id": "person_A",
                        "node_0_properties": {"name_zh": "专家A"},
                        "node_1_id": "paper_1",
                        "node_1_properties": {"publication_year": "2023"},
                        "node_2_id": "person_B",
                        "node_2_properties": {"name_zh": "专家B"},
                        "edge_0_properties": {"citations": 12},
                        "edge_0_rank": 0,
                        "edge_1_properties": {"citations": 12},
                        "edge_1_rank": 0,
                    }
                ]
            )

    monkeypatch.setattr(graph_search, "_get_client", lambda space=None: FakeGraphClient())

    response = client.post(ENDPOINT, json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    path = body["data"]["items"][0]
    assert [node["id"] for node in path["nodes"]] == [
        "person_A",
        "paper_1",
        "person_B",
    ]
    assert path["edges"][0]["source"] == "paper_1"
    assert path["edges"][0]["target"] == "person_A"
    assert path["edges"][1]["source"] == "paper_1"
    assert path["edges"][1]["target"] == "person_B"


def test_typed_path_api_rejects_unsafe_identifier() -> None:
    payload = _payload()
    payload["steps"][0]["edgeType"] = "AUTHORED_BY); DELETE VERTEX"

    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422
    assert "String should match pattern" in response.text
