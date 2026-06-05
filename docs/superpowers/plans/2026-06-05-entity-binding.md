# 跨库绑定（Entity Binding）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现人才库、论文库、专利库、机构库之间的跨库实体绑定功能，含 TRS Graph 后端适配、规则+LLM 绑定逻辑、API、前端展示。

**Architecture:** 在 `graph_db` 抽象层中添加 TRS Graph HTTP 后端，通过调用 `trs-graph-service`（Java REST API on :8090）操作 TRS Graph。绑定逻辑采用规则召回+LLM精排的 pipeline，结果以边形式写入 TRS Graph。前端用纯 HTML+D3.js 展示绑定关系图。

**Tech Stack:** Python 3.13, FastAPI, httpx, Pydantic v2, ZhipuAI GLM, D3.js (CDN)

---

## 文件结构

| 操作 | 文件路径 | 职责 |
|---|---|---|
| Create | `graph_db/backends/trs_graph_backend.py` | TRS Graph HTTP 后端，实现 GraphDatabase ABC 全部 25 个方法 + TRSTransaction |
| Modify | `graph_db/config.py` | 修复 `connect()` 工厂方法，为非 Neo4j 后端传入 config；注册 trs_graph |
| Modify | `graph_db/backends/__init__.py` | 导入 TRSGraphDatabase |
| Modify | `graph_db/__init__.py` | 导出 TRSGraphDatabase |
| Create | `app/schemas/entity_binding.py` | 绑定相关请求/响应 Pydantic 模型 |
| Create | `app/services/binding_matcher.py` | 规则召回匹配逻辑（姓名/机构/字段相似度） |
| Create | `app/services/entity_binding.py` | 绑定核心 pipeline（数据召回→规则→LLM→写入） |
| Create | `app/routers/entity_binding.py` | 绑定 API 路由（6 个端点） |
| Create | `app/static/binding.html` | 前端展示页面（操作+统计+详情表+D3关系图） |
| Modify | `app/main.py` | 注册绑定路由 + 挂载 static 文件 |
| Create | `tests/test_trs_graph_backend.py` | TRS Graph 后端单元测试 |
| Create | `tests/test_binding_matcher.py` | 规则匹配逻辑单元测试 |
| Create | `tests/test_entity_binding.py` | 绑定集成测试 |

---

### Task 1: TRS Graph Backend — 连接与节点 CRUD

**Files:**
- Create: `graph_db/backends/trs_graph_backend.py`
- Modify: `graph_db/config.py`
- Modify: `graph_db/backends/__init__.py`
- Modify: `graph_db/__init__.py`
- Create: `tests/test_trs_graph_backend.py`

- [ ] **Step 1: Create `trs_graph_backend.py` with connection lifecycle and node CRUD**

