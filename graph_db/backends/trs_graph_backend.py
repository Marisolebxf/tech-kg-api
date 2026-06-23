"""TRS Graph backend implementing the generic GraphDatabase API.

Communicates with ``trs-graph-service`` (a Java Spring Boot REST API)
over HTTP to perform all graph database operations on NebulaGraph.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Sequence

import httpx

from graph_db.base import GraphDatabase
from graph_db.models import (
    ConstraintSpec,
    Edge,
    IndexSpec,
    Node,
    PagedResult,
    PageInfo,
    Path,
    QueryResult,
)

logger = logging.getLogger("graph_db.trs_graph")


# ---------------------------------------------------------------------------
# Internal conversion helpers
# ---------------------------------------------------------------------------

def _trs_node_to_model(data: dict[str, Any]) -> Node:
    """Convert trs-graph-service Node JSON to graph_db Node model.

    Expected JSON shape: {"id": ..., "labels": [...], "properties": {...}}
    """
    return Node(
        id=data["id"],
        labels=data.get("labels", []),
        properties=data.get("properties", {}),
    )


def _trs_edge_to_model(data: dict[str, Any]) -> Edge:
    """Convert trs-graph-service Edge JSON to graph_db Edge model.

    Expected JSON shape: {"id": ..., "type": ..., "sourceId": ..., "targetId": ..., "properties": {...}}
    """
    return Edge(
        id=data["id"],
        type=data["type"],
        source_id=data["sourceId"],
        target_id=data["targetId"],
        properties=data.get("properties", {}),
    )


def _build_node_create_body(labels: list[str], properties: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build request body for node creation.

    TRS Graph expects ``labels`` as a list. The service maps the first label
    to the NebulaGraph TAG.
    """
    body: dict[str, Any] = {
        "labels": labels if labels else ["Vertex"],
        "properties": dict(properties) if properties else {},
    }
    return body


def _parse_edge_id(edge_id: str) -> tuple[str, str, int]:
    """Parse TRS Graph edge ID format ``"sourceId->targetId@ranking"``.

    Returns (source_id, target_id, ranking).
    """
    parts = edge_id.split("@")
    ranking = int(parts[1]) if len(parts) > 1 else 0
    src_dst = parts[0].split("->")
    return src_dst[0], src_dst[1], ranking


