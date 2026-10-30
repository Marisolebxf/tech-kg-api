from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from infra.graph_db.client import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphIndexPreparing
from service.expert_cooperation_achievement import ExpertCooperationAchievementService, clear_caches
from service.industry_node_top_events_business import _subgraph_sync


def test_stable_edge_pages_preserve_rank_properties_and_do_not_repeat():
    queries = []

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "UP"})
        assert request.url.path == "/api/v1/query/read"
        query = __import__("json").loads(request.content)["query"]
        queries.append(query)
        rank = 1 if "SKIP 1 LIMIT 1" in query else 0
        return httpx.Response(
            200,
            json={
                "records": [
                    {
                        "e": {
                            "id": f"a->b@{rank}",
                            "type": "KNOWS",
                            "sourceId": "a",
                            "targetId": "b",
                            "properties": {"rankMarker": rank},
                        }
                    }
                ],
                "summary": {},
            },
        )

    client = TRSGraphClient(TRSGraphSettings(space="test"), transport=httpx.MockTransport(handler))
    client.connect()
    first = client.get_node_edges("a", limit=1)
    second = client.get_node_edges("a", limit=1, offset=1)
    assert first[0].id != second[0].id
    assert second[0].properties["rankMarker"] == 1
    assert all("ORDER BY edge_src, edge_dst, edge_type, edge_rank" in q for q in queries)
    client.close()


def test_preparing_index_never_issues_partial_lookup(monkeypatch):
    monkeypatch.setattr("infra.graph_db.index_maintenance.request_indexes", lambda *a: False)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"status": "UP"})

    client = TRSGraphClient(TRSGraphSettings(), transport=httpx.MockTransport(handler))
    client.connect()
    with pytest.raises(GraphIndexPreparing):
        client.find_nodes(["Person"], {"school": "A"})
    assert calls == ["/health"]
    client.close()


def test_event_neighbors_are_batched_and_edges_have_real_endpoints():
    def node(vid):
        return SimpleNamespace(id=vid, properties={})

    edges = [
        SimpleNamespace(source_id="org", target_id=f"ev{i}", type="INVOLVED_IN", properties={})
        for i in range(100)
    ]
    client = SimpleNamespace(
        get_node=MagicMock(return_value=node("org")),
        get_node_edges=MagicMock(return_value=edges),
        get_nodes_bulk=MagicMock(
            side_effect=lambda ids: {vid: node(vid) for vid in ids if vid != "ev99"}
        ),
    )
    result = _subgraph_sync(client, "org", ["INVOLVED_IN"], 100)
    assert client.get_node.call_count == 1
    assert client.get_nodes_bulk.call_count == 1
    assert len(result["edges"]) == 99
    ids = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in result["edges"])


def test_achievement_filters_before_limit_and_reads_past_first_edge_page():
    clear_caches()

    class Graph:
        _settings = SimpleNamespace(space="test")

        def __init__(self):
            self.offsets = []
            self.bulk_calls = 0

        def get_node(self, vid):
            assert vid in ("S1", "S2"), "Achievement details must use batch reads"
            return SimpleNamespace(id=vid, labels=["Person"], properties={"name": vid})

        def get_node_edges(self, vid, *, limit, offset=0, **kwargs):
            if vid not in ("S1", "S2"):
                return []
            self.offsets.append(offset)
            edges = [
                SimpleNamespace(
                    id=f"P{i:04}->{vid}@0",
                    source_id=f"P{i:04}",
                    target_id=vid,
                    type="AUTHORED_BY",
                    properties={},
                )
                for i in range(501)
            ]
            return edges[offset : offset + limit]

        def get_nodes_bulk(self, ids):
            self.bulk_calls += 1
            return {
                vid: SimpleNamespace(
                    id=vid,
                    labels=["Paper"],
                    properties={"title": vid, "year": "2024" if vid == "P0500" else "2010"},
                )
                for vid in ids
            }

    graph = Graph()
    svc = ExpertCooperationAchievementService()
    svc._client = lambda: graph
    result = svc.query(
        source_expert_id="S1",
        target_expert_id="S2",
        achievement_types=["paper"],
        limit_per_type=1,
        time_range_start="2024",
        time_range_end="2024",
    )
    assert [item["id"] for item in result["items"]] == ["P0500"]
    assert 500 in graph.offsets
    assert graph.bulk_calls == 4
    clear_caches()