```python
"""TRS Graph backend for the graph_db abstraction layer.

Communicates with trs-graph-service (Spring Boot REST API) over HTTP.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Sequence

import httpx

from graph_db.base import GraphDatabase, Transaction
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

logger = logging.getLogger(__name__)


class TRSTransaction:
    """Pseudo-transaction for TRS Graph.

    TRS Graph (NebulaGraph) does not support ACID multi-statement transactions.
    This class caches write operations and executes them on commit().
    No atomicity guarantee.
    """

    def __init__(self, db: "TRSGraphDatabase") -> None:
        self._db = db
        self._queue: list[tuple[str, dict[str, Any]]] = []
        self._committed = False
        self._rolled_back = False

    def _enqueue(self, method: str, kwargs: dict[str, Any]) -> Node | Edge:
        self._queue.append((method, kwargs))
        # Return a placeholder — real result only after commit
        if "source_id" in kwargs:
            return Edge(id="", type=kwargs.get("edge_type", ""), source_id=kwargs["source_id"], target_id=kwargs["target_id"])
        return Node(id=kwargs.get("properties", {}).get("vid", ""), labels=kwargs.get("labels", []), properties=kwargs.get("properties", {}))

    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> Node:
        return self._enqueue("create_node", {"labels": labels, "properties": properties})

    def merge_node(self, labels: list[str], identity_props: dict[str, Any], properties: dict[str, Any] | None = None) -> Node:
        return self._enqueue("merge_node", {"labels": labels, "identity_props": identity_props, "properties": properties})

    def get_node(self, node_id: Any) -> Node | None:
        return self._db.get_node(node_id)

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        return self._enqueue("update_node", {"node_id": node_id, "properties": properties})

    def delete_node(self, node_id: Any, detach: bool = False) -> bool:
        return self._enqueue("delete_node", {"node_id": node_id, "detach": detach})

    def create_edge(self, source_id: Any, target_id: Any, edge_type: str, properties: dict[str, Any] | None = None) -> Edge:
        return self._enqueue("create_edge", {"source_id": source_id, "target_id": target_id, "edge_type": edge_type, "properties": properties})

    def merge_edge(self, source_id: Any, target_id: Any, edge_type: str, identity_props: dict[str, Any], properties: dict[str, Any] | None = None) -> Edge:
        return self._enqueue("merge_edge", {"source_id": source_id, "target_id": target_id, "edge_type": edge_type, "identity_props": identity_props, "properties": properties})

    def get_edge(self, edge_id: Any) -> Edge | None:
        return self._db.get_edge(edge_id)

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        return self._enqueue("update_edge", {"edge_id": edge_id, "properties": properties})

    def delete_edge(self, edge_id: Any) -> bool:
        return self._enqueue("delete_edge", {"edge_id": edge_id})

    def run(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        return self._db.execute_query(query, params)

    def commit(self) -> None:
        if self._rolled_back:
            return
        for method_name, kwargs in self._queue:
            getattr(self._db, method_name)(**kwargs)
        self._committed = True

    def rollback(self) -> None:
        self._queue.clear()
        self._rolled_back = True

    def __enter__(self) -> "TRSTransaction":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.rollback()


def _trs_node_to_model(data: dict[str, Any]) -> Node:
    """Convert trs-graph-service Node JSON to graph_db Node model."""
    return Node(
        id=data.get("id", ""),
        labels=data.get("labels", []),
        properties=data.get("properties", {}),
    )


def _trs_edge_to_model(data: dict[str, Any]) -> Edge:
    """Convert trs-graph-service Edge JSON to graph_db Edge model."""
    return Edge(
        id=data.get("id", ""),
        type=data.get("type", ""),
        source_id=data.get("sourceId", ""),
        target_id=data.get("targetId", ""),
        properties=data.get("properties", {}),
    )


def _build_node_create_body(labels: list[str], properties: dict[str, Any] | None) -> dict[str, Any]:
    """Build request body for node creation.

    TRS Graph supports only one TAG per vertex.
    First label becomes the TAG; extras go into _additional_labels property.
    """
    props = dict(properties) if properties else {}
    tag = labels[0] if labels else "Unknown"
    if len(labels) > 1:
        props["_additional_labels"] = labels[1:]
    return {"labels": [tag], "properties": props}


class TRSGraphDatabase(GraphDatabase):
    """TRS Graph backend that communicates with trs-graph-service over HTTP."""

    def __init__(
        self,
        base_url: str = "http://localhost:8090",
        graph_space: str = "entity_binding_demo",
        timeout: int = 30,
        **kwargs: Any,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._graph_space = graph_space
        self._timeout = timeout
        self._client: httpx.Client | None = None

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request to trs-graph-service."""
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")
        url = f"{self._base_url}{path}"
        response = self._client.request(method, url, json=json, params=params)
        response.raise_for_status()
        return response.json()

    # ----- connection lifecycle -----

    def connect(self) -> None:
        self._client = httpx.Client(
            timeout=self._timeout,
            headers={"X-Graph-Space": self._graph_space, "Content-Type": "application/json"},
        )
        # Verify connection
        try:
            health = self._request("GET", "/health")
            if health.get("status") != "UP":
                raise ConnectionError(f"TRS Graph service not healthy: {health}")
        except httpx.HTTPError as e:
            self._client = None
            raise ConnectionError(f"Cannot connect to trs-graph-service: {e}") from e

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            health = self._request("GET", "/health")
            return health.get("status") == "UP"
        except Exception:
            return False

    # ----- Node CRUD -----

    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> Node:
        body = _build_node_create_body(labels, properties)
        data = self._request("POST", "/api/v1/nodes", json=body)
        return _trs_node_to_model(data)

    def merge_node(self, labels: list[str], identity_props: dict[str, Any], properties: dict[str, Any] | None = None) -> Node:
        props = dict(properties) if properties else {}
        tag = labels[0] if labels else "Unknown"
        extra_labels = labels[1:]
        if extra_labels:
            props["_additional_labels"] = extra_labels
        # Merge identity_props into properties for trs-graph-service
        # The service uses vid from identity_props for upsert
        merged_props = {**identity_props, **props}
        body = {"labels": [tag], "identityProps": identity_props, "properties": merged_props}
        data = self._request("POST", "/api/v1/nodes/merge", json=body)
        return _trs_node_to_model(data)

    def get_node(self, node_id: Any) -> Node | None:
        try:
            data = self._request("GET", f"/api/v1/nodes/{node_id}")
            return _trs_node_to_model(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_nodes_by_label(self, label: str, *, limit: int = 100, offset: int = 0) -> PagedResult:
        data = self._request("GET", f"/api/v1/nodes/label/{label}", params={"limit": limit, "offset": offset})
        items = [_trs_node_to_model(item) for item in data.get("items", [])]
        page_data = data.get("page", {})
        return PagedResult(items=items, page=PageInfo(offset=page_data.get("offset", 0), limit=page_data.get("limit", 100), total=page_data.get("total", 0)))

    def find_nodes(self, labels: list[str], properties: dict[str, Any], *, limit: int = 100, offset: int = 0) -> PagedResult:
        body = {"labels": labels, "properties": properties, "offset": offset, "limit": limit}
        data = self._request("POST", "/api/v1/nodes/find", json=body)
        items = [_trs_node_to_model(item) for item in data.get("items", [])]
        page_data = data.get("page", {})
        return PagedResult(items=items, page=PageInfo(offset=page_data.get("offset", 0), limit=page_data.get("limit", 100), total=page_data.get("total", 0)))

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        # trs-graph-service requires label for update
        # Fetch node first to get its label
        node = self.get_node(node_id)
        label = node.labels[0] if node and node.labels else "Unknown"
        body = {"label": label, "properties": properties}
        data = self._request("PUT", f"/api/v1/nodes/{node_id}", json=body)
        return _trs_node_to_model(data)

    def delete_node(self, node_id: Any, *, detach: bool = False) -> bool:
        try:
            self._request("DELETE", f"/api/v1/nodes/{node_id}", params={"detach": str(detach).lower()})
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    # ----- Edge CRUD -----

    def create_edge(self, source_id: Any, target_id: Any, edge_type: str, properties: dict[str, Any] | None = None) -> Edge:
        body = {"type": edge_type, "sourceId": str(source_id), "targetId": str(target_id), "properties": properties or {}}
        data = self._request("POST", "/api/v1/edges", json=body)
        return _trs_edge_to_model(data)

    def merge_edge(self, source_id: Any, target_id: Any, edge_type: str, identity_props: dict[str, Any], properties: dict[str, Any] | None = None) -> Edge:
        props = dict(properties) if properties else {}
        merged_props = {**identity_props, **props}
        body = {"type": edge_type, "sourceId": str(source_id), "targetId": str(target_id), "identityProps": identity_props, "properties": merged_props}
        data = self._request("POST", "/api/v1/edges/merge", json=body)
        return _trs_edge_to_model(data)

    def get_edge(self, edge_id: Any) -> Edge | None:
        # TRS Graph edge ID format: "sourceId->targetId@ranking"
        # Parse and use the traversal endpoint
        # For simplicity, delegate to find via source/target
        # edge_id is opaque — callers should use get_edges_by_type or find_edges
        try:
            parts = str(edge_id).split("->")
            if len(parts) != 2:
                return None
            source = parts[0]
            rest = parts[1].split("@")
            target = rest[0]
            ranking = int(rest[1]) if len(rest) > 1 else 0
            # Need edge type — try fetching from node edges
            data = self._request("GET", f"/api/v1/edges/{source}/{target}", params={"type": "", "ranking": ranking})
            return _trs_edge_to_model(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_edges_by_type(self, edge_type: str, *, limit: int = 100, offset: int = 0) -> PagedResult:
        data = self._request("GET", f"/api/v1/edges/type/{edge_type}", params={"limit": limit, "offset": offset})
        items = [_trs_edge_to_model(item) for item in data.get("items", [])]
        page_data = data.get("page", {})
        return PagedResult(items=items, page=PageInfo(offset=page_data.get("offset", 0), limit=page_data.get("limit", 100), total=page_data.get("total", 0)))

    def find_edges(self, edge_type: str, properties: dict[str, Any], *, limit: int = 100, offset: int = 0) -> PagedResult:
        body = {"type": edge_type, "properties": properties, "offset": offset, "limit": limit}
        data = self._request("POST", "/api/v1/edges/find", json=body)
        items = [_trs_edge_to_model(item) for item in data.get("items", [])]
        page_data = data.get("page", {})
        return PagedResult(items=items, page=PageInfo(offset=page_data.get("offset", 0), limit=page_data.get("limit", 100), total=page_data.get("total", 0)))

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        # Parse edge_id to get source/target
        parts = str(edge_id).split("->")
        source = parts[0]
        rest = parts[1].split("@")
        target = rest[0]
        ranking = int(rest[1]) if len(rest) > 1 else 0
        body = {"ranking": ranking, "properties": properties}
        data = self._request("PUT", f"/api/v1/edges/{source}/{target}", json=body)
        return _trs_edge_to_model(data)

    def delete_edge(self, edge_id: Any) -> bool:
        parts = str(edge_id).split("->")
        source = parts[0]
        rest = parts[1].split("@")
        target = rest[0]
        try:
            self._request("DELETE", f"/api/v1/edges/{source}/{target}", params={"type": "", "ranking": 0})
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    # ----- Traversal -----

    def get_node_edges(self, node_id: Any, *, direction: str = "both", edge_type: str | None = None, limit: int = 100) -> list[Edge]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        data = self._request("GET", f"/api/v1/traversal/{node_id}/edges", params=params)
        return [_trs_edge_to_model(item) for item in data]

    def get_neighbours(self, node_id: Any, *, direction: str = "both", edge_type: str | None = None, limit: int = 100) -> list[Node]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        data = self._request("GET", f"/api/v1/traversal/{node_id}/neighbours", params=params)
        return [_trs_node_to_model(item) for item in data]

    def shortest_path(self, source_id: Any, target_id: Any, *, edge_type: str | None = None, max_depth: int = 10) -> Path | None:
        params: dict[str, Any] = {"sourceId": str(source_id), "targetId": str(target_id), "maxDepth": max_depth}
        if edge_type:
            params["edgeType"] = edge_type
        try:
            data = self._request("GET", "/api/v1/traversal/path/shortest", params=params)
            nodes = [_trs_node_to_model(n) for n in data.get("nodes", [])]
            edges = [_trs_edge_to_model(e) for e in data.get("edges", [])]
            if not nodes:
                return None
            return Path(nodes=nodes, edges=edges)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # ----- Query execution -----

    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        body = {"query": query, "params": params or {}}
        data = self._request("POST", "/api/v1/query", json=body)
        return QueryResult(records=data.get("records", []), summary=data.get("summary"))

    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        body = {"query": query, "params": params or {}}
        data = self._request("POST", "/api/v1/query/read", json=body)
        return QueryResult(records=data.get("records", []), summary=data.get("summary"))

    def execute_write(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        body = {"query": query, "params": params or {}}
        data = self._request("POST", "/api/v1/query/write", json=body)
        return QueryResult(records=data.get("records", []), summary=data.get("summary"))

    # ----- Transactions -----

    def transaction(self) -> Transaction:
        return TRSTransaction(self)

    # ----- Batch operations -----

    def batch_create_nodes(self, items: Sequence[dict[str, Any]], labels: list[str]) -> list[Node]:
        tag = labels[0] if labels else "Unknown"
        extra_labels = labels[1:]
        processed_items = []
        for item in items:
            props = dict(item)
            if extra_labels:
                props["_additional_labels"] = extra_labels
            processed_items.append(props)
        body = {"labels": [tag], "items": processed_items}
        data = self._request("POST", "/api/v1/nodes/batch", json=body)
        if isinstance(data, list):
            return [_trs_node_to_model(item) for item in data]
        return []

    def batch_create_edges(self, items: Sequence[dict[str, Any]], edge_type: str) -> list[Edge]:
        processed_items = []
        for item in items:
            props = dict(item)
            processed_items.append(props)
        body = {"type": edge_type, "items": processed_items}
        data = self._request("POST", "/api/v1/edges/batch", json=body)
        if isinstance(data, list):
            return [_trs_edge_to_model(item) for item in data]
        return []

    # ----- Schema management -----

    def create_index(self, spec: IndexSpec) -> None:
        body = {"label": spec.label, "properties": spec.properties, "unique": spec.unique}
        self._request("POST", "/api/v1/schema/indexes", json=body)

    def drop_index(self, label: str, properties: list[str]) -> None:
        # trs-graph-service drops by index name; derive name from label + properties
        index_name = f"idx_{label}_{'_'.join(properties)}"
        self._request("DELETE", f"/api/v1/schema/indexes/{index_name}")

    def list_indexes(self, label: str | None = None) -> list[IndexSpec]:
        params = {}
        if label:
            params["label"] = label
        data = self._request("GET", "/api/v1/schema/indexes", params=params)
        if isinstance(data, list):
            return [IndexSpec(label=item.get("label", ""), properties=item.get("properties", []), unique=item.get("unique", False)) for item in data]
        return []

    def create_constraint(self, spec: ConstraintSpec) -> None:
        body = {"name": spec.name, "label": spec.label, "property": spec.property, "kind": spec.kind}
        self._request("POST", "/api/v1/schema/constraints", json=body)

    def drop_constraint(self, name: str) -> None:
        self._request("DELETE", f"/api/v1/schema/constraints/{name}")

    def list_constraints(self) -> list[ConstraintSpec]:
        data = self._request("GET", "/api/v1/schema/constraints")
        if isinstance(data, list):
            return [ConstraintSpec(name=item.get("name", ""), label=item.get("label", ""), property=item.get("property", ""), kind=item.get("kind", "unique")) for item in data]
        return []

    # ----- Database info -----

    def node_count(self, label: str | None = None) -> int:
        params = {}
        if label:
            params["label"] = label
        data = self._request("GET", "/api/v1/schema/stats/node-count", params=params)
        return data.get("count", 0)

    def edge_count(self, edge_type: str | None = None) -> int:
        params = {}
        if edge_type:
            params["edgeType"] = edge_type
        data = self._request("GET", "/api/v1/schema/stats/edge-count", params=params)
        return data.get("count", 0)

    def labels(self) -> list[str]:
        data = self._request("GET", "/api/v1/schema/labels")
        if isinstance(data, list):
            return [item.get("Name", item) if isinstance(item, dict) else str(item) for item in data]
        return []

    def edge_types(self) -> list[str]:
        data = self._request("GET", "/api/v1/schema/edge-types")
        if isinstance(data, list):
            return [item.get("Name", item) if isinstance(item, dict) else str(item) for item in data]
        return []
```

- [ ] **Step 2: Modify `graph_db/config.py` — fix connect() for non-Neo4j backends and register trs_graph**

