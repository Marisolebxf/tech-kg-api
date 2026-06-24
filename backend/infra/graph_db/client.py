"""TRSGraphClient — internal ORM-style repository over trs-graph-service.

Wraps the trs-graph-service REST API (NebulaGraph) for in-app use.
Logic ported from graph_db/backends/trs_graph_backend.py on the
refactor/trs-graph-db-api branch.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx

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
    GraphRequestError,
)
from infra.graph_db.models import (
    GraphConstraintSpec,
    GraphEdge,
    GraphIndexSpec,
    GraphNode,
    GraphPagedResult,
    GraphPath,
    GraphQueryResult,
)

logger = logging.getLogger("infra.graph_db")


class TRSGraphClient:
    """ORM-style repository over trs-graph-service.

    Args:
        settings: Connection settings.
        transport: Optional httpx transport (test seam for MockTransport).
    """

    def __init__(
        self,
        settings: TRSGraphSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.Client | None = None

    # ----- connection lifecycle -----

    def connect(self) -> None:
        if self._client is not None:
            return
        headers = {"X-Graph-Space": self._settings.space}
        if self._settings.api_key:
            headers["X-API-Key"] = self._settings.api_key
        self._client = httpx.Client(
            base_url=self._settings.base_url,
            headers=headers,
            timeout=self._settings.timeout,
            transport=self._transport,
        )
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._client.close()
            self._client = None
            raise GraphConnectionError(
                f"Cannot connect to trs-graph-service at {self._settings.base_url}"
            ) from exc
        logger.info(
            "Connected to TRS Graph at %s (space: %s)",
            self._settings.base_url,
            self._settings.space,
        )

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
            return resp.json().get("status") == "UP"
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
        if self._client is None:
            raise GraphConnectionError("Not connected — call connect() first")
        try:
            resp = self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise GraphConnectionError(f"Request failed: {method} {path}") from exc
        if resp.status_code == 404:
            raise GraphNotFoundError(f"{method} {path} -> 404")
        if not resp.is_success:
            raise GraphRequestError(
                f"{method} {path} -> {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text,
            )
        return resp

    # ==================================================================
    # Node CRUD
    # ==================================================================

    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> GraphNode:
        body = _build_node_create_body(labels, properties)
        resp = self._request("POST", "/api/v1/nodes", json=body)
        return _trs_node_to_model(resp.json())

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        body = {
            "labels": labels if labels else ["Vertex"],
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/nodes/merge", json=body)
        return _trs_node_to_model(resp.json())

    def get_node(self, node_id: Any) -> GraphNode | None:
        try:
            resp = self._request("GET", f"/api/v1/nodes/{node_id}")
        except GraphNotFoundError:
            return None
        return _trs_node_to_model(resp.json())

    def get_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> GraphPagedResult:
        resp = self._request(
            "GET",
            f"/api/v1/nodes/label/{label}",
            params={"limit": limit, "offset": offset},
        )
        data = resp.json()
        items = [_trs_node_to_model(n) for n in data.get("items", [])]
        return GraphPagedResult(
            items=items, total=data.get("total", len(items)), limit=limit, offset=offset
        )

    def find_nodes(
        self,
        labels: list[str],
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> GraphPagedResult:
        body = {
            "labels": labels if labels else ["Vertex"],
            "properties": properties,
            "limit": limit,
            "offset": offset,
        }
        resp = self._request("POST", "/api/v1/nodes/find", json=body)
        data = resp.json()
        items = [_trs_node_to_model(n) for n in data.get("items", [])]
        return GraphPagedResult(
            items=items, total=data.get("total", len(items)), limit=limit, offset=offset
        )

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> GraphNode:
        existing = self.get_node(node_id)
        if existing is None:
            raise GraphNotFoundError(f"Node {node_id} not found")
        label = existing.labels[0] if existing.labels else "Vertex"
        body = {"label": label, "properties": properties}
        resp = self._request("PUT", f"/api/v1/nodes/{node_id}", json=body)
        data = resp.json()
        if isinstance(data, dict) and "id" in data:
            return _trs_node_to_model(data)
        existing.properties.update(properties)
        return existing

    def delete_node(self, node_id: Any, *, detach: bool = False) -> bool:
        params: dict[str, Any] = {}
        if detach:
            params["detach"] = "true"
        try:
            self._request("DELETE", f"/api/v1/nodes/{node_id}", params=params)
        except GraphNotFoundError:
            return False
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
    ) -> GraphEdge:
        body = {
            "type": edge_type,
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/edges", json=body)
        return _trs_edge_to_model(resp.json())

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> GraphEdge:
        body = {
            "type": edge_type,
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/edges/merge", json=body)
        return _trs_edge_to_model(resp.json())

    def get_edge(self, edge_id: Any, edge_type: str | None = None) -> GraphEdge | None:
        try:
            source, target, ranking = _parse_edge_id(str(edge_id))
        except (ValueError, IndexError):
            return None

        if edge_type:
            try:
                resp = self._request(
                    "GET",
                    f"/api/v1/edges/{source}/{target}",
                    params={"type": edge_type, "ranking": ranking},
                )
            except GraphNotFoundError:
                return None
            return _trs_edge_to_model(resp.json())

        # No edge_type — scan the source node's edges.
        try:
            edges = self.get_node_edges(source, direction="both", limit=500)
            for e in edges:
                if e.id == str(edge_id):
                    return e
        except Exception as exc:
            logger.debug("get_edge scan failed for edge %s: %s", edge_id, exc)
        return None

    def get_edges_by_type(
        self, edge_type: str, *, limit: int = 100, offset: int = 0
    ) -> GraphPagedResult:
        resp = self._request(
            "GET",
            f"/api/v1/edges/type/{edge_type}",
            params={"limit": limit, "offset": offset},
        )
        data = resp.json()
        items = [_trs_edge_to_model(e) for e in data.get("items", [])]
        return GraphPagedResult(
            items=items, total=data.get("total", len(items)), limit=limit, offset=offset
        )

    def find_edges(
        self,
        edge_type: str,
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> GraphPagedResult:
        body = {"type": edge_type, "properties": properties, "limit": limit, "offset": offset}
        resp = self._request("POST", "/api/v1/edges/find", json=body)
        data = resp.json()
        items = [_trs_edge_to_model(e) for e in data.get("items", [])]
        return GraphPagedResult(
            items=items, total=data.get("total", len(items)), limit=limit, offset=offset
        )

    def update_edge(
        self, edge_id: Any, properties: dict[str, Any], edge_type: str | None = None
    ) -> GraphEdge:
        source, target, ranking = _parse_edge_id(str(edge_id))
        if not edge_type:
            found = self.get_edge(edge_id)
            edge_type = found.type if found else "unknown"
        body = {"type": edge_type, "ranking": ranking, "properties": properties}
        resp = self._request("PUT", f"/api/v1/edges/{source}/{target}", json=body)
        return _trs_edge_to_model(resp.json())

    def delete_edge(self, edge_id: Any, *, edge_type: str | None = None) -> bool:
        source, target, ranking = _parse_edge_id(str(edge_id))
        params: dict[str, Any] = {"ranking": ranking}
        if not edge_type:
            found = self.get_edge(edge_id)
            edge_type = found.type if found else "unknown"
        params["type"] = edge_type
        try:
            self._request("DELETE", f"/api/v1/edges/{source}/{target}", params=params)
        except GraphNotFoundError:
            return False
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
    ) -> list[GraphEdge]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/edges", params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [_trs_edge_to_model(e) for e in items]

    def get_neighbours(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[GraphNode]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/neighbours", params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [_trs_node_to_model(n) for n in items]

    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        edge_type: str | None = None,
        max_depth: int = 10,
    ) -> GraphPath | None:
        params: dict[str, Any] = {
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "maxDepth": max_depth,
        }
        if edge_type:
            params["type"] = edge_type
        try:
            resp = self._request("GET", "/api/v1/traversal/path/shortest", params=params)
        except GraphNotFoundError:
            return None
        data = resp.json()
        nodes = [_trs_node_to_model(n) for n in data.get("nodes", [])]
        edges = [_trs_edge_to_model(e) for e in data.get("edges", [])]
        for i, node in enumerate(nodes):
            if not node.labels and not node.properties:
                try:
                    full = self.get_node(node.id)
                    if full:
                        nodes[i] = full
                except Exception as exc:
                    logger.debug("shortest_path backfill failed for node %s: %s", node.id, exc)
        return GraphPath(nodes=nodes, edges=edges)

    # ==================================================================
    # Query execution (nGQL)
    # ==================================================================

    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": query}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query", json=body)
        data = resp.json()
        return GraphQueryResult(records=data.get("records", []), summary=data.get("summary"))

    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": query}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/read", json=body)
        data = resp.json()
        return GraphQueryResult(records=data.get("records", []), summary=data.get("summary"))

    def execute_write(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": query}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/write", json=body)
        data = resp.json()
        return GraphQueryResult(records=data.get("records", []), summary=data.get("summary"))

    # ==================================================================
    # Batch operations
    # ==================================================================

    def batch_create_nodes(
        self,
        items: Sequence[dict[str, Any]],
        labels: list[str],
    ) -> list[GraphNode]:
        body = {"labels": labels if labels else ["Vertex"], "items": list(items)}
        resp = self._request("POST", "/api/v1/nodes/batch", json=body)
        data = resp.json()
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return [_trs_node_to_model(n) for n in data if isinstance(n, dict)]
        return []

    def batch_create_edges(
        self,
        items: Sequence[dict[str, Any]],
        edge_type: str,
    ) -> list[GraphEdge]:
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            entry = dict(item)
            if "source_id" in entry and "sourceId" not in entry:
                entry["sourceId"] = str(entry.pop("source_id"))
            if "target_id" in entry and "targetId" not in entry:
                entry["targetId"] = str(entry.pop("target_id"))
            if "properties" in entry and isinstance(entry["properties"], dict):
                props = entry.pop("properties")
                entry.update(props)
            normalized_items.append(entry)
        body = {"type": edge_type, "items": normalized_items}
        resp = self._request("POST", "/api/v1/edges/batch", json=body)
        data = resp.json()
        return [_trs_edge_to_model(e) for e in data if isinstance(e, dict)]

    # ==================================================================
    # Schema management
    # ==================================================================

    def create_index(self, spec: GraphIndexSpec) -> None:
        body = {"label": spec.label, "properties": spec.properties, "unique": spec.unique}
        self._request("POST", "/api/v1/schema/indexes", json=body)

    def drop_index(self, label: str, properties: list[str]) -> None:
        params = {"label": label, "properties": ",".join(properties)}
        self._request("DELETE", "/api/v1/schema/indexes", params=params)

    def list_indexes(self, label: str | None = None) -> list[GraphIndexSpec]:
        params: dict[str, Any] = {}
        if label:
            params["label"] = label
        resp = self._request("GET", "/api/v1/schema/indexes", params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        indexes: list[GraphIndexSpec] = []
        for item in items:
            idx_label = _strip_quotes(item.get("label", ""))
            raw_props = item.get("properties", [])
            clean_props: list[str] = []
            for p in raw_props if isinstance(raw_props, list) else []:
                p = _strip_quotes(p)
                if p.startswith("[") and p.endswith("]"):
                    try:
                        parsed = json.loads(p)
                        if isinstance(parsed, list):
                            clean_props.extend(_strip_quotes(x) for x in parsed)
                            continue
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.debug("list_indexes could not parse bracket property %r: %s", p, exc)
                clean_props.append(p)
            indexes.append(
                GraphIndexSpec(
                    label=idx_label,
                    properties=clean_props,
                    unique=item.get("unique", False),
                )
            )
        return indexes

    def create_constraint(self, spec: GraphConstraintSpec) -> None:
        body = {
            "name": spec.name,
            "label": spec.label,
            "property": spec.property,
            "kind": spec.kind,
        }
        self._request("POST", "/api/v1/schema/constraints", json=body)

    def drop_constraint(self, name: str) -> None:
        self._request("DELETE", f"/api/v1/schema/constraints/{name}")

    def list_constraints(self) -> list[GraphConstraintSpec]:
        resp = self._request("GET", "/api/v1/schema/constraints")
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        constraints: list[GraphConstraintSpec] = []
        for item in items:
            constraints.append(
                GraphConstraintSpec(
                    name=_strip_quotes(item.get("name", "")),
                    label=_strip_quotes(item.get("label", "")),
                    property=_strip_quotes(item.get("property", "")),
                    kind=item.get("kind", "unique"),
                )
            )
        return constraints

    # ==================================================================
    # Database info
    # ==================================================================

    def node_count(self, label: str | None = None) -> int:
        params: dict[str, Any] = {}
        if label:
            params["label"] = label
        resp = self._request("GET", "/api/v1/schema/stats/node-count", params=params)
        return resp.json().get("count", 0)

    def edge_count(self, edge_type: str | None = None) -> int:
        params: dict[str, Any] = {}
        if edge_type:
            params["type"] = edge_type
        resp = self._request("GET", "/api/v1/schema/stats/edge-count", params=params)
        return resp.json().get("count", 0)

    def labels(self) -> list[str]:
        resp = self._request("GET", "/api/v1/schema/labels")
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        result: list[str] = []
        for item in items:
            if isinstance(item, dict):
                result.append(item.get("Name", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result

    def edge_types(self) -> list[str]:
        resp = self._request("GET", "/api/v1/schema/edge-types")
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        result: list[str] = []
        for item in items:
            if isinstance(item, dict):
                result.append(item.get("Name", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result
