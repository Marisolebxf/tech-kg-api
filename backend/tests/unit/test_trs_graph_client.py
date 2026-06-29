"""Unit tests for infra.graph_db repository and helpers."""

from __future__ import annotations

import json

import httpx
import pytest

import infra.graph_db as graph_pkg
from infra.graph_db import TRSGraphClient, close_trs_graph_client, get_trs_graph_client
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.convert import (
    _build_node_create_body,
    _parse_edge_id,
    _strip_quotes,
    _trs_edge_to_model,
    _trs_node_to_model,
)
from infra.graph_db.exceptions import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphRepoError,
    GraphRequestError,
)
from infra.graph_db.models import (
    GraphConstraintSpec,
    GraphEdge,
    GraphIndexSpec,
    GraphNode,
    GraphPagedResult,
    GraphQueryResult,
)


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(GraphConnectionError, GraphRepoError)
        assert issubclass(GraphNotFoundError, GraphRepoError)
        assert issubclass(GraphRequestError, GraphRepoError)

    def test_request_error_carries_status_and_body(self):
        err = GraphRequestError("boom", status_code=500, body="oops")
        assert err.status_code == 500
        assert err.body == "oops"


class TestModels:
    def test_node_defaults(self):
        n = GraphNode(id="1")
        assert n.id == "1"
        assert n.labels == []
        assert n.properties == {}

    def test_edge_defaults(self):
        e = GraphEdge(id="a->b@0", type="KNOWS", source_id="a", target_id="b")
        assert e.properties == {}

    def test_paged_result_fields(self):
        p = GraphPagedResult(items=[], total=0, limit=100, offset=0)
        assert p.total == 0

    def test_query_result_defaults(self):
        q = GraphQueryResult()
        assert q.records == []
        assert q.summary is None


class TestSettings:
    def test_defaults(self, monkeypatch):
        for k in (
            "TRS_GRAPH_BASE_URL",
            "TRS_GRAPH_SPACE",
            "TRS_GRAPH_API_KEY",
            "TRS_GRAPH_TIMEOUT",
        ):
            monkeypatch.delenv(k, raising=False)
        s = TRSGraphSettings.from_env()
        assert s.base_url == "http://localhost:8090"
        assert s.space == "entity_binding_demo"
        assert s.api_key is None
        assert s.timeout == 30

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://graph:8090")
        monkeypatch.setenv("TRS_GRAPH_SPACE", "tech-kg")
        monkeypatch.setenv("TRS_GRAPH_API_KEY", "secret")
        monkeypatch.setenv("TRS_GRAPH_TIMEOUT", "10")
        s = TRSGraphSettings.from_env()
        assert s.base_url == "http://graph:8090"
        assert s.space == "tech-kg"
        assert s.api_key == "secret"
        assert s.timeout == 10


class TestConvert:
    def test_node_to_model(self):
        n = _trs_node_to_model({"id": "42", "labels": ["Person"], "properties": {"name": "Alice"}})
        assert isinstance(n, GraphNode)
        assert n.id == "42"
        assert n.labels == ["Person"]
        assert n.properties == {"name": "Alice"}

    def test_node_to_model_defaults(self):
        n = _trs_node_to_model({"id": "1"})
        assert n.labels == []
        assert n.properties == {}

    def test_edge_to_model(self):
        e = _trs_edge_to_model(
            {
                "id": "a->b@0",
                "type": "KNOWS",
                "sourceId": "a",
                "targetId": "b",
                "properties": {"x": 1},
            }
        )
        assert e.type == "KNOWS"
        assert e.source_id == "a"
        assert e.target_id == "b"
        assert e.properties == {"x": 1}

    def test_build_node_create_body_no_labels(self):
        assert _build_node_create_body([], {"k": "v"}) == {
            "labels": ["Vertex"],
            "properties": {"k": "v"},
        }

    def test_build_node_create_body_no_props(self):
        assert _build_node_create_body(["Tag"]) == {"labels": ["Tag"], "properties": {}}

    def test_parse_edge_id(self):
        assert _parse_edge_id("a->b@3") == ("a", "b", 3)

    def test_parse_edge_id_no_ranking(self):
        assert _parse_edge_id("a->b") == ("a", "b", 0)

    def test_strip_quotes(self):
        assert _strip_quotes('"Person"') == "Person"
        assert _strip_quotes('""Person""') == "Person"

    def test_strip_quotes_non_string(self):
        assert _strip_quotes(5) == "5"