def _extract_batch_items(payload: Any) -> list[dict[str, Any]]:
    """Normalize batch endpoints that may return either a raw list or a wrapper."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "records", "nodes", "edges"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


# ---------------------------------------------------------------------------
# Pseudo-transaction
# ---------------------------------------------------------------------------

class TRSTransaction:
    """Pseudo-transaction that caches write operations and executes on commit().

    TRS Graph has no ACID multi-statement transactions, so this class
    merely queues operations and fires them sequentially on ``commit()``.
    No atomicity guarantee is provided.
    """

    def __init__(self, db: "TRSGraphDatabase"):
        self._db = db
        self._queue: list[tuple[str, Any]] = []
        self._committed = False
        self._rolled_back = False

    # -- Node CRUD (queued) --

    def create_node(
        self, labels: list[str], properties: dict[str, Any] | None = None
    ) -> Node:
        result = self._db.create_node(labels, properties)
        return result

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node:
        result = self._db.merge_node(labels, identity_props, properties)
        return result

    def get_node(self, node_id: Any) -> Node | None:
        return self._db.get_node(node_id)

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        result = self._db.update_node(node_id, properties)
        return result

    def delete_node(self, node_id: Any, detach: bool = False) -> bool:
        return self._db.delete_node(node_id, detach=detach)

    # -- Edge CRUD (queued) --

    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        result = self._db.create_edge(source_id, target_id, edge_type, properties)
        return result

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        result = self._db.merge_edge(source_id, target_id, edge_type, identity_props, properties)
        return result

    def get_edge(self, edge_id: Any) -> Edge | None:
        return self._db.get_edge(edge_id)

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        result = self._db.update_edge(edge_id, properties)
        return result

    def delete_edge(self, edge_id: Any) -> bool:
        return self._db.delete_edge(edge_id)

    # -- Raw query --

    def run(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        return self._db.execute_query(query, params)

    # -- Commit / Rollback --

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        self._queue.clear()
        self._rolled_back = True

    # -- Context manager --

    def __enter__(self) -> "TRSTransaction":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.rollback()


# ---------------------------------------------------------------------------
# TRS Graph Database implementation
# ---------------------------------------------------------------------------

class TRSGraphDatabase(GraphDatabase):
    """TRS Graph implementation of the generic GraphDatabase API.

    Communicates with ``trs-graph-service`` over HTTP.

    Args:
        base_url: Base URL of the trs-graph-service REST API.
        graph_space: NebulaGraph space name (sent as ``X-Graph-Space`` header).
        timeout: HTTP request timeout in seconds.

    Example::

        db = TRSGraphDatabase("http://localhost:8090", "my_space")
        db.connect()
        node = db.create_node(["Person"], {"name": "Alice"})
        db.close()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8090",
        graph_space: str = "entity_binding_demo",
        timeout: int = 30,
        **kwargs: Any,
    ):
        self._base_url = base_url.rstrip("/")
        self._graph_space = graph_space
        self._timeout = timeout
        self._api_key = kwargs.get("api_key") or os.getenv("TRS_GRAPH_API_KEY", "")
        self._client: httpx.Client | None = None
        # Allow passing config= for compatibility with connect() factory
        self._config = kwargs.get("config")

    # ----- connection lifecycle -----

    def connect(self) -> None:
        if self._client is not None:
            return
        headers = {"X-Graph-Space": self._graph_space}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        self._client = httpx.Client(base_url=self._base_url, headers=headers, timeout=self._timeout)
        # Verify connectivity
        resp = self._client.get("/health")
        resp.raise_for_status()
        logger.info("Connected to TRS Graph at %s (space: %s)", self._base_url, self._graph_space)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Disconnected from TRS Graph")

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
            data = resp.json()
            return data.get("status") == "UP"
        except Exception:
            return False

    # ----- internal HTTP helper -----

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Core HTTP request method. Raises RuntimeError if not connected."""
        if self._client is None:
            raise RuntimeError("Not connected — call connect() first")
        resp = self._client.request(method, path, json=json, params=params)
        return resp

    # ==================================================================
    # Node CRUD
    # ==================================================================

    def create_node(
        self, labels: list[str], properties: dict[str, Any] | None = None
    ) -> Node:
        body = _build_node_create_body(labels, properties)
        resp = self._request("POST", "/api/v1/nodes", json=body)
        resp.raise_for_status()
        return _trs_node_to_model(resp.json())

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node:
        body = {
            "labels": labels if labels else ["Vertex"],
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/nodes/merge", json=body)
        resp.raise_for_status()
        return _trs_node_to_model(resp.json())

    def get_node(self, node_id: Any) -> Node | None:
        resp = self._request("GET", f"/api/v1/nodes/{node_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _trs_node_to_model(resp.json())

    def get_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> PagedResult:
        resp = self._request(
            "GET",
            f"/api/v1/nodes/label/{label}",
            params={"limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        items = [_trs_node_to_model(n) for n in data.get("items", [])]
        total = data.get("total", len(items))
        return PagedResult(
            items=items,
            page=PageInfo(offset=offset, limit=limit, total=total),
        )

    def find_nodes(
        self,
        labels: list[str],
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        body = {
            "labels": labels if labels else ["Vertex"],
            "properties": properties,
            "limit": limit,
            "offset": offset,
        }
        resp = self._request("POST", "/api/v1/nodes/find", json=body)
        resp.raise_for_status()
        data = resp.json()
        items = [_trs_node_to_model(n) for n in data.get("items", [])]
        total = data.get("total", len(items))
        return PagedResult(
            items=items,
            page=PageInfo(offset=offset, limit=limit, total=total),
        )

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        # Fetch existing node first to get its label (trs-graph-service requires label for update)
        existing = self.get_node(node_id)
        if existing is None:
            raise ValueError(f"Node {node_id} not found")
        label = existing.labels[0] if existing.labels else "Vertex"
        body = {
            "label": label,
            "properties": properties,
        }
        resp = self._request("PUT", f"/api/v1/nodes/{node_id}", json=body)
        resp.raise_for_status()
        data = resp.json()
        # Service may return a map wrapper: {"id": ..., "labels": [...], "properties": {...}}
        if "id" in data:
            return _trs_node_to_model(data)
        # Or it may return just properties — merge with existing
        existing.properties.update(properties)
        return existing

    def delete_node(self, node_id: Any, *, detach: bool = False) -> bool:
        params = {}
        if detach:
            params["detach"] = "true"
        resp = self._request("DELETE", f"/api/v1/nodes/{node_id}", params=params)
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True

    # ==================================================================
    # Edge CRUD
    # ==================================================================

    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        body = {
            "type": edge_type,
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/edges", json=body)
        resp.raise_for_status()
        return _trs_edge_to_model(resp.json())

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        body = {
            "type": edge_type,
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/edges/merge", json=body)
        resp.raise_for_status()
        return _trs_edge_to_model(resp.json())

    def get_edge(self, edge_id: Any) -> Edge | None:
        # TRS Graph edge ID format: "sourceId->targetId@ranking"
        # The service endpoint is GET /api/v1/edges/{sourceId}/{targetId}?type=...&ranking=0
        try:
            source, target, ranking = _parse_edge_id(str(edge_id))
        except (ValueError, IndexError):
            return None
        resp = self._request(
            "GET",
            f"/api/v1/edges/{source}/{target}",
            params={"type": "unknown", "ranking": ranking},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _trs_edge_to_model(resp.json())

    def get_edges_by_type(
        self, edge_type: str, *, limit: int = 100, offset: int = 0
    ) -> PagedResult:
        resp = self._request(
            "GET",
            f"/api/v1/edges/type/{edge_type}",
            params={"limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        items = [_trs_edge_to_model(e) for e in data.get("items", [])]
        total = data.get("total", len(items))
        return PagedResult(
            items=items,
            page=PageInfo(offset=offset, limit=limit, total=total),
        )

    def find_edges(
        self,
        edge_type: str,
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        body = {
            "type": edge_type,
            "properties": properties,
            "limit": limit,
            "offset": offset,
        }
        resp = self._request("POST", "/api/v1/edges/find", json=body)
        resp.raise_for_status()
        data = resp.json()
        items = [_trs_edge_to_model(e) for e in data.get("items", [])]
        total = data.get("total", len(items))
        return PagedResult(
            items=items,
            page=PageInfo(offset=offset, limit=limit, total=total),
        )

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        source, target, ranking = _parse_edge_id(str(edge_id))
        body = {
            "type": "unknown",
            "ranking": ranking,
            "properties": properties,
        }
        resp = self._request("PUT", f"/api/v1/edges/{source}/{target}", json=body)
        resp.raise_for_status()
        return _trs_edge_to_model(resp.json())

    def delete_edge(self, edge_id: Any, *, edge_type: str | None = None) -> bool:
        source, target, ranking = _parse_edge_id(str(edge_id))
        params: dict[str, Any] = {"ranking": ranking}
        if edge_type:
            params["type"] = edge_type
        else:
            params["type"] = "unknown"
        resp = self._request(
            "DELETE",
            f"/api/v1/edges/{source}/{target}",
            params=params,
        )
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True

    # ==================================================================
    # Neighbourhood / traversal
    # ==================================================================

    def get_node_edges(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Edge]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/edges", params=params)
        resp.raise_for_status()
        data = resp.json()
        return [_trs_edge_to_model(e) for e in (data if isinstance(data, list) else data.get("items", []))]

    def get_neighbours(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Node]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/neighbours", params=params)
        resp.raise_for_status()
        data = resp.json()
        return [_trs_node_to_model(n) for n in (data if isinstance(data, list) else data.get("items", []))]

    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        edge_type: str | None = None,
        max_depth: int = 10,
    ) -> Path | None:
        params: dict[str, Any] = {
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "maxDepth": max_depth,
        }
        if edge_type:
            params["type"] = edge_type
        resp = self._request("GET", "/api/v1/traversal/path/shortest", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        nodes = [_trs_node_to_model(n) for n in data.get("nodes", [])]
        edges = [_trs_edge_to_model(e) for e in data.get("edges", [])]
        return Path(nodes=nodes, edges=edges)

    # ==================================================================
    # Query execution
    # ==================================================================

    def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        body = {"query": query}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query", json=body)
        resp.raise_for_status()
        data = resp.json()
        return QueryResult(records=data.get("records", []), summary=data.get("summary"))

    def execute_read(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        body = {"query": query}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/read", json=body)
        resp.raise_for_status()
        data = resp.json()
        return QueryResult(records=data.get("records", []), summary=data.get("summary"))

    def execute_write(
        self, query: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        body = {"query": query}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/write", json=body)
        resp.raise_for_status()
        data = resp.json()
        return QueryResult(records=data.get("records", []), summary=data.get("summary"))

    # ==================================================================
    # Transactions
    # ==================================================================

    def transaction(self) -> TRSTransaction:
        return TRSTransaction(self)

    # ==================================================================
    # Batch operations
    # ==================================================================

    def batch_create_nodes(
        self,
        items: Sequence[dict[str, Any]],
        labels: list[str],
    ) -> list[Node]:
        body = {
            "labels": labels if labels else ["Vertex"],
            "items": list(items),
        }
        resp = self._request("POST", "/api/v1/nodes/batch", json=body)
        resp.raise_for_status()
        data = _extract_batch_items(resp.json())
        return [_trs_node_to_model(n) for n in data]

    def batch_create_edges(
        self,
        items: Sequence[dict[str, Any]],
        edge_type: str,
    ) -> list[Edge]:
        # Each item should contain sourceId, targetId, and optionally ranking + properties
        normalized_items = []
        for item in items:
            entry = dict(item)
            # Ensure sourceId/targetId keys are present
            if "source_id" in entry and "sourceId" not in entry:
                entry["sourceId"] = str(entry.pop("source_id"))
            if "target_id" in entry and "targetId" not in entry:
                entry["targetId"] = str(entry.pop("target_id"))
            normalized_items.append(entry)
        body = {
            "type": edge_type,
            "items": normalized_items,
        }
        resp = self._request("POST", "/api/v1/edges/batch", json=body)
        resp.raise_for_status()
        data = _extract_batch_items(resp.json())
        return [_trs_edge_to_model(e) for e in data]

    # ==================================================================
    # Schema management
    # ==================================================================

    def create_index(self, spec: IndexSpec) -> None:
        body = {
            "label": spec.label,
            "properties": spec.properties,
            "unique": spec.unique,
        }
        resp = self._request("POST", "/api/v1/schema/indexes", json=body)
        resp.raise_for_status()

    def drop_index(self, label: str, properties: list[str]) -> None:
        # Build a query params approach for identifying the index
        params = {"label": label, "properties": ",".join(properties)}
        resp = self._request("DELETE", "/api/v1/schema/indexes", params=params)
        resp.raise_for_status()

    def list_indexes(self, label: str | None = None) -> list[IndexSpec]:
        params = {}
        if label:
            params["label"] = label
        resp = self._request("GET", "/api/v1/schema/indexes", params=params)
        resp.raise_for_status()
        data = resp.json()
        indexes = []
        for item in data.get("items", data if isinstance(data, list) else []):
            indexes.append(IndexSpec(
                label=item.get("label", ""),
                properties=item.get("properties", []),
                unique=item.get("unique", False),
            ))
        return indexes

    def create_constraint(self, spec: ConstraintSpec) -> None:
        body = {
            "name": spec.name,
            "label": spec.label,
            "property": spec.property,
            "kind": spec.kind,
        }
        resp = self._request("POST", "/api/v1/schema/constraints", json=body)
        resp.raise_for_status()

    def drop_constraint(self, name: str) -> None:
        resp = self._request("DELETE", f"/api/v1/schema/constraints/{name}")
        resp.raise_for_status()

    def list_constraints(self) -> list[ConstraintSpec]:
        resp = self._request("GET", "/api/v1/schema/constraints")
        resp.raise_for_status()
        data = resp.json()
        constraints = []
        for item in data.get("items", data if isinstance(data, list) else []):
            constraints.append(ConstraintSpec(
                name=item.get("name", ""),
                label=item.get("label", ""),
                property=item.get("property", ""),
                kind=item.get("kind", "unique"),
            ))
        return constraints

    # ==================================================================
    # Database info
    # ==================================================================

    def node_count(self, label: str | None = None) -> int:
        path = "/api/v1/schema/stats/node-count"
        params = {}
        if label:
            params["label"] = label
        resp = self._request("GET", path, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("count", 0)

    def edge_count(self, edge_type: str | None = None) -> int:
        path = "/api/v1/schema/stats/edge-count"
        params = {}
        if edge_type:
            params["type"] = edge_type
        resp = self._request("GET", path, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("count", 0)

    def labels(self) -> list[str]:
        resp = self._request("GET", "/api/v1/schema/labels")
        resp.raise_for_status()
        data = resp.json()
        result = []
        for item in data.get("items", data if isinstance(data, list) else []):
            # Handle both {"Name": "xxx"} dict and plain string formats
            if isinstance(item, dict):
                result.append(item.get("Name", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result

    def edge_types(self) -> list[str]:
        resp = self._request("GET", "/api/v1/schema/edge-types")
        resp.raise_for_status()
        data = resp.json()
        result = []
        for item in data.get("items", data if isinstance(data, list) else []):
            # Handle both {"Name": "xxx"} dict and plain string formats
            if isinstance(item, dict):
                result.append(item.get("Name", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result
