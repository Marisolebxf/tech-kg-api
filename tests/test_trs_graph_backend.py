"""Unit tests for the TRS Graph backend."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from graph_db.backends.trs_graph_backend import (
    TRSGraphDatabase,
    TRSTransaction,
    _build_node_create_body,
    _parse_edge_id,
    _trs_edge_to_model,
    _trs_node_to_model,
)
from graph_db.models import Edge, Node


# ---------------------------------------------------------------------------
# Conversion helper tests
# ---------------------------------------------------------------------------

class TestTrsNodeToModel:
    def test_basic_conversion(self):
        data = {"id": "42", "labels": ["Person"], "properties": {"name": "Alice", "age": 30}}
        node = _trs_node_to_model(data)
        assert isinstance(node, Node)
        assert node.id == "42"
        assert node.labels == ["Person"]
        assert node.properties == {"name": "Alice", "age": 30}

    def test_missing_labels_defaults_empty(self):
        data = {"id": "1", "properties": {}}
        node = _trs_node_to_model(data)
        assert node.labels == []

    def test_missing_properties_defaults_empty(self):
        data = {"id": "1", "labels": ["Tag"]}
        node = _trs_node_to_model(data)
        assert node.properties == {}

    def test_multiple_labels(self):
        data = {"id": "99", "labels": ["Person", "Employee"], "properties": {}}
        node = _trs_node_to_model(data)
        assert node.labels == ["Person", "Employee"]


class TestTrsEdgeToModel:
    def test_basic_conversion(self):
        data = {
            "id": "src->dst@0",
            "type": "KNOWS",
            "sourceId": "src",
            "targetId": "dst",
            "properties": {"since": 2020},
        }
        edge = _trs_edge_to_model(data)
        assert isinstance(edge, Edge)
        assert edge.id == "src->dst@0"
        assert edge.type == "KNOWS"
        assert edge.source_id == "src"
        assert edge.target_id == "dst"
        assert edge.properties == {"since": 2020}

    def test_missing_properties_defaults_empty(self):
        data = {"id": "a->b@1", "type": "FOLLOWS", "sourceId": "a", "targetId": "b"}
        edge = _trs_edge_to_model(data)
        assert edge.properties == {}


class TestBuildNodeCreateBody:
    def test_single_label(self):
        body = _build_node_create_body(["Person"], {"name": "Alice"})
        assert body["labels"] == ["Person"]
        assert body["properties"] == {"name": "Alice"}

    def test_multiple_labels(self):
        body = _build_node_create_body(["Person", "Employee"], {"name": "Bob"})
        assert body["labels"] == ["Person", "Employee"]
        assert body["properties"] == {"name": "Bob"}

    def test_no_labels(self):
        body = _build_node_create_body([], {"key": "val"})
        assert body["labels"] == ["Vertex"]
        assert body["properties"] == {"key": "val"}

    def test_no_properties(self):
        body = _build_node_create_body(["Tag"])
        assert body["labels"] == ["Tag"]
        assert body["properties"] == {}


class TestParseEdgeId:
    def test_standard_format(self):
        src, dst, rank = _parse_edge_id("node1->node2@3")
        assert src == "node1"
        assert dst == "node2"
        assert rank == 3

    def test_zero_ranking(self):
        src, dst, rank = _parse_edge_id("a->b@0")
        assert src == "a"
        assert dst == "b"
        assert rank == 0

    def test_no_ranking_defaults_zero(self):
        src, dst, rank = _parse_edge_id("a->b")
        assert src == "a"
        assert dst == "b"
        assert rank == 0


# ---------------------------------------------------------------------------
# Connection lifecycle tests
# ---------------------------------------------------------------------------

def _make_mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class TestTRSGraphDatabaseConnect:
    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_connect_creates_client(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase("http://localhost:8090", "test_space")
        db.connect()

        mock_client_cls.assert_called_once_with(
            base_url="http://localhost:8090",
            headers={"X-Graph-Space": "test_space"},
            timeout=30,
        )
        mock_client.get.assert_called_once_with("/health")

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_connect_idempotent(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()
        db.connect()  # second call should be no-op

        assert mock_client_cls.call_count == 1


class TestTRSGraphDatabaseClose:
    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_close_destroys_client(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()
        db.close()

        mock_client.close.assert_called_once()
        assert db._client is None

    def test_close_when_not_connected(self):
        db = TRSGraphDatabase()
        db.close()  # should not raise


class TestTRSGraphDatabaseIsConnected:
    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_connected_when_healthy(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()
        assert db.is_connected() is True

    def test_not_connected_when_client_none(self):
        db = TRSGraphDatabase()
        assert db.is_connected() is False

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_not_connected_on_http_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()

        # Simulate health check failure
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        assert db.is_connected() is False


class TestRequestNotConnected:
    def test_request_raises_when_not_connected(self):
        db = TRSGraphDatabase()
        with pytest.raises(RuntimeError, match="Not connected"):
            db._request("GET", "/api/v1/nodes")


# ---------------------------------------------------------------------------
# Transaction tests
# ---------------------------------------------------------------------------

class TestTRSTransaction:
    def test_commit_sets_flag(self):
        db = TRSGraphDatabase()
        tx = TRSTransaction(db)
        tx.commit()
        assert tx._committed is True

    def test_rollback_clears_queue(self):
        db = TRSGraphDatabase()
        tx = TRSTransaction(db)
        tx.rollback()
        assert tx._rolled_back is True

    def test_context_manager_exit_on_exception(self):
        db = TRSGraphDatabase()
        tx = TRSTransaction(db)
        with pytest.raises(ValueError, match="test error"):
            with tx:
                raise ValueError("test error")
        assert tx._rolled_back is True

    def test_context_manager_normal_exit(self):
        db = TRSGraphDatabase()
        tx = TRSTransaction(db)
        with tx:
            pass
        assert tx._rolled_back is False


# ---------------------------------------------------------------------------
# CRUD operation tests (with mocked HTTP)
# ---------------------------------------------------------------------------

class TestCRUDOperations:
    def _setup_db(self, mock_client_cls, response_data=None, status_code=200):
        """Helper to set up a connected TRSGraphDatabase with a mock client."""
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client.request.return_value = _make_mock_response(
            status_code, response_data or {}
        )
        mock_client_cls.return_value = mock_client
        db = TRSGraphDatabase()
        db.connect()
        return db, mock_client

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_create_node(self, mock_client_cls):
        node_data = {"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
        db, mock_client = self._setup_db(mock_client_cls, node_data)

        node = db.create_node(["Person"], {"name": "Alice"})
        assert isinstance(node, Node)
        assert node.id == "1"
        assert node.labels == ["Person"]

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_get_node_found(self, mock_client_cls):
        node_data = {"id": "42", "labels": ["Tag"], "properties": {}}
        db, mock_client = self._setup_db(mock_client_cls, node_data)

        node = db.get_node("42")
        assert node is not None
        assert node.id == "42"

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_get_node_not_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()

        # For get_node, _request is called which uses client.request
        not_found_resp = _make_mock_response(404)
        mock_client.request.return_value = not_found_resp

        node = db.get_node("missing")
        assert node is None

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_create_edge(self, mock_client_cls):
        edge_data = {
            "id": "a->b@0",
            "type": "KNOWS",
            "sourceId": "a",
            "targetId": "b",
            "properties": {},
        }
        db, mock_client = self._setup_db(mock_client_cls, edge_data)

        edge = db.create_edge("a", "b", "KNOWS")
        assert isinstance(edge, Edge)
        assert edge.type == "KNOWS"

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_delete_node_returns_true(self, mock_client_cls):
        db, mock_client = self._setup_db(mock_client_cls)

        result = db.delete_node("1")
        assert result is True

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_delete_node_not_found_returns_false(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()

        not_found_resp = _make_mock_response(404)
        mock_client.request.return_value = not_found_resp

        result = db.delete_node("missing")
        assert result is False

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_execute_query(self, mock_client_cls):
        query_data = {"records": [{"name": "Alice"}], "summary": None}
        db, mock_client = self._setup_db(mock_client_cls, query_data)

        result = db.execute_query("MATCH (n) RETURN n.name")
        assert result.records == [{"name": "Alice"}]

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_labels_with_dict_items(self, mock_client_cls):
        labels_data = {"items": [{"Name": "Person"}, {"Name": "Company"}]}
        db, mock_client = self._setup_db(mock_client_cls, labels_data)

        result = db.labels()
        assert result == ["Person", "Company"]

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_labels_with_string_items(self, mock_client_cls):
        labels_data = {"items": ["Person", "Company"]}
        db, mock_client = self._setup_db(mock_client_cls, labels_data)

        result = db.labels()
        assert result == ["Person", "Company"]

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_edge_types_with_dict_items(self, mock_client_cls):
        types_data = {"items": [{"Name": "KNOWS"}, {"Name": "WORKS_FOR"}]}
        db, mock_client = self._setup_db(mock_client_cls, types_data)

        result = db.edge_types()
        assert result == ["KNOWS", "WORKS_FOR"]

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_node_count(self, mock_client_cls):
        db, mock_client = self._setup_db(mock_client_cls, {"count": 42})

        result = db.node_count()
        assert result == 42

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_edge_count(self, mock_client_cls):
        db, mock_client = self._setup_db(mock_client_cls, {"count": 10})

        result = db.edge_count()
        assert result == 10

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_shortest_path_found(self, mock_client_cls):
        path_data = {
            "nodes": [
                {"id": "a", "labels": ["Person"], "properties": {}},
                {"id": "b", "labels": ["Person"], "properties": {}},
            ],
            "edges": [
                {"id": "a->b@0", "type": "KNOWS", "sourceId": "a", "targetId": "b", "properties": {}},
            ],
        }
        db, mock_client = self._setup_db(mock_client_cls, path_data)

        path = db.shortest_path("a", "b")
        assert path is not None
        assert len(path.nodes) == 2
        assert len(path.edges) == 1

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_shortest_path_not_found(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()

        not_found_resp = _make_mock_response(404)
        mock_client.request.return_value = not_found_resp

        path = db.shortest_path("a", "b")
        assert path is None


# ---------------------------------------------------------------------------
# Schema management tests
# ---------------------------------------------------------------------------

class TestSchemaManagement:
    def _setup_db(self, mock_client_cls, response_data=None, status_code=200):
        mock_client = MagicMock()
        mock_client.get.return_value = _make_mock_response(200, {"status": "UP"})
        mock_client.request.return_value = _make_mock_response(
            status_code, response_data or {}
        )
        mock_client_cls.return_value = mock_client
        db = TRSGraphDatabase()
        db.connect()
        return db, mock_client

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_create_index(self, mock_client_cls):
        from graph_db.models import IndexSpec

        db, mock_client = self._setup_db(mock_client_cls)
        spec = IndexSpec(label="Person", properties=["name"], unique=False)
        db.create_index(spec)
        # Verify the request was made (no exception means success)

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_list_indexes(self, mock_client_cls):
        index_data = {
            "items": [
                {"label": "Person", "properties": ["name"], "unique": False},
                {"label": "Company", "properties": ["id"], "unique": True},
            ]
        }
        db, mock_client = self._setup_db(mock_client_cls, index_data)

        indexes = db.list_indexes()
        assert len(indexes) == 2
        assert indexes[0].label == "Person"
        assert indexes[1].unique is True

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_list_constraints(self, mock_client_cls):
        constraint_data = {
            "items": [
                {"name": "uniq_name", "label": "Person", "property": "name", "kind": "unique"},
            ]
        }
        db, mock_client = self._setup_db(mock_client_cls, constraint_data)

        constraints = db.list_constraints()
        assert len(constraints) == 1
        assert constraints[0].name == "uniq_name"