In `graph_db/config.py`, replace the `_ensure_backends()` function and the `if backend_name == "neo4j"` block in `connect()`:

```python
def _ensure_backends() -> None:
    """Lazily register built-in backends."""
    if _BACKEND_REGISTRY:
        return
    # Import and register Neo4j backend
    from graph_db.backends.neo4j_backend import Neo4jGraphDatabase
    register_backend("neo4j", Neo4jGraphDatabase)
    # Import and register TRS Graph backend
    from graph_db.backends.trs_graph_backend import TRSGraphDatabase
    register_backend("trs_graph", TRSGraphDatabase)
```

And replace lines 136-144 in `connect()`:

```python
    # Instantiate with backend-specific args
    if backend_name == "neo4j":
        db = cls(
            uri=config.uri,
            auth=(config.username, config.password),
            database=config.database,
        )
    elif backend_name == "trs_graph":
        db = cls(
            base_url=config.uri,
            graph_space=config.database,
            timeout=config.connection_timeout,
        )
    else:
        db = cls(config=config)
```

- [ ] **Step 3: Modify `graph_db/backends/__init__.py`**

```python
"""Backend implementations for the graph database API."""

from graph_db.backends.neo4j_backend import Neo4jGraphDatabase
from graph_db.backends.trs_graph_backend import TRSGraphDatabase

__all__ = ["Neo4jGraphDatabase", "TRSGraphDatabase"]
```

- [ ] **Step 4: Modify `graph_db/__init__.py` — add TRSGraphDatabase to exports**

Add import and export:

```python
# In the lazy-import section, add:
from graph_db.backends import Neo4jGraphDatabase, TRSGraphDatabase

# Add to __all__:
    "TRSGraphDatabase",
```

- [ ] **Step 5: Write basic test for TRS Graph backend connection**

Create `tests/test_trs_graph_backend.py`:

```python
"""Tests for TRS Graph backend."""
import pytest
from unittest.mock import patch, MagicMock
from graph_db.backends.trs_graph_backend import TRSGraphDatabase, _trs_node_to_model, _trs_edge_to_model
from graph_db.models import Node, Edge


class TestTrsNodeEdgeConversion:
    def test_trs_node_to_model(self):
        data = {"id": "talent_001", "labels": ["talent"], "properties": {"name_zh": "张伟"}}
        node = _trs_node_to_model(data)
        assert node.id == "talent_001"
        assert node.labels == ["talent"]
        assert node.properties["name_zh"] == "张伟"

    def test_trs_edge_to_model(self):
        data = {"id": "talent_001->paper_001@0", "type": "bind_talent_paper_author", "sourceId": "talent_001", "targetId": "paper_001", "properties": {"confidence": 0.95}}
        edge = _trs_edge_to_model(data)
        assert edge.source_id == "talent_001"
        assert edge.target_id == "paper_001"
        assert edge.type == "bind_talent_paper_author"
        assert edge.properties["confidence"] == 0.95


class TestTRSGraphDatabaseConnection:
    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_connect_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "UP"}
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase(base_url="http://localhost:8090", graph_space="test_space")
        db.connect()
        assert db.is_connected()

    def test_connect_not_initialized(self):
        db = TRSGraphDatabase()
        with pytest.raises(RuntimeError, match="Not connected"):
            db._request("GET", "/health")

    @patch("graph_db.backends.trs_graph_backend.httpx.Client")
    def test_close(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "UP"}
        mock_response.raise_for_status.return_value = None
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        db = TRSGraphDatabase()
        db.connect()
        db.close()
        assert db._client is None
```

- [ ] **Step 6: Run tests to verify**

Run: `cd /data1/huyatao/tech-kg-api && python -m pytest tests/test_trs_graph_backend.py -v`
Expected: PASS

- [ ] **Step 7: Verify import works**

Run: `cd /data1/huyatao/tech-kg-api && python -c "from graph_db import TRSGraphDatabase; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add graph_db/backends/trs_graph_backend.py graph_db/config.py graph_db/backends/__init__.py graph_db/__init__.py tests/test_trs_graph_backend.py
git commit -m "feat: add TRS Graph backend for graph_db abstraction layer"
```

---

### Task 2: 规则召回匹配逻辑

**Files:**
- Create: `app/services/binding_matcher.py`
- Create: `tests/test_binding_matcher.py`

- [ ] **Step 1: Write failing tests for BindingMatcher**

Create `tests/test_binding_matcher.py`:

```python
"""Tests for the rule-based binding matcher."""
import pytest
from app.services.binding_matcher import BindingMatcher, jaccard_similarity, edit_distance_similarity


class TestJaccardSimilarity:
    def test_identical_sets(self):
        assert jaccard_similarity("清华大学", "清华大学") == 1.0

    def test_partial_overlap(self):
        sim = jaccard_similarity("清华大学", "清华")
        assert 0.0 < sim < 1.0

    def test_no_overlap(self):
        assert jaccard_similarity("清华大学", "北京大学") == 0.0

    def test_empty_strings(self):
        assert jaccard_similarity("", "") == 0.0


class TestEditDistanceSimilarity:
    def test_identical(self):
        assert edit_distance_similarity("浙江大学", "浙江大学") == 1.0

    def test_similar(self):
        sim = edit_distance_similarity("浙江大学", "浙大")
        assert sim > 0.5

    def test_completely_different(self):
        sim = edit_distance_similarity("清华大学", "复旦大学")
        assert sim < 0.5


class TestBindingMatcherTalentPaper:
    def setup_method(self):
        self.matcher = BindingMatcher()

    def test_name_exact_match(self):
        talent = {"name_zh": "张伟", "name_en": "Wei Zhang", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        paper = {"authors": "张伟", "institution": "清华大学", "keywords": "知识图谱;实体对齐"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 1
        assert pairs[0]["rule_score"] >= 0.5

    def test_name_no_match(self):
        talent = {"name_zh": "张伟", "name_en": "Wei Zhang", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        paper = {"authors": "赵磊", "institution": "中科院", "keywords": "推荐系统"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 0

    def test_name_match_org_abbreviation(self):
        """浙大 should match 浙江大学 via edit distance similarity."""
        talent = {"name_zh": "王芳", "name_en": "Fang Wang", "scholar_org_name_zh": "浙江大学", "fields": "计算机视觉"}
        paper = {"authors": "王芳", "institution": "浙大", "keywords": "计算机视觉;深度学习"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 1

    def test_below_threshold_not_returned(self):
        talent = {"name_zh": "张伟", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        paper = {"authors": "不同的人", "institution": "不同的大学", "keywords": "完全不同"}
        pairs = self.matcher.match_talent_paper([talent], [paper])
        assert len(pairs) == 0


class TestBindingMatcherTalentPatent:
    def setup_method(self):
        self.matcher = BindingMatcher()

    def test_inventor_match(self):
        talent = {"name_zh": "张伟", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        patent = {"first_inventor_name": "张伟", "first_applicant_name": "清华大学", "title_zh": "知识图谱构建方法"}
        pairs = self.matcher.match_talent_patent([talent], [patent])
        assert len(pairs) == 1

    def test_inventor_no_match(self):
        talent = {"name_zh": "张伟", "scholar_org_name_zh": "清华大学", "fields": "知识图谱"}
        patent = {"first_inventor_name": "赵磊", "first_applicant_name": "中科院", "title_zh": "智能推荐"}
        pairs = self.matcher.match_talent_patent([talent], [patent])
        assert len(pairs) == 0


class TestBindingMatcherOrgOrg:
    def setup_method(self):
        self.matcher = BindingMatcher()

    def test_same_org_name(self):
        org_a = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        org_b = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        pairs = self.matcher.match_org_org([org_a], [org_b])
        assert len(pairs) == 1
        assert pairs[0]["rule_score"] >= 0.6

    def test_sub_org_match(self):
        org_a = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        org_b = {"name_cn": "清华大学计算机系", "province": "北京市", "city": "北京", "org_type": "院系"}
        pairs = self.matcher.match_org_org([org_a], [org_b])
        assert len(pairs) == 1

    def test_no_match(self):
        org_a = {"name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"}
        org_b = {"name_cn": "浙江大学", "province": "浙江省", "city": "杭州", "org_type": "高等院校"}
        pairs = self.matcher.match_org_org([org_a], [org_b])
        assert len(pairs) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /data1/huyatao/tech-kg-api && python -m pytest tests/test_binding_matcher.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement BindingMatcher**

Create `app/services/binding_matcher.py`:

```python
"""Rule-based binding matcher for cross-database entity alignment.

Provides similarity functions and matching logic for:
- talent ↔ cn_paper author
- talent ↔ patent inventor
- cn_organization ↔ cn_organization
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def jaccard_similarity(a: str, b: str) -> float:
    """Character-level Jaccard similarity between two strings."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def edit_distance_similarity(a: str, b: str) -> float:
    """Normalized edit distance similarity (1 - normalized_distance)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    m, n = len(a), len(b)
    # Dynamic programming edit distance
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    distance = dp[n]
    max_len = max(m, n)
    return 1.0 - (distance / max_len)


def name_match_score(name_a: str, name_b: str) -> float:
    """Score name similarity using both exact match and edit distance."""
    if not name_a or not name_b:
        return 0.0
    name_a = name_a.strip()
    name_b = name_b.strip()
    if name_a == name_b:
        return 1.0
    # Use edit distance for fuzzy matching
    return edit_distance_similarity(name_a, name_b)


def org_similarity_score(org_a: str, org_b: str) -> float:
    """Score organization name similarity using Jaccard + edit distance."""
    if not org_a or not org_b:
        return 0.0
    org_a = org_a.strip()
    org_b = org_b.strip()
    if org_a == org_b:
        return 1.0
    # Combine Jaccard and edit distance for better handling of abbreviations
    jaccard = jaccard_similarity(org_a, org_b)
    edit_sim = edit_distance_similarity(org_a, org_b)
    # Also check containment (e.g., "浙大" in "浙江大学")
    containment = 0.0
    if org_a in org_b or org_b in org_a:
        containment = min(len(org_a), len(org_b)) / max(len(org_a), len(org_b))
    return max(jaccard, edit_sim, containment)


class BindingMatcher:
    """Rule-based matcher for cross-database entity binding candidates."""

    # Weight configs for different binding types
    TALENT_PAPER_WEIGHTS = {"name": 0.6, "org": 0.3, "field": 0.1}
    TALENT_PAPER_THRESHOLD = 0.5

    TALENT_PATENT_WEIGHTS = {"name": 0.7, "org": 0.3}
    TALENT_PATENT_THRESHOLD = 0.5

    ORG_ORG_THRESHOLD = 0.6

    def match_talent_paper(
        self,
        talents: list[dict[str, Any]],
        papers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Match talent nodes to cn_paper author nodes.

        Returns list of candidate binding pairs with rule scores.
        Each pair: {"talent": dict, "paper": dict, "rule_score": float, "name_score": float, "org_score": float, "field_score": float}
        """
        candidates = []
        w = self.TALENT_PAPER_WEIGHTS

        for talent in talents:
            for paper in papers:
                name_score = name_match_score(
                    talent.get("name_zh", ""),
                    paper.get("authors", ""),
                )
                # Also try English name match
                if name_score < 1.0:
                    en_score = name_match_score(
                        talent.get("name_en", ""),
                        paper.get("authors", ""),
                    )
                    name_score = max(name_score, en_score)

                org_score = org_similarity_score(
                    talent.get("scholar_org_name_zh", ""),
                    paper.get("institution", ""),
                )
                # Also try English org match
                if org_score < 1.0:
                    en_org_score = org_similarity_score(
                        talent.get("scholar_org_name_en", ""),
                        paper.get("institution", ""),
                    )
                    org_score = max(org_score, en_org_score)

                field_score = jaccard_similarity(
                    talent.get("fields", ""),
                    paper.get("keywords", ""),
                )

                rule_score = (
                    w["name"] * name_score
                    + w["org"] * org_score
                    + w["field"] * field_score
                )

                if rule_score >= self.TALENT_PAPER_THRESHOLD:
                    candidates.append({
                        "talent": talent,
                        "paper": paper,
                        "rule_score": round(rule_score, 4),
                        "name_score": round(name_score, 4),
                        "org_score": round(org_score, 4),
                        "field_score": round(field_score, 4),
                    })

        return candidates

    def match_talent_patent(
        self,
        talents: list[dict[str, Any]],
        patents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Match talent nodes to patent inventor nodes."""
        candidates = []
        w = self.TALENT_PATENT_WEIGHTS

        for talent in talents:
            for patent in patents:
                name_score = name_match_score(
                    talent.get("name_zh", ""),
                    patent.get("first_inventor_name", ""),
                )

                org_score = org_similarity_score(
                    talent.get("scholar_org_name_zh", ""),
                    patent.get("first_applicant_name", ""),
                )

                rule_score = (
                    w["name"] * name_score
                    + w["org"] * org_score
                )

                if rule_score >= self.TALENT_PATENT_THRESHOLD:
                    candidates.append({
                        "talent": talent,
                        "patent": patent,
                        "rule_score": round(rule_score, 4),
                        "name_score": round(name_score, 4),
                        "org_score": round(org_score, 4),
                    })

        return candidates

    def match_org_org(
        self,
        orgs_a: list[dict[str, Any]],
        orgs_b: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Match organization nodes across databases."""
        candidates = []

        for org_a in orgs_a:
            for org_b in orgs_b:
                # Skip self-match
                if org_a.get("org_id") and org_a["org_id"] == org_b.get("org_id"):
                    continue

                name_sim = org_similarity_score(
                    org_a.get("name_cn", ""),
                    org_b.get("name_cn", ""),
                )

                # Bonus for same province/city
                geo_bonus = 0.0
                if org_a.get("province") and org_a["province"] == org_b.get("province"):
                    geo_bonus += 0.1
                if org_a.get("city") and org_a["city"] == org_b.get("city"):
                    geo_bonus += 0.1

                # Bonus for same type
                type_bonus = 0.0
                if org_a.get("org_type") and org_a["org_type"] == org_b.get("org_type"):
                    type_bonus = 0.05

                rule_score = min(name_sim + geo_bonus + type_bonus, 1.0)

                if rule_score >= self.ORG_ORG_THRESHOLD:
                    candidates.append({
                        "org_a": org_a,
                        "org_b": org_b,
                        "rule_score": round(rule_score, 4),
                        "name_score": round(name_sim, 4),
                        "geo_bonus": round(geo_bonus, 4),
                        "type_bonus": round(type_bonus, 4),
                    })

        return candidates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /data1/huyatao/tech-kg-api && python -m pytest tests/test_binding_matcher.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/binding_matcher.py tests/test_binding_matcher.py
git commit -m "feat: add rule-based binding matcher with similarity functions"
```

---

### Task 3: 绑定核心 Pipeline（含 LLM 精排）

**Files:**
- Create: `app/schemas/entity_binding.py`
- Create: `app/services/entity_binding.py`

- [ ] **Step 1: Create schemas for entity binding**

Create `app/schemas/entity_binding.py`:

```python
"""Entity binding request/response data models."""

from typing import Optional
from pydantic import BaseModel


class BindingExecuteRequest(BaseModel):
    binding_type: str = "all"  # "talent_paper" | "talent_patent" | "org_org" | "all"


class BindingPairDetail(BaseModel):
    source_name: str
    source_id: str
    source_label: str
    target_name: str
    target_id: str
    target_label: str
    confidence: float
    method: str
    rule_score: float
    llm_score: float
    status: str
    reason: str = ""


class BindingResult(BaseModel):
    binding_type: str
    total_candidates: int = 0
    confirmed: int = 0
    candidate: int = 0
    rejected: int = 0
    details: list[BindingPairDetail] = []


class BindingStatsResponse(BaseModel):
    talent_paper: Optional[BindingResult] = None
    talent_patent: Optional[BindingResult] = None
    org_org: Optional[BindingResult] = None
    total_confirmed: int = 0
    total_candidates: int = 0


class BindingGraphResponse(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []


class InitDataResponse(BaseModel):
    edge_types_created: list[str] = []
    indexes_created: list[str] = []
    nodes_inserted: dict[str, int] = {}
    message: str = ""


class ClearResponse(BaseModel):
    message: str = ""
    edges_deleted: int = 0
```

- [ ] **Step 2: Implement EntityBindingService**

Create `app/services/entity_binding.py`:

```python
"""Entity binding service — cross-database entity alignment pipeline.

Pipeline: data recall -> rule matching -> LLM refinement -> write binding edges.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from graph_db.base import GraphDatabase
from app.services.binding_matcher import BindingMatcher
from app.schemas.entity_binding import BindingResult, BindingPairDetail

load_dotenv()

logger = logging.getLogger(__name__)

# LLM setup
try:
    from zai import ZhipuAiClient
except ImportError:
    ZhipuAiClient = None

API_KEY = os.getenv("ZHIPUAI_API_KEY", "")
MODEL = os.getenv("BINDING_MODEL", "glm-4-flash")
_client = ZhipuAiClient(api_key=API_KEY) if ZhipuAiClient and API_KEY else None


# --- Test data definitions ---

TALENT_DATA = [
    {
        "scholar_id": "talent_001", "name_zh": "张伟", "name_en": "Wei Zhang",
        "scholar_org_name_zh": "清华大学", "scholar_org_name_en": "Tsinghua University",
        "fields": "知识图谱", "paper_nums": 35, "citation_nums": 1200,
        "h_index": 12, "status": 1,
    },
    {
        "scholar_id": "talent_002", "name_zh": "李明", "name_en": "Ming Li",
        "scholar_org_name_zh": "北京大学", "scholar_org_name_en": "Peking University",
        "fields": "自然语言处理", "paper_nums": 28, "citation_nums": 890,
        "h_index": 10, "status": 1,
    },
    {
        "scholar_id": "talent_003", "name_zh": "王芳", "name_en": "Fang Wang",
        "scholar_org_name_zh": "浙江大学", "scholar_org_name_en": "Zhejiang University",
        "fields": "计算机视觉", "paper_nums": 22, "citation_nums": 560,
        "h_index": 8, "status": 1,
    },
    {
        "scholar_id": "talent_004", "name_zh": "刘洋", "name_en": "Yang Liu",
        "scholar_org_name_zh": "清华大学", "scholar_org_name_en": "Tsinghua University",
        "fields": "机器学习", "paper_nums": 40, "citation_nums": 2100,
        "h_index": 15, "status": 1,
    },
    {
        "scholar_id": "talent_005", "name_zh": "陈静", "name_en": "Jing Chen",
        "scholar_org_name_zh": "复旦大学", "scholar_org_name_en": "Fudan University",
        "fields": "数据挖掘", "paper_nums": 18, "citation_nums": 430,
        "h_index": 7, "status": 1,
    },
]

PAPER_DATA = [
    {
        "id": "paper_001", "zh_name": "基于知识图谱的实体对齐方法研究", "en_name": "Entity Alignment in Knowledge Graphs",
        "authors": "张伟", "author_id": "auth_001", "author_sequence": 1,
        "institution": "清华大学", "cover_date_start": "2024-03-15",
        "keywords": "知识图谱;实体对齐", "doi": "10.1234/kg001",
    },
    {
        "id": "paper_002", "zh_name": "NLP前沿技术综述", "en_name": "Advances in NLP",
        "authors": "李明", "author_id": "auth_002", "author_sequence": 1,
        "institution": "北京大学", "cover_date_start": "2024-05-20",
        "keywords": "自然语言处理;深度学习", "doi": "10.1234/nlp002",
    },
    {
        "id": "paper_003", "zh_name": "深度学习在CV中的应用", "en_name": "Deep Learning for Computer Vision",
        "authors": "王芳", "author_id": "auth_003", "author_sequence": 1,
        "institution": "浙大", "cover_date_start": "2024-01-10",
        "keywords": "计算机视觉;深度学习", "doi": "10.1234/cv003",
    },
    {
        "id": "paper_004", "zh_name": "机器学习优化方法研究", "en_name": "Optimization Methods in ML",
        "authors": "刘洋", "author_id": "auth_004", "author_sequence": 1,
        "institution": "清华大学计算机系", "cover_date_start": "2023-11-08",
        "keywords": "机器学习;优化算法", "doi": "10.1234/ml004",
    },
    {
        "id": "paper_005", "zh_name": "知识图谱构建技术研究", "en_name": "Knowledge Graph Construction",
        "authors": "张伟", "author_id": "auth_005", "author_sequence": 1,
        "institution": "Tsinghua University", "cover_date_start": "2024-06-01",
        "keywords": "知识图谱;图构建", "doi": "10.1234/kg005",
    },
    {
        "id": "paper_006", "zh_name": "数据挖掘方法综述", "en_name": "Data Mining Survey",
        "authors": "陈静", "author_id": "auth_006", "author_sequence": 1,
        "institution": "复旦大学", "cover_date_start": "2023-09-15",
        "keywords": "数据挖掘;机器学习", "doi": "10.1234/dm006",
    },
]

PATENT_DATA = [
    {
        "patent_id": "patent_001", "title_zh": "知识图谱构建方法", "title_localized": "Knowledge Graph Construction Method",
        "first_inventor_name": "张伟", "first_applicant_name": "清华大学",
        "country_code": "CN", "classification_ipcr": "G06F16.36", "keywords": "知识图谱;图数据库",
    },
    {
        "patent_id": "patent_002", "title_zh": "自然语言处理装置", "title_localized": "NLP Processing Apparatus",
        "first_inventor_name": "李明", "first_applicant_name": "北京大学",
        "country_code": "CN", "classification_ipcr": "G06F40.30", "keywords": "自然语言处理;语义分析",
    },
    {
        "patent_id": "patent_003", "title_zh": "图像识别系统", "title_localized": "Image Recognition System",
        "first_inventor_name": "王芳", "first_applicant_name": "浙江大学",
        "country_code": "CN", "classification_ipcr": "G06V10.00", "keywords": "计算机视觉;图像识别",
    },
    {
        "patent_id": "patent_004", "title_zh": "智能推荐算法", "title_localized": "Intelligent Recommendation Algorithm",
        "first_inventor_name": "赵磊", "first_applicant_name": "中科院",
        "country_code": "CN", "classification_ipcr": "G06F16.95", "keywords": "推荐系统;协同过滤",
    },
]

ORG_DATA = [
    {"org_id": "org_001", "name_cn": "清华大学", "province": "北京市", "city": "北京", "org_type": "高等院校"},
    {"org_id": "org_002", "name_cn": "北京大学", "province": "北京市", "city": "北京", "org_type": "高等院校"},
    {"org_id": "org_003", "name_cn": "浙江大学", "province": "浙江省", "city": "杭州", "org_type": "高等院校"},
    {"org_id": "org_004", "name_cn": "清华大学计算机系", "province": "北京市", "city": "北京", "org_type": "院系"},
]

EDGE_NGQLS = [
    "CREATE EDGE IF NOT EXISTS bind_talent_paper_author(confidence double, method string, bound_at string, rule_score double, llm_score double, status string)",
    "CREATE EDGE IF NOT EXISTS bind_talent_patent_inventor(confidence double, method string, bound_at string, rule_score double, llm_score double, status string)",
    "CREATE EDGE IF NOT EXISTS bind_org_org(confidence double, method string, bound_at string, rule_score double, llm_score double, status string)",
]

INDEX_NGQLS = [
    "CREATE TAG INDEX IF NOT EXISTS idx_talent_name ON talent(name_zh)",
    "CREATE TAG INDEX IF NOT EXISTS idx_talent_name_en ON talent(name_en)",
    "CREATE TAG INDEX IF NOT EXISTS idx_talent_org ON talent(scholar_org_name_zh)",
    "CREATE TAG INDEX IF NOT EXISTS idx_paper_author ON cn_paper(authors)",
    "CREATE TAG INDEX IF NOT EXISTS idx_paper_author_id ON cn_paper(author_id)",
    "CREATE TAG INDEX IF NOT EXISTS idx_paper_inst ON cn_paper(institution)",
    "CREATE TAG INDEX IF NOT EXISTS idx_patent_inventor ON patent(first_inventor_name)",
    "CREATE TAG INDEX IF NOT EXISTS idx_patent_applicant ON patent(first_applicant_name)",
    "CREATE TAG INDEX IF NOT EXISTS idx_org_name ON cn_organization(name_cn)",
]


def _llm_judge(entity_a_desc: str, entity_b_desc: str, source_db: str, target_db: str) -> dict[str, Any] | None:
    """Use LLM to judge if two entities are the same real-world entity."""
    if _client is None:
        logger.warning("LLM client not available, skipping LLM refinement")
        return None

    prompt = f"""你是一个实体对齐专家。请判断以下两个实体是否为同一个现实实体。

实体A（来自{source_db}）：{entity_a_desc}
实体B（来自{target_db}）：{entity_b_desc}

请严格以JSON格式回答：
{{"is_same": true或false, "confidence": 0.0到1.0之间的数字, "reason": "判断理由"}}"""

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = response.choices[0].message.content.strip()
        # Extract JSON from response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
        return result
    except Exception as e:
        logger.error(f"LLM judge failed: {e}")
        return None


def _summarize_entity(props: dict[str, Any], key_fields: list[str]) -> str:
    """Create a short text summary of an entity for LLM prompt."""
    parts = []
    for field in key_fields:
        val = props.get(field)
        if val:
            parts.append(f"{field}={val}")
    return "; ".join(parts)


class EntityBindingService:
    """Core service for cross-database entity binding."""

    def __init__(self, graph_db: GraphDatabase):
        self.db = graph_db
        self.matcher = BindingMatcher()
        # Cache for binding results
        self._results: dict[str, BindingResult] = {}

    def init_data(self) -> dict[str, Any]:
        """Initialize test data: create edge types, indexes, and insert nodes."""
        # 1. Create edge types
        edges_created = []
        for ngql in EDGE_NGQLS:
            try:
                self.db.execute_write(ngql)
                edges_created.append(ngql.split("NOT EXISTS ")[1].split("(")[0].strip())
            except Exception as e:
                logger.warning(f"Edge creation may already exist: {e}")

        # 2. Create indexes
        indexes_created = []
        for ngql in INDEX_NGQLS:
            try:
                self.db.execute_write(ngql)
                idx_name = ngql.split("NOT EXISTS ")[1].split(" ON")[0].strip()
                indexes_created.append(idx_name)
            except Exception as e:
                logger.warning(f"Index creation may already exist: {e}")

        # 3. Insert talent nodes
        talent_count = 0
        for t in TALENT_DATA:
            try:
                self.db.create_node(["talent"], t)
                talent_count += 1
            except Exception as e:
                logger.warning(f"Talent insert failed for {t.get('scholar_id')}: {e}")

        # 4. Insert paper nodes
        paper_count = 0
        for p in PAPER_DATA:
            try:
                self.db.create_node(["cn_paper"], p)
                paper_count += 1
            except Exception as e:
                logger.warning(f"Paper insert failed for {p.get('id')}: {e}")

        # 5. Insert patent nodes
        patent_count = 0
        for p in PATENT_DATA:
            try:
                self.db.create_node(["patent"], p)
                patent_count += 1
            except Exception as e:
                logger.warning(f"Patent insert failed for {p.get('patent_id')}: {e}")

        # 6. Insert org nodes
        org_count = 0
        for o in ORG_DATA:
            try:
                self.db.create_node(["cn_organization"], o)
                org_count += 1
            except Exception as e:
                logger.warning(f"Org insert failed for {o.get('org_id')}: {e}")

        return {
            "edge_types_created": edges_created,
            "indexes_created": indexes_created,
            "nodes_inserted": {
                "talent": talent_count,
                "cn_paper": paper_count,
                "patent": patent_count,
                "cn_organization": org_count,
            },
            "message": "初始化完成",
        }

    def _fetch_all_nodes(self, label: str) -> list[dict[str, Any]]:
        """Fetch all nodes of a given label as property dicts."""
        nodes = []
        offset = 0
        limit = 100
        while True:
            result = self.db.get_nodes_by_label(label, limit=limit, offset=offset)
            for node in result.items:
                nodes.append(node.properties)
            if not result.page.has_next:
                break
            offset += limit
        return nodes

    def bind_talent_paper(self) -> BindingResult:
        """Execute talent ↔ paper author binding pipeline."""
        talents = self._fetch_all_nodes("talent")
        papers = self._fetch_all_nodes("cn_paper")

        candidates = self.matcher.match_talent_paper(talents, papers)

        details = []
        confirmed = 0
        candidate_count = 0
        rejected = 0

        for pair in candidates:
            talent = pair["talent"]
            paper = pair["paper"]

            # LLM refinement
            entity_a_desc = _summarize_entity(talent, ["name_zh", "name_en", "scholar_org_name_zh", "scholar_org_name_en", "fields"])
            entity_b_desc = _summarize_entity(paper, ["authors", "institution", "keywords"])

            llm_result = _llm_judge(entity_a_desc, entity_b_desc, "人才库", "论文库")

            llm_score = 0.0
            is_same = False
            reason = ""
            if llm_result:
                llm_score = float(llm_result.get("confidence", 0.0))
                is_same = llm_result.get("is_same", False)
                reason = llm_result.get("reason", "")
            else:
                # Fallback: use rule score only
                llm_score = pair["rule_score"]
                is_same = pair["rule_score"] >= 0.7

            # Determine status
            if is_same and llm_score >= 0.7:
                status = "confirmed"
                confirmed += 1
            elif is_same and llm_score >= 0.5:
                status = "candidate"
                candidate_count += 1
            else:
                rejected += 1
                continue

            confidence = (pair["rule_score"] + llm_score) / 2 if llm_result else pair["rule_score"]
            method = "rule+llm" if llm_result else "rule"

            # Write binding edge
            try:
                self.db.create_edge(
                    source_id=talent.get("scholar_id", ""),
                    target_id=paper.get("id", ""),
                    edge_type="bind_talent_paper_author",
                    properties={
                        "confidence": round(confidence, 4),
                        "method": method,
                        "bound_at": datetime.now().isoformat(),
                        "rule_score": pair["rule_score"],
                        "llm_score": round(llm_score, 4),
                        "status": status,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to create binding edge: {e}")

            details.append(BindingPairDetail(
                source_name=talent.get("name_zh", ""),
                source_id=talent.get("scholar_id", ""),
                source_label="talent",
                target_name=paper.get("zh_name", ""),
                target_id=paper.get("id", ""),
                target_label="cn_paper",
                confidence=round(confidence, 4),
                method=method,
                rule_score=pair["rule_score"],
                llm_score=round(llm_score, 4),
                status=status,
                reason=reason,
            ))

        result = BindingResult(
            binding_type="talent_paper",
            total_candidates=len(candidates),
            confirmed=confirmed,
            candidate=candidate_count,
            rejected=rejected,
            details=details,
        )
        self._results["talent_paper"] = result
        return result

    def bind_talent_patent(self) -> BindingResult:
        """Execute talent ↔ patent inventor binding pipeline."""
        talents = self._fetch_all_nodes("talent")
        patents = self._fetch_all_nodes("patent")

        candidates = self.matcher.match_talent_patent(talents, patents)

        details = []
        confirmed = 0
        candidate_count = 0
        rejected = 0

        for pair in candidates:
            talent = pair["talent"]
            patent = pair["patent"]

            entity_a_desc = _summarize_entity(talent, ["name_zh", "scholar_org_name_zh", "fields"])
            entity_b_desc = _summarize_entity(patent, ["first_inventor_name", "first_applicant_name", "title_zh"])

            llm_result = _llm_judge(entity_a_desc, entity_b_desc, "人才库", "专利库")

            llm_score = 0.0
            is_same = False
            reason = ""
            if llm_result:
                llm_score = float(llm_result.get("confidence", 0.0))
                is_same = llm_result.get("is_same", False)
                reason = llm_result.get("reason", "")
            else:
                llm_score = pair["rule_score"]
                is_same = pair["rule_score"] >= 0.7

            if is_same and llm_score >= 0.7:
                status = "confirmed"
                confirmed += 1
            elif is_same and llm_score >= 0.5:
                status = "candidate"
                candidate_count += 1
            else:
                rejected += 1
                continue

            confidence = (pair["rule_score"] + llm_score) / 2 if llm_result else pair["rule_score"]
            method = "rule+llm" if llm_result else "rule"

            try:
                self.db.create_edge(
                    source_id=talent.get("scholar_id", ""),
                    target_id=patent.get("patent_id", ""),
                    edge_type="bind_talent_patent_inventor",
                    properties={
                        "confidence": round(confidence, 4),
                        "method": method,
                        "bound_at": datetime.now().isoformat(),
                        "rule_score": pair["rule_score"],
                        "llm_score": round(llm_score, 4),
                        "status": status,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to create binding edge: {e}")

            details.append(BindingPairDetail(
                source_name=talent.get("name_zh", ""),
                source_id=talent.get("scholar_id", ""),
                source_label="talent",
                target_name=patent.get("title_zh", ""),
                target_id=patent.get("patent_id", ""),
                target_label="patent",
                confidence=round(confidence, 4),
                method=method,
                rule_score=pair["rule_score"],
                llm_score=round(llm_score, 4),
                status=status,
                reason=reason,
            ))

        result = BindingResult(
            binding_type="talent_patent",
            total_candidates=len(candidates),
            confirmed=confirmed,
            candidate=candidate_count,
            rejected=rejected,
            details=details,
        )
        self._results["talent_patent"] = result
        return result

    def bind_org_org(self) -> BindingResult:
        """Execute organization ↔ organization binding pipeline."""
        orgs = self._fetch_all_nodes("cn_organization")

        candidates = self.matcher.match_org_org(orgs, orgs)

        details = []
        confirmed = 0
        candidate_count = 0
        rejected = 0

        for pair in candidates:
            org_a = pair["org_a"]
            org_b = pair["org_b"]

            entity_a_desc = _summarize_entity(org_a, ["name_cn", "province", "city", "org_type"])
            entity_b_desc = _summarize_entity(org_b, ["name_cn", "province", "city", "org_type"])

            llm_result = _llm_judge(entity_a_desc, entity_b_desc, "机构库A", "机构库B")

            llm_score = 0.0
            is_same = False
            reason = ""
            if llm_result:
                llm_score = float(llm_result.get("confidence", 0.0))
                is_same = llm_result.get("is_same", False)
                reason = llm_result.get("reason", "")
            else:
                llm_score = pair["rule_score"]
                is_same = pair["rule_score"] >= 0.7

            if is_same and llm_score >= 0.7:
                status = "confirmed"
                confirmed += 1
            elif is_same and llm_score >= 0.5:
                status = "candidate"
                candidate_count += 1
            else:
                rejected += 1
                continue

            confidence = (pair["rule_score"] + llm_score) / 2 if llm_result else pair["rule_score"]
            method = "rule+llm" if llm_result else "rule"

            try:
                self.db.create_edge(
                    source_id=org_a.get("org_id", ""),
                    target_id=org_b.get("org_id", ""),
                    edge_type="bind_org_org",
                    properties={
                        "confidence": round(confidence, 4),
                        "method": method,
                        "bound_at": datetime.now().isoformat(),
                        "rule_score": pair["rule_score"],
                        "llm_score": round(llm_score, 4),
                        "status": status,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to create binding edge: {e}")

            details.append(BindingPairDetail(
                source_name=org_a.get("name_cn", ""),
                source_id=org_a.get("org_id", ""),
                source_label="cn_organization",
                target_name=org_b.get("name_cn", ""),
                target_id=org_b.get("org_id", ""),
                target_label="cn_organization",
                confidence=round(confidence, 4),
                method=method,
                rule_score=pair["rule_score"],
                llm_score=round(llm_score, 4),
                status=status,
                reason=reason,
            ))

        result = BindingResult(
            binding_type="org_org",
            total_candidates=len(candidates),
            confirmed=confirmed,
            candidate=candidate_count,
            rejected=rejected,
            details=details,
        )
        self._results["org_org"] = result
        return result

    def bind_all(self) -> dict[str, Any]:
        """Execute all binding types."""
        tp = self.bind_talent_paper()
        tpt = self.bind_talent_patent()
        oo = self.bind_org_org()
        return {
            "talent_paper": tp.model_dump(),
            "talent_patent": tpt.model_dump(),
            "org_org": oo.model_dump(),
            "total_confirmed": tp.confirmed + tpt.confirmed + oo.confirmed,
            "total_candidates": tp.candidate + tpt.candidate + oo.candidate,
        }

    def get_binding_stats(self) -> dict[str, Any]:
        """Get current binding statistics from graph."""
        stats = {}
        for edge_type in ["bind_talent_paper_author", "bind_talent_patent_inventor", "bind_org_org"]:
            edges_result = self.db.get_edges_by_type(edge_type, limit=1000)
            confirmed = 0
            candidate = 0
            for edge in edges_result.items:
                status = edge.properties.get("status", "")
                if status == "confirmed":
                    confirmed += 1
                elif status == "candidate":
                    candidate += 1
            stats[edge_type] = {
                "total": edges_result.page.total,
                "confirmed": confirmed,
                "candidate": candidate,
            }
        total_confirmed = sum(s["confirmed"] for s in stats.values())
        total_candidate = sum(s["candidate"] for s in stats.values())
        return {"binding_types": stats, "total_confirmed": total_confirmed, "total_candidates": total_candidate}

    def get_binding_detail(self, binding_type: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get binding detail list."""
        type_map = {
            "talent_paper": "bind_talent_paper_author",
            "talent_patent": "bind_talent_patent_inventor",
            "org_org": "bind_org_org",
        }
        edge_type = type_map.get(binding_type)
        if not edge_type:
            return []

        edges_result = self.db.get_edges_by_type(edge_type, limit=limit, offset=offset)
        details = []
        for edge in edges_result.items:
            details.append({
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "edge_type": edge.type,
                "confidence": edge.properties.get("confidence", 0),
                "method": edge.properties.get("method", ""),
                "rule_score": edge.properties.get("rule_score", 0),
                "llm_score": edge.properties.get("llm_score", 0),
                "status": edge.properties.get("status", ""),
                "bound_at": edge.properties.get("bound_at", ""),
            })
        return details

    def get_binding_graph(self) -> dict[str, Any]:
        """Get graph data for visualization."""
        nodes = []
        edges = []
        seen_node_ids = set()

        # Fetch all binding edges
        for edge_type in ["bind_talent_paper_author", "bind_talent_patent_inventor", "bind_org_org"]:
            edges_result = self.db.get_edges_by_type(edge_type, limit=1000)
            for edge in edges_result.items:
                # Add source node
                if edge.source_id not in seen_node_ids:
                    source_node = self.db.get_node(edge.source_id)
                    if source_node:
                        name = source_node.properties.get("name_zh") or source_node.properties.get("name_cn") or source_node.properties.get("zh_name") or source_node.properties.get("title_zh") or str(edge.source_id)
                        label = source_node.labels[0] if source_node.labels else "unknown"
                        nodes.append({"id": str(edge.source_id), "label": label, "name": name})
                        seen_node_ids.add(edge.source_id)

                # Add target node
                if edge.target_id not in seen_node_ids:
                    target_node = self.db.get_node(edge.target_id)
                    if target_node:
                        name = target_node.properties.get("name_zh") or target_node.properties.get("name_cn") or target_node.properties.get("zh_name") or target_node.properties.get("title_zh") or str(edge.target_id)
                        label = target_node.labels[0] if target_node.labels else "unknown"
                        nodes.append({"id": str(edge.target_id), "label": label, "name": name})
                        seen_node_ids.add(edge.target_id)

                edges.append({
                    "source": str(edge.source_id),
                    "target": str(edge.target_id),
                    "type": edge.type,
                    "confidence": edge.properties.get("confidence", 0),
                    "status": edge.properties.get("status", ""),
                })

        return {"nodes": nodes, "edges": edges}

    def clear_bindings(self, clear_data: bool = False) -> dict[str, Any]:
        """Clear binding edges, optionally also clear test data."""
        total_deleted = 0
        for edge_type in ["bind_talent_paper_author", "bind_talent_patent_inventor", "bind_org_org"]:
            try:
                edges_result = self.db.get_edges_by_type(edge_type, limit=1000)
                for edge in edges_result.items:
                    try:
                        self.db.delete_edge(edge.id)
                        total_deleted += 1
                    except Exception:
                        pass
            except Exception:
                pass

        if clear_data:
            for label in ["talent", "cn_paper", "patent", "cn_organization"]:
                try:
                    nodes_result = self.db.get_nodes_by_label(label, limit=1000)
                    for node in nodes_result.items:
                        try:
                            self.db.delete_node(node.id, detach=True)
                        except Exception:
                            pass
                except Exception:
                    pass

        return {"message": "绑定边已清除" + ("，测试数据已清除" if clear_data else ""), "edges_deleted": total_deleted}
```

- [ ] **Step 3: Verify import works**

Run: `cd /data1/huyatao/tech-kg-api && python -c "from app.services.entity_binding import EntityBindingService; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/schemas/entity_binding.py app/services/entity_binding.py
git commit -m "feat: add entity binding service with LLM refinement pipeline"
```

---

### Task 4: API 路由

**Files:**
- Create: `app/routers/entity_binding.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create the binding router**

Create `app/routers/entity_binding.py`:

```python
"""Entity binding API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from graph_db import connect, GraphDBConfig
from app.schemas.entity_binding import (
    BindingExecuteRequest,
    BindingResult,
    BindingStatsResponse,
    BindingGraphResponse,
    InitDataResponse,
    ClearResponse,
)
from app.services.entity_binding import EntityBindingService

router = APIRouter(prefix="/binding", tags=["Entity Binding"])


def _get_service() -> EntityBindingService:
    """Create an EntityBindingService with TRS Graph backend."""
    config = GraphDBConfig(
        backend="trs_graph",
        uri="http://localhost:8090",
        database="entity_binding_demo",
        connection_timeout=30,
    )
    db = connect(config)
    try:
        return EntityBindingService(db)
    except Exception:
        db.close()
        raise


@router.post("/init-data", response_model=InitDataResponse)
def init_data():
    """Initialize test data: create edge types, indexes, and insert nodes."""
    try:
        service = _get_service()
        result = service.init_data()
        service.db.close()
        return InitDataResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"初始化数据失败: {exc}") from exc


@router.post("/execute")
def execute_binding(body: BindingExecuteRequest):
    """Execute entity binding pipeline."""
    try:
        service = _get_service()
        if body.binding_type == "all":
            result = service.bind_all()
        elif body.binding_type == "talent_paper":
            result = service.bind_talent_paper().model_dump()
        elif body.binding_type == "talent_patent":
            result = service.bind_talent_patent().model_dump()
        elif body.binding_type == "org_org":
            result = service.bind_org_org().model_dump()
        else:
            service.db.close()
            raise HTTPException(status_code=400, detail=f"Unknown binding_type: {body.binding_type}")
        service.db.close()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"绑定执行失败: {exc}") from exc


@router.get("/stats")
def get_stats():
    """Get binding statistics."""
    try:
        service = _get_service()
        result = service.get_binding_stats()
        service.db.close()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {exc}") from exc


@router.get("/detail")
def get_detail(binding_type: str = Query("talent_paper"), limit: int = Query(100), offset: int = Query(0)):
    """Get binding detail list."""
    try:
        service = _get_service()
        result = service.get_binding_detail(binding_type, limit=limit, offset=offset)
        service.db.close()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取详情失败: {exc}") from exc


@router.get("/graph", response_model=BindingGraphResponse)
def get_graph():
    """Get graph data for visualization."""
    try:
        service = _get_service()
        result = service.get_binding_graph()
        service.db.close()
        return BindingGraphResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取图数据失败: {exc}") from exc


@router.delete("/clear", response_model=ClearResponse)
def clear_bindings(clear_data: bool = Query(False)):
    """Clear binding edges and optionally test data."""
    try:
        service = _get_service()
        result = service.clear_bindings(clear_data=clear_data)
        service.db.close()
        return ClearResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清除失败: {exc}") from exc
```

- [ ] **Step 2: Modify `app/main.py` to register the router and static files**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.routers.entity_linking import router as entity_linking_router
from app.routers.entity_extraction import router as entity_extraction_router
from app.routers.graphrag_demo import router as graphrag_demo_router
from app.routers.relation_extraction import router as relation_extraction_router
from app.routers.entity_binding import router as entity_binding_router

app = FastAPI(
    title="Tech KG API",
    description="亿级知识图谱 API 接口",
    version="0.1.0",
)

app.include_router(entity_linking_router, prefix="/api/v1")
app.include_router(entity_extraction_router, prefix="/api/v1")
app.include_router(graphrag_demo_router, prefix="/api/v1")
app.include_router(relation_extraction_router, prefix="/api/v1")
app.include_router(entity_binding_router, prefix="/api/v1")

# Mount static files for binding demo
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/hello")
def hello():
    return {"message": "Hello, Tech KG!"}


@app.get("/api")
def api_root():
    return {"message": "API is running", "version": "0.1.0"}


@app.get("/binding")
def binding_demo():
    """Serve the binding demo page."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "binding.html")
    if os.path.exists(static_path):
        return FileResponse(static_path)
    return {"message": "Binding demo page not found. Create app/static/binding.html"}
```

- [ ] **Step 3: Verify FastAPI app starts**

Run: `cd /data1/huyatao/tech-kg-api && python -c "from app.main import app; print('App created, routes:', [r.path for r in app.routes])"`
Expected: App loads without error, `/api/v1/binding/` routes listed

- [ ] **Step 4: Commit**

```bash
git add app/routers/entity_binding.py app/main.py
git commit -m "feat: add entity binding API routes and register in FastAPI app"
```

---

### Task 5: 前端展示页面

**Files:**
- Create: `app/static/binding.html`

- [ ] **Step 1: Create the binding demo HTML page**

Create `app/static/binding.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>跨库绑定 Demo</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; color: #333; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1 { text-align: center; margin-bottom: 20px; color: #1a73e8; }
        .section { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .section h2 { margin-bottom: 15px; color: #333; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; }
        button { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: all 0.2s; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: #1a73e8; color: #fff; }
        .btn-primary:hover:not(:disabled) { background: #1557b0; }
        .btn-success { background: #34a853; color: #fff; }
        .btn-success:hover:not(:disabled) { background: #2d8e47; }
        .btn-danger { background: #ea4335; color: #fff; }
        .btn-danger:hover:not(:disabled) { background: #c5372c; }
        .btn-warning { background: #fbbc04; color: #333; }
        .btn-warning:hover:not(:disabled) { background: #e0a800; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .stat-card { background: #f8f9fa; border-radius: 8px; padding: 15px; text-align: center; border-left: 4px solid #1a73e8; }
        .stat-card h3 { font-size: 14px; color: #666; margin-bottom: 8px; }
        .stat-card .number { font-size: 28px; font-weight: bold; color: #1a73e8; }
        .stat-card.confirmed { border-left-color: #34a853; }
        .stat-card.confirmed .number { color: #34a853; }
        .stat-card.candidate { border-left-color: #fbbc04; }
        .stat-card.candidate .number { color: #fbbc04; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }
        th { background: #f8f9fa; font-weight: 600; position: sticky; top: 0; }
        .status-badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
        .status-confirmed { background: #e6f4ea; color: #34a853; }
        .status-candidate { background: #fef7e0; color: #f9a825; }
        .graph-container { width: 100%; height: 500px; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
        .loading { display: none; text-align: center; padding: 20px; color: #666; }
        .loading.active { display: block; }
        .spinner { border: 3px solid #f3f3f3; border-top: 3px solid #1a73e8; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 10px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .message { padding: 10px; border-radius: 6px; margin: 10px 0; display: none; }
        .message.success { display: block; background: #e6f4ea; color: #34a853; }
        .message.error { display: block; background: #fce8e6; color: #ea4335; }
        .detail-table-wrap { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
<div class="container">
    <h1>🔗 跨库绑定 Demo</h1>

    <!-- 操作区 -->
    <div class="section">
        <h2>操作区</h2>
        <div class="btn-group">
            <button class="btn-primary" onclick="initData()">📥 初始化数据</button>
            <button class="btn-success" onclick="executeBinding('all')">🔗 执行全部绑定</button>
            <button class="btn-success" onclick="executeBinding('talent_paper')">人才↔论文</button>
            <button class="btn-success" onclick="executeBinding('talent_patent')">人才↔专利</button>
            <button class="btn-success" onclick="executeBinding('org_org')">机构↔机构</button>
            <button class="btn-danger" onclick="clearBindings(false')">🗑️ 清除绑定</button>
            <button class="btn-warning" onclick="clearBindings(true)">⚠️ 清除全部数据</button>
        </div>
        <div id="message" class="message"></div>
        <div id="loading" class="loading"><div class="spinner"></div>处理中，请稍候...</div>
    </div>

    <!-- 统计区 -->
    <div class="section">
        <h2>绑定统计</h2>
        <div class="stats-grid" id="stats-grid">
            <div class="stat-card"><h3>总绑定数</h3><div class="number" id="stat-total">-</div></div>
            <div class="stat-card confirmed"><h3>已确认</h3><div class="number" id="stat-confirmed">-</div></div>
            <div class="stat-card candidate"><h3>待确认</h3><div class="number" id="stat-candidate">-</div></div>
        </div>
    </div>

    <!-- 详情表 -->
    <div class="section">
        <h2>绑定详情</h2>
        <div style="margin-bottom:10px;">
            <select id="detail-type" onchange="loadDetail()" style="padding:6px 12px;border-radius:4px;border:1px solid #ddd;">
                <option value="talent_paper">人才↔论文</option>
                <option value="talent_patent">人才↔专利</option>
                <option value="org_org">机构↔机构</option>
            </select>
        </div>
        <div class="detail-table-wrap">
            <table>
                <thead><tr><th>源实体</th><th>目标实体</th><th>置信度</th><th>方法</th><th>规则分</th><th>LLM分</th><th>状态</th></tr></thead>
                <tbody id="detail-tbody"></tbody>
            </table>
        </div>
    </div>

    <!-- 关系图 -->
    <div class="section">
        <h2>绑定关系图</h2>
        <div class="graph-container" id="graph-container"></div>
    </div>
</div>

<script>
const API_BASE = '/api/v1/binding';
const LABEL_COLORS = {talent:'#1a73e8', cn_paper:'#34a853', patent:'#ea4335', cn_organization:'#fbbc04'};
const LABEL_NAMES = {talent:'人才', cn_paper:'论文', patent:'专利', cn_organization:'机构'};

function showMsg(text, type) {
    const el = document.getElementById('message');
    el.textContent = text; el.className = 'message ' + type;
    setTimeout(() => el.className = 'message', 5000);
}
function setLoading(on) { document.getElementById('loading').className = 'loading' + (on ? ' active' : ''); }
function disableBtns(on) { document.querySelectorAll('button').forEach(b => b.disabled = on); }

async function api(path, method='GET', body=null) {
    const opts = {method, headers:{'Content-Type':'application/json'}};
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || res.statusText); }
    return res.json();
}

async function initData() {
    setLoading(true); disableBtns(true);
    try { const r = await api('/init-data', 'POST'); showMsg('初始化完成: ' + JSON.stringify(r.nodes_inserted), 'success'); loadStats(); }
    catch(e) { showMsg('初始化失败: ' + e.message, 'error'); }
    finally { setLoading(false); disableBtns(false); }
}

async function executeBinding(type) {
    setLoading(true); disableBtns(true);
    try { const r = await api('/execute', 'POST', {binding_type: type}); showMsg('绑定完成', 'success'); loadStats(); loadDetail(); loadGraph(); }
    catch(e) { showMsg('绑定失败: ' + e.message, 'error'); }
    finally { setLoading(false); disableBtns(false); }
}

async function clearBindings(clearData) {
    setLoading(true); disableBtns(true);
    try { const r = await api('/clear?clear_data=' + clearData, 'DELETE'); showMsg(r.message, 'success'); loadStats(); loadDetail(); loadGraph(); }
    catch(e) { showMsg('清除失败: ' + e.message, 'error'); }
    finally { setLoading(false); disableBtns(false); }
}

async function loadStats() {
    try {
        const r = await api('/stats');
        const types = r.binding_types || {};
        let total=0, confirmed=0, candidate=0;
        for (const t of Object.values(types)) { total += t.total; confirmed += t.confirmed; candidate += t.candidate; }
        document.getElementById('stat-total').textContent = total;
        document.getElementById('stat-confirmed').textContent = confirmed;
        document.getElementById('stat-candidate').textContent = candidate;
    } catch(e) {}
}

async function loadDetail() {
    const type = document.getElementById('detail-type').value;
    try {
        const rows = await api('/detail?binding_type=' + type + '&limit=100');
        const tbody = document.getElementById('detail-tbody');
        tbody.innerHTML = rows.map(r => `<tr>
            <td>${r.source_id}</td><td>${r.target_id}</td>
            <td>${r.confidence.toFixed(3)}</td><td>${r.method}</td>
            <td>${r.rule_score.toFixed(3)}</td><td>${r.llm_score.toFixed(3)}</td>
            <td><span class="status-badge status-${r.status}">${r.status}</span></td>
        </tr>`).join('');
    } catch(e) { document.getElementById('detail-tbody').innerHTML = '<tr><td colspan="7">加载失败</td></tr>'; }
}

async function loadGraph() {
    try {
        const data = await api('/graph');
        renderGraph(data.nodes, data.edges);
    } catch(e) { document.getElementById('graph-container').innerHTML = '<p style="padding:20px;color:#999;">图数据加载失败</p>'; }
}

function renderGraph(nodes, edges) {
    const container = document.getElementById('graph-container');
    container.innerHTML = '';
    const width = container.clientWidth, height = container.clientHeight;
    const svg = d3.select(container).append('svg').attr('width', width).attr('height', height);

    const sim = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(edges).id(d => d.id).distance(120))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width/2, height/2));

    const link = svg.append('g').selectAll('line').data(edges).join('line')
        .attr('stroke', d => d.status === 'confirmed' ? '#34a853' : '#fbbc04')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', d => d.status === 'candidate' ? '5,5' : 'none');

    const linkLabel = svg.append('g').selectAll('text').data(edges).join('text')
        .attr('font-size', 10).attr('fill', '#666').attr('text-anchor', 'middle')
        .text(d => d.confidence ? d.confidence.toFixed(2) : '');

    const node = svg.append('g').selectAll('g').data(nodes).join('g').call(d3.drag()
        .on('start', (e,d) => { if(!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
        .on('drag', (e,d) => { d.fx=e.x; d.fy=e.y; })
        .on('end', (e,d) => { if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }));

    node.append('circle').attr('r', 18).attr('fill', d => LABEL_COLORS[d.label] || '#999');
    node.append('text').attr('dy', 4).attr('text-anchor', 'middle').attr('fill', '#fff').attr('font-size', 10).attr('font-weight', 'bold')
        .text(d => (LABEL_NAMES[d.label] || d.label).charAt(0));
    node.append('title').text(d => `${LABEL_NAMES[d.label] || d.label}: ${d.name}`);

    sim.on('tick', () => {
        link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
        linkLabel.attr('x', d => (d.source.x + d.target.x) / 2).attr('y', d => (d.source.y + d.target.y) / 2 - 5);
        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
}

// Initial load
loadStats(); loadDetail(); loadGraph();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify static file mount**

Run: `cd /data1/huyatao/tech-kg-api && python -c "import os; print(os.path.exists('app/static/binding.html'))"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add app/static/binding.html
git commit -m "feat: add binding demo frontend page with D3.js visualization"
```

---

### Task 6: 端到端测试

**Files:**
- Create: `tests/test_entity_binding.py`

- [ ] **Step 1: Write integration test for binding API**

Create `tests/test_entity_binding.py`:

```python
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
        assert "binding_types" in data

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
```

- [ ] **Step 2: Run the full test suite**

Start `trs-graph-service` first if not running:
```bash
cd /data1/huyatao/trs-graph-service && bash start.sh status
```

Then run:
```bash
cd /data1/huyatao/tech-kg-api && python -m pytest tests/test_binding_matcher.py tests/test_trs_graph_backend.py -v
```

For integration tests (requires trs-graph-service):
```bash
cd /data1/huyatao/tech-kg-api && python -m pytest tests/test_entity_binding.py -v --tb=short
```

Expected: All PASS

- [ ] **Step 3: Start the API server and test in browser**

```bash
cd /data1/huyatao/tech-kg-api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open browser to `http://localhost:8000/binding` and test:
1. Click "初始化数据" → should see node counts
2. Click "执行全部绑定" → should see stats update
3. Check detail table and graph

- [ ] **Step 4: Commit**

```bash
git add tests/test_entity_binding.py
git commit -m "test: add integration tests for entity binding API"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ TRS Graph backend (Section 1) → Task 1
- ✅ Binding edges definition (Section 2.1) → Task 1 (EDGE_NGQLS in entity_binding.py)
- ✅ Binding pipeline (Section 2.2) → Task 3
- ✅ Rule matching (Section 2.3) → Task 2
- ✅ LLM refinement (Section 2.4) → Task 3
- ✅ Service structure (Section 2.5) → Task 3
- ✅ API routes (Section 3.1) → Task 4
- ✅ Frontend (Section 3.2) → Task 5
- ✅ Test data (Section 4.1) → Task 3 (data constants)
- ✅ Indexes (Section 4.3) → Task 3 (INDEX_NGQLS)
- ✅ Edge types (Section 4.4) → Task 3 (EDGE_NGQLS)
- ✅ Init flow (Section 4.5) → Task 3 (init_data method)

**2. Placeholder scan:** No TBD/TODO/fill-in-later found ✅

**3. Type consistency:**
- `BindingMatcher.match_talent_paper` returns `list[dict]` → consumed by `EntityBindingService.bind_talent_paper` ✅
- `BindingPairDetail` fields match what `EntityBindingService` populates ✅
- `GraphDBConfig` fields used in `_get_service()` match config.py ✅
- TRS Graph backend method signatures match `GraphDatabase` ABC ✅