def _make_repo(handler, *, api_key=None):
    """Build a TRSGraphClient backed by a MockTransport handler and connect it."""
    settings = TRSGraphSettings(base_url="http://test", space="test", api_key=api_key, timeout=5)
    repo = TRSGraphClient(settings, transport=httpx.MockTransport(handler))
    repo.connect()
    return repo


def _health_ok(request):
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "UP"})
    return httpx.Response(404)


class TestConnection:
    def test_connect_sets_headers(self):
        seen = {}

        def handler(request):
            seen["headers"] = request.headers
            return _health_ok(request)

        repo = _make_repo(handler, api_key="secret")
        assert seen["headers"]["x-graph-space"] == "test"
        assert seen["headers"]["x-api-key"] == "secret"
        assert repo.is_connected()
        repo.close()

    def test_connect_health_failure_raises(self):
        def handler(request):
            return httpx.Response(503)

        settings = TRSGraphSettings(base_url="http://test", space="s")
        repo = TRSGraphClient(settings, transport=httpx.MockTransport(handler))
        with pytest.raises(GraphConnectionError):
            repo.connect()

    def test_request_before_connect_raises(self):
        repo = TRSGraphClient(TRSGraphSettings())
        with pytest.raises(GraphConnectionError):
            repo._request("GET", "/x")

    def test_request_404_raises_not_found(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        with pytest.raises(GraphNotFoundError):
            repo._request("GET", "/api/v1/nodes/1")
        repo.close()

    def test_request_500_raises_request_error(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(500, text="boom")

        repo = _make_repo(handler)
        with pytest.raises(GraphRequestError) as exc:
            repo._request("GET", "/api/v1/nodes/1")
        assert exc.value.status_code == 500
        repo.close()

    def test_request_transport_error_maps_to_connection_error(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            raise httpx.ConnectError("boom")

        repo = _make_repo(handler)
        with pytest.raises(GraphConnectionError):
            repo._request("GET", "/api/v1/nodes/1")
        repo.close()


class TestNodeCrud:
    def test_create_node(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes"
            assert request.method == "POST"
            assert json.loads(request.content) == {
                "labels": ["Person"],
                "properties": {"name": "Alice"},
            }
            return httpx.Response(
                200, json={"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
            )

        repo = _make_repo(handler)
        n = repo.create_node(["Person"], {"name": "Alice"})
        assert n.id == "1"
        repo.close()

    def test_merge_node(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/merge"
            return httpx.Response(
                200, json={"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
            )

        repo = _make_repo(handler)
        n = repo.merge_node(["Person"], {"name": "Alice"}, {"age": 30})
        assert n.properties == {"name": "Alice"}
        repo.close()

    def test_create_node_injects_vid_when_missing(self):
        """Without a vid/id/name key the client must inject one so the service
        can read the node back (otherwise the service 404s on its internal
        read-back). The first property value is promoted to the vid, matching
        the techkg natural-key-as-vid convention."""
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            seen["body"] = json.loads(request.content)
            props = seen["body"]["properties"]
            vid = props["vid"]
            return httpx.Response(200, json={"id": vid, "labels": ["Org"], "properties": props})

        repo = _make_repo(handler)
        n = repo.create_node(["Org"], {"org_id": "ENT001", "name_cn": "Acme"})
        # org_id value promoted to vid; org_id kept as a tag property
        assert seen["body"]["properties"]["vid"] == "ENT001"
        assert seen["body"]["properties"]["org_id"] == "ENT001"
        assert n.id == "ENT001"
        repo.close()

    def test_merge_node_injects_vid_from_identity(self):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            seen["body"] = json.loads(request.content)
            vid = seen["body"]["identityProps"]["vid"]
            return httpx.Response(
                200, json={"id": vid, "labels": ["Scholar"], "properties": {"scholar_id": vid}}
            )

        repo = _make_repo(handler)
        n = repo.merge_node(["Scholar"], {"scholar_id": "E10001"}, {"name_zh": "专家"})
        assert seen["body"]["identityProps"]["vid"] == "E10001"
        assert n.id == "E10001"
        repo.close()

    def test_get_node_found(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(200, json={"id": "1", "labels": ["Person"], "properties": {}})

        repo = _make_repo(handler)
        assert repo.get_node("1") is not None
        repo.close()

    def test_get_node_missing_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.get_node("999") is None
        repo.close()

    def test_get_nodes_by_label(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/label/Person"
            assert request.url.params["limit"] == "10"
            # real trs-graph-service shape: total nested under "page"
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1", "labels": ["Person"], "properties": {}}],
                    "page": {"offset": 0, "limit": 10, "total": 1, "hasNext": False},
                },
            )

        repo = _make_repo(handler)
        page = repo.get_nodes_by_label("Person", limit=10, offset=0)
        assert page.total == 1
        assert page.items[0].id == "1"
        repo.close()

    def test_get_nodes_by_label_total_exceeds_items(self):
        """total must come from page.total, not fall back to len(items)."""

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1", "labels": ["Person"], "properties": {}}],
                    "page": {"offset": 0, "limit": 1, "total": 200, "hasNext": True},
                },
            )

        repo = _make_repo(handler)
        page = repo.get_nodes_by_label("Person", limit=1)
        assert page.total == 200
        assert len(page.items) == 1
        repo.close()

    def test_find_nodes(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/find"
            return httpx.Response(200, json={"items": [], "total": 0})

        repo = _make_repo(handler)
        page = repo.find_nodes(["Person"], {"name": "Alice"})
        assert page.items == []
        repo.close()

    def test_update_node_fetches_label(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            calls.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json={"id": "1", "labels": ["Person"], "properties": {}})
            return httpx.Response(
                200, json={"id": "1", "labels": ["Person"], "properties": {"age": 30}}
            )

        repo = _make_repo(handler)
        n = repo.update_node("1", {"age": 30})
        assert ("GET", "/api/v1/nodes/1") in calls
        assert ("PUT", "/api/v1/nodes/1") in calls
        assert n.properties["age"] == 30
        repo.close()

    def test_update_node_missing_raises(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        with pytest.raises(GraphNotFoundError):
            repo.update_node("999", {"age": 30})
        repo.close()

    def test_update_node_response_without_id_merges_existing(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(
                    200, json={"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
                )
            # PUT returns a body without "id" -> triggers the fallback merge branch
            return httpx.Response(200, json={"updated": True})

        repo = _make_repo(handler)
        n = repo.update_node("1", {"age": 30})
        assert n.id == "1"
        assert n.properties == {"name": "Alice", "age": 30}
        repo.close()

    def test_delete_node(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/1"
            return httpx.Response(204)

        repo = _make_repo(handler)
        assert repo.delete_node("1") is True
        repo.close()

    def test_delete_node_missing_returns_false(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.delete_node("999") is False
        repo.close()


class TestTraversal:
    def test_get_node_edges(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/1/edges"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->2@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "2",
                        "properties": {},
                    }
                ],
            )

        repo = _make_repo(handler)
        edges = repo.get_node_edges("1", direction="both")
        assert len(edges) == 1
        repo.close()

    def test_get_neighbours(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/1/neighbours"
            return httpx.Response(200, json=[{"id": "2", "labels": ["Person"], "properties": {}}])

        repo = _make_repo(handler)
        nbrs = repo.get_neighbours("1")
        assert nbrs[0].id == "2"
        repo.close()

    def test_shortest_path_backfills_incomplete_nodes(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.url.path == "/api/v1/traversal/path/shortest":
                return httpx.Response(
                    200,
                    json={
                        "nodes": [
                            {"id": "1", "labels": [], "properties": {}},
                            {"id": "2", "labels": ["P"], "properties": {"x": 1}},
                        ],
                        "edges": [],
                    },
                )
            if request.url.path == "/api/v1/nodes/1":
                calls.append("backfill")
                return httpx.Response(
                    200, json={"id": "1", "labels": ["Person"], "properties": {"name": "A"}}
                )
            return httpx.Response(404)

        repo = _make_repo(handler)
        path = repo.shortest_path("1", "2")
        assert path is not None
        assert path.nodes[0].labels == ["Person"]
        assert "backfill" in calls
        assert path.nodes[1].properties == {"x": 1}
        repo.close()

    def test_shortest_path_missing_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.shortest_path("1", "2") is None
        repo.close()

    def test_shortest_path_passes_edgeType_param(self):
        """The traversal shortest-path endpoint expects ?edgeType= (not ?type=);
        sending the wrong name silently ignores the edge-type filter."""

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/path/shortest"
            assert request.url.params["edgeType"] == "KNOWS"
            assert "type" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {"id": "1", "labels": ["P"], "properties": {}},
                        {"id": "2", "labels": ["P"], "properties": {}},
                    ],
                    "edges": [],
                },
            )

        repo = _make_repo(handler)
        path = repo.shortest_path("1", "2", edge_type="KNOWS")
        assert path is not None and len(path.nodes) == 2
        repo.close()


class TestEdgeCrud:
    def test_create_edge(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            body = json.loads(request.content)
            assert body == {"type": "KNOWS", "sourceId": "1", "targetId": "2", "properties": {}}
            return httpx.Response(
                200,
                json={
                    "id": "1->2@0",
                    "type": "KNOWS",
                    "sourceId": "1",
                    "targetId": "2",
                    "properties": {},
                },
            )

        repo = _make_repo(handler)
        e = repo.create_edge("1", "2", "KNOWS")
        assert e.id == "1->2@0"
        repo.close()

    def test_get_edge_with_type(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/edges/1/2"
            assert request.url.params["type"] == "KNOWS"
            return httpx.Response(
                200,
                json={
                    "id": "1->2@0",
                    "type": "KNOWS",
                    "sourceId": "1",
                    "targetId": "2",
                    "properties": {},
                },
            )

        repo = _make_repo(handler)
        e = repo.get_edge("1->2@0", edge_type="KNOWS")
        assert e is not None
        repo.close()

    def test_get_edge_missing_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.get_edge("1->2@0", edge_type="KNOWS") is None
        repo.close()

    def test_update_edge_without_type_looks_up(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "1->2@0",
                            "type": "KNOWS",
                            "sourceId": "1",
                            "targetId": "2",
                            "properties": {},
                        }
                    ],
                )
            return httpx.Response(
                200,
                json={
                    "id": "1->2@0",
                    "type": "KNOWS",
                    "sourceId": "1",
                    "targetId": "2",
                    "properties": {"w": 5},
                },
            )

        repo = _make_repo(handler)
        e = repo.update_edge("1->2@0", {"w": 5})
        assert e.properties["w"] == 5
        repo.close()

    def test_delete_edge(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "1->2@0",
                            "type": "KNOWS",
                            "sourceId": "1",
                            "targetId": "2",
                            "properties": {},
                        }
                    ],
                )
            assert request.url.params["type"] == "KNOWS"
            return httpx.Response(204)

        repo = _make_repo(handler)
        assert repo.delete_edge("1->2@0") is True
        repo.close()

    def test_delete_edge_missing_returns_false(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(404)
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.delete_edge("1->2@0") is False
        repo.close()

    def test_get_edge_without_type_scans_node_edges(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/1/edges"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->3@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "3",
                        "properties": {},
                    },
                    {
                        "id": "1->2@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "2",
                        "properties": {},
                    },
                ],
            )

        repo = _make_repo(handler)
        e = repo.get_edge("1->2@0")  # no edge_type -> scan branch
        assert e is not None
        assert e.target_id == "2"
        repo.close()

    def test_get_edge_without_type_not_found_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->3@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "3",
                        "properties": {},
                    }
                ],
            )

        repo = _make_repo(handler)
        assert repo.get_edge("1->9@0") is None
        repo.close()


class TestQuery:
    def test_execute_query(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/query"
            assert json.loads(request.content) == {
                "query": "MATCH (n) RETURN n",
                "params": {"k": 1},
            }
            return httpx.Response(
                200, json={"records": [{"n": {"id": "1"}}], "summary": {"count": 1}}
            )

        repo = _make_repo(handler)
        r = repo.execute_query("MATCH (n) RETURN n", {"k": 1})
        assert r.records == [{"n": {"id": "1"}}]
        assert r.summary == {"count": 1}
        repo.close()

    def test_execute_read(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/query/read"
            return httpx.Response(200, json={"records": [], "summary": None})

        repo = _make_repo(handler)
        r = repo.execute_read("MATCH (n) RETURN n")
        assert r.records == []
        repo.close()

    def test_execute_write(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/query/write"
            return httpx.Response(200, json={"records": [], "summary": None})

        repo = _make_repo(handler)
        repo.execute_write("CREATE TAG T(name string)")
        repo.close()


class TestBatch:
    def test_batch_create_nodes(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            body = json.loads(request.content)
            assert body["labels"] == ["Person"]
            assert body["items"] == [{"name": "Alice"}, {"name": "Bob"}]
            return httpx.Response(
                200,
                json=[
                    {"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}},
                    {"id": "2", "labels": ["Person"], "properties": {"name": "Bob"}},
                ],
            )

        repo = _make_repo(handler)
        nodes = repo.batch_create_nodes([{"name": "Alice"}, {"name": "Bob"}], ["Person"])
        assert [n.id for n in nodes] == ["1", "2"]
        repo.close()

    def test_batch_create_nodes_empty_response(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=[])

        repo = _make_repo(handler)
        assert repo.batch_create_nodes([{"name": "A"}], ["Person"]) == []
        repo.close()

    def test_batch_create_edges_flattens_properties(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            body = json.loads(request.content)
            assert body["type"] == "KNOWS"
            assert body["items"][0]["sourceId"] == "1"
            assert body["items"][0]["targetId"] == "2"
            # properties flattened to top level
            assert body["items"][0]["since"] == 2020
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->2@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "2",
                        "properties": {},
                    }
                ],
            )

        repo = _make_repo(handler)
        edges = repo.batch_create_edges(
            [{"source_id": "1", "target_id": "2", "properties": {"since": 2020}}], "KNOWS"
        )
        assert len(edges) == 1
        repo.close()


class TestSchema:
    def test_create_index(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/indexes"
            assert json.loads(request.content) == {
                "label": "Person",
                "properties": ["name"],
                "unique": True,
            }
            return httpx.Response(201)

        repo = _make_repo(handler)
        repo.create_index(GraphIndexSpec(label="Person", properties=["name"], unique=True))
        repo.close()

    def test_list_indexes_strips_quotes(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[{"label": '"Person"', "properties": ['"name"'], "unique": False}],
            )

        repo = _make_repo(handler)
        indexes = repo.list_indexes()
        assert indexes[0].label == "Person"
        assert indexes[0].properties == ["name"]
        repo.close()

    def test_list_indexes_parses_bracket_list_properties(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[{"label": "Person", "properties": ['["name","age"]'], "unique": False}],
            )

        repo = _make_repo(handler)
        indexes = repo.list_indexes()
        assert indexes[0].label == "Person"
        assert indexes[0].properties == ["name", "age"]
        repo.close()

    def test_drop_index(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.method == "DELETE"
            assert request.url.params["label"] == "Person"
            assert request.url.params["properties"] == "name,age"
            return httpx.Response(204)

        repo = _make_repo(handler)
        repo.drop_index("Person", ["name", "age"])
        repo.close()

    def test_create_constraint(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert json.loads(request.content) == {
                "name": "c1",
                "label": "Person",
                "property": "name",
                "kind": "unique",
            }
            return httpx.Response(201)

        repo = _make_repo(handler)
        repo.create_constraint(GraphConstraintSpec(name="c1", label="Person", property="name"))
        repo.close()

    def test_list_constraints_strips_quotes(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[
                    {"name": '"c1"', "label": '"Person"', "property": '"name"', "kind": "unique"}
                ],
            )

        repo = _make_repo(handler)
        cs = repo.list_constraints()
        assert cs[0].name == "c1"
        assert cs[0].label == "Person"
        repo.close()

    def test_drop_constraint(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/constraints/c1"
            return httpx.Response(204)

        repo = _make_repo(handler)
        repo.drop_constraint("c1")
        repo.close()


class TestDbInfo:
    def test_node_count(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/stats/node-count"
            return httpx.Response(200, json={"count": 42})

        repo = _make_repo(handler)
        assert repo.node_count() == 42
        repo.close()

    def test_edge_count(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json={"count": 7})

        repo = _make_repo(handler)
        assert repo.edge_count() == 7
        repo.close()

    def test_edge_count_passes_edgeType_param(self):
        """The service's edge-count endpoint expects ?edgeType= (not ?type=);
        sending the wrong name makes it count ALL edges in the space."""

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/stats/edge-count"
            assert request.url.params["edgeType"] == "EMPLOYED_BY"
            assert "type" not in request.url.params
            return httpx.Response(200, json={"count": 5})

        repo = _make_repo(handler)
        assert repo.edge_count("EMPLOYED_BY") == 5
        repo.close()

    def test_labels(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=[{"Name": "Person"}, {"Name": "Tag"}])

        repo = _make_repo(handler)
        assert repo.labels() == ["Person", "Tag"]
        repo.close()

    def test_edge_types_plain_strings(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=["KNOWS", "LIKES"])

        repo = _make_repo(handler)
        assert repo.edge_types() == ["KNOWS", "LIKES"]
        repo.close()


class TestSingleton:
    def test_get_trs_graph_client_caches(self, monkeypatch):
        # Force connectable settings; patch connect/is_connected to avoid real network.
        monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
        monkeypatch.setenv("TRS_GRAPH_SPACE", "s")
        monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
        close_trs_graph_client()  # reset any prior singleton
        monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
        monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
        r1 = get_trs_graph_client()
        r2 = get_trs_graph_client()
        assert r1 is r2
        close_trs_graph_client()
        assert graph_pkg._client is None

    def test_get_trs_graph_client_resets_when_connect_fails(self, monkeypatch):
        monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
        monkeypatch.setenv("TRS_GRAPH_SPACE", "s")
        monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
        close_trs_graph_client()  # reset

        def _fail_connect(self):
            raise GraphConnectionError("service down")

        monkeypatch.setattr(TRSGraphClient, "connect", _fail_connect)
        with pytest.raises(GraphConnectionError):
            get_trs_graph_client()
        assert graph_pkg._client is None
        close_trs_graph_client()