def test_explain_scopes_the_entire_plan_including_use():
    captured = []

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "UP"})
        captured.append(__import__("json").loads(request.content)["query"])
        return httpx.Response(200, json={"records": [], "summary": {}})

    client = TRSGraphClient(TRSGraphSettings(space="dev"), transport=httpx.MockTransport(handler))
    client.connect()
    client.execute_explain("LOOKUP ON Person YIELD id(vertex) AS vid")
    assert captured == ["EXPLAIN { USE dev; LOOKUP ON Person YIELD id(vertex) AS vid; }"]
    client.close()


def test_event_two_edge_types_share_one_neighbor_batch():
    def node(vid):
        return SimpleNamespace(id=vid, properties={})

    def edge_page(vid, edge_type, **kwargs):
        return [
            SimpleNamespace(
                source_id=vid, target_id=f"{edge_type}{i}", type=edge_type, properties={}
            )
            for i in range(50)
        ]

    client = SimpleNamespace(
        get_node=MagicMock(return_value=node("org")),
        get_node_edges=MagicMock(side_effect=edge_page),
        get_nodes_bulk=MagicMock(side_effect=lambda ids: {vid: node(vid) for vid in ids}),
    )
    result = _subgraph_sync(client, "org", ["INVOLVED_IN", "HAS_NEWS"], 50)
    assert len(result["nodes"]) == 101 and len(result["edges"]) == 100
    assert (
        client.get_node.call_count
        + client.get_node_edges.call_count
        + client.get_nodes_bulk.call_count
        == 4
    )


def test_achievement_does_not_drop_leads_with_same_endpoints_and_rank():
    clear_caches()

    class Graph:
        _settings = SimpleNamespace(space="test")

        def get_node(self, vid):
            return SimpleNamespace(id=vid, labels=["Person"], properties={"name": vid})

        def get_node_edges(self, vid, **kwargs):
            if vid not in ("S1", "S2"):
                return []
            return [
                SimpleNamespace(
                    id=f"P->{vid}@0", source_id="P", target_id=vid, type=t, properties={}
                )
                for t in ("HAS_PARTICIPANT", "LEADS")
            ]

        def get_nodes_bulk(self, ids):
            return {
                v: SimpleNamespace(
                    id=v, labels=["Project"], properties={"title": v, "year": "2024"}
                )
                for v in ids
            }

    svc = ExpertCooperationAchievementService()
    svc._client = lambda: Graph()
    result = svc.query(source_expert_id="S1", target_expert_id="S2", achievement_types=["project"])
    assert all(e["edgeType"] == "LEADS" for e in result["items"][0]["expertRelations"])
    clear_caches()


def test_event_optional_missing_edge_type_does_not_hide_other_events():
    from infra.graph_db.exceptions import GraphRequestError

    def page(vid, edge_type, **kwargs):
        if edge_type == "HAS_NEWS":
            raise GraphRequestError("Edge HAS_NEWS does not exist", status_code=400)
        return [SimpleNamespace(source_id=vid, target_id="event", type=edge_type, properties={})]

    def node(vid):
        return SimpleNamespace(id=vid, properties={})

    client = SimpleNamespace(
        get_node=lambda vid: node(vid),
        get_node_edges=page,
        get_nodes_bulk=lambda ids: {vid: node(vid) for vid in ids},
    )
    result = _subgraph_sync(client, "org", ["INVOLVED_IN", "HAS_NEWS"], 5)
    assert len(result["edges"]) == 1 and len(result["nodes"]) == 2
