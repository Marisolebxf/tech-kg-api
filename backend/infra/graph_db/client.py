"""TRSGraphClient — internal ORM-style repository over trs-graph-service.

Wraps the trs-graph-service REST API (NebulaGraph) for in-app use.
Logic ported from graph_db/backends/trs_graph_backend.py on the
refactor/trs-graph-db-api branch.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
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

SCHEMA_INDEXES_PATH = "/api/v1/schema/indexes"

logger = logging.getLogger("infra.graph_db")

# nGQL 直查只接受白名单标签名（SHOW TAGS 出来的标识符），防注入
_TAG_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,128}$")
# SHOW STATS 快照缓存：{space: (monotonic 时间, {"tags", "edges", "total_nodes", "total_edges"})}
_stats_snapshot_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_STATS_CACHE_TTL_SECONDS = 300.0

# The trs-graph-service only treats these property keys as the Nebula vertex id
# (see NodeService.extractVid / NgqlBuilder.extractOrGenerateVid). When none of
# them is present the service generates a UUID vid internally but then *cannot
# read the node back* (it looks up vid/id/name and finds nothing → 404). So the
# client must guarantee one of these keys is set before calling the service.
_VID_KEYS: tuple[str, ...] = ("vid", "id", "name")


def _vid_has_slash(node_id: Any) -> bool:
    """DOI 类业务 VID 本身含 ``/``（如 paper_ref_10.1111/jth.14768）。

    trs-graph REST 的 ``/nodes/{id}``、``/traversal/{id}/edges`` 是单段路径
    参数，斜杠 VID（无论是否 %2F 编码）都路由不匹配，需改走 nGQL 查询端点。
    """
    return "/" in str(node_id)


def _ngql_quote(value: Any) -> str:
    """值转为 nGQL 双引号字符串字面量（转义反斜杠与双引号，防注入）。"""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _error_detail(resp: httpx.Response) -> str:
    """从 trs-graph 错误响应体里提取人类可读信息（如 Nebula SemanticError）。"""
    try:
        data = resp.json()
    except ValueError:
        return ""
    if isinstance(data, dict):
        message = data.get("message") or data.get("error")
        if message:
            return f": {message}"
    return ""


def _ensure_vid(props: dict[str, Any]) -> dict[str, Any]:
    """Return props with a vid guaranteed.

    If a vid/id/name key is already present, props is returned unchanged. If
    props is non-empty but has no vid-key, the *first* property's value is
    promoted to the vid (this matches the techkg convention where the natural
    key — e.g. org_id / scholar_id — is also the vertex id). If props is empty,
    a random uuid is generated.
    """
    if any(k in props for k in _VID_KEYS):
        return props
    if props:
        first_value = next(iter(props.values()))
        props["vid"] = str(first_value)
    else:
        props["vid"] = uuid.uuid4().hex
    return props


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
                f"{method} {path} -> {resp.status_code}{_error_detail(resp)}",
                status_code=resp.status_code,
                body=resp.text,
            )
        return resp

    # ==================================================================
    # Node CRUD
    # ==================================================================

    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> GraphNode:
        properties = _ensure_vid(dict(properties) if properties else {})
        body = _build_node_create_body(labels, properties)
        resp = self._request("POST", "/api/v1/nodes", json=body)
        return _trs_node_to_model(resp.json())

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        identity_props = _ensure_vid(dict(identity_props) if identity_props else {})
        body = {
            "labels": labels if labels else ["Vertex"],
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/nodes/merge", json=body)
        return _trs_node_to_model(resp.json())

    def get_node(self, node_id: Any) -> GraphNode | None:
        if _vid_has_slash(node_id):
            return self._get_node_via_ngql(node_id)
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
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
        )

    def paged_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> list[GraphNode]:
        """按标签分页取节点：LOOKUP 索引枚举优先，无标签索引回退 MATCH 全扫。

        MATCH (v:`Label`) SKIP/LIMIT 即便标签有索引也不走（实测 dev2 DataSource
        39 行 2.7s，高负载 30s 超时拖垮实体列表），LOOKUP 走标签索引 0.07s；
        无索引标签 LOOKUP 立即 400 "There is no index to use"（快速失败不扫描），
        回退 MATCH 慢但正确——补建标签索引后自动切回快路径。
        REST /api/v1/nodes/label/{label} 在 trs-graph 侧附带全量总数计算，
        大标签（如 Paper 十万级）30s+ 超时（2026-09-21 实测 limit=2 也挂）；
        总数需求另走 label_count()，不要为此恢复 REST 分页端点。
        """
        if not _TAG_IDENTIFIER.fullmatch(label or ""):
            raise GraphRequestError(f"非法节点标签: {label!r}", status_code=400)
        try:
            result = self.execute_read(
                f"LOOKUP ON `{label}` YIELD vertex AS v | LIMIT {int(limit)} OFFSET {int(offset)}"
            )
        except GraphRequestError as exc:
            logger.warning("LOOKUP 分页无索引（label=%s），回退 MATCH 全扫: %s", label, exc)
            result = self.execute_read(
                f"MATCH (v:`{label}`) RETURN v SKIP {int(offset)} LIMIT {int(limit)}"
            )
        nodes: list[GraphNode] = []
        for record in result.records or []:
            data = record.get("v") if isinstance(record, dict) else None
            if not isinstance(data, dict):
                continue
            nodes.append(
                GraphNode(
                    id=data.get("id"),
                    labels=list(data.get("labels") or []),
                    properties=dict(data.get("properties") or {}),
                )
            )
        return nodes

    def label_count(self, label: str) -> int:
        """标签节点数：优先 SHOW STATS（毫秒级）；标签不在统计中，或空间从未
        跑过 SUBMIT JOB STATS（SHOW STATS 直接 400 "no any stats info"）时回退
        nGQL 标签 count 直查（走标签索引，亚秒级）。不用 REST /schema/stats/
        node-count 兜底——其在 trs-graph 侧全表扫描，11 顶点空间实测 31s+，
        大标签必超时。"""
        try:
            counts = self.stats_tag_counts()
        except (GraphRequestError, GraphConnectionError) as exc:
            logger.warning(
                "SHOW STATS 不可用（space=%s label=%s），回退 nGQL 标签计数: %s",
                self._settings.space,
                label,
                exc,
            )
            counts = {}
        if label in counts:
            return counts[label]
        return self._ngql_label_count(label)

    def _ngql_label_count(self, label: str) -> int:
        """nGQL 标签计数：``MATCH (v:`Label`) RETURN count(v)``（标签过滤亚秒级）。"""
        if not _TAG_IDENTIFIER.fullmatch(label or ""):
            raise GraphRequestError(f"非法节点标签: {label!r}", status_code=400)
        result = self.execute_read(f"MATCH (v:`{label}`) RETURN count(v) AS c")
        for record in result.records or []:
            if isinstance(record, dict) and record.get("c") is not None:
                return int(record["c"])
        return 0

    def stats_snapshot(self) -> dict[str, Any]:
        """SHOW STATS 解析快照 {"tags", "edges", "total_nodes", "total_edges"}，按空间缓存 300s。

        Nebula 统计只在 SUBMIT JOB STATS 后刷新，本就允许轻微滞后，用它换掉
        逐标签/边类型全表 count（Paper 实测 45s+ 超时）。缓存模块级共享：
        即使 SHOW STATS 此刻报错（如 stats 任务卡死），300s 内成功过的快照
        仍可读——平台总览等消费方的回退路径据此兜底。
        """
        cached = _stats_snapshot_cache.get(self._settings.space)
        if cached and time.monotonic() - cached[0] < _STATS_CACHE_TTL_SECONDS:
            return cached[1]
        result = self.execute_read("SHOW STATS;")
        tags: dict[str, int] = {}
        edges: dict[str, int] = {}
        vertices = 0
        edge_total = 0
        for record in result.records or []:
            if not isinstance(record, dict):
                continue
            rtype = record.get("Type")
            name = record.get("Name")
            count = int(record.get("Count") or 0)
            if rtype == "Tag" and name:
                tags[str(name)] = count
            elif rtype == "Edge" and name:
                edges[str(name)] = count
            elif rtype == "Space":
                if name == "vertices":
                    vertices = count
                elif name == "edges":
                    edge_total = count
        snapshot = {
            "tags": tags,
            "edges": edges,
            "total_nodes": vertices or sum(tags.values()),
            "total_edges": edge_total or sum(edges.values()),
        }
        _stats_snapshot_cache[self._settings.space] = (time.monotonic(), snapshot)
        return snapshot

    def stats_tag_counts(self) -> dict[str, int]:
        """SHOW STATS 的全标签计数（stats_snapshot 的 tags 部分，副本）。"""
        return dict(self.stats_snapshot()["tags"])

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
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
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
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
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
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
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
        offset: int = 0,
    ) -> list[GraphEdge]:
        if _vid_has_slash(node_id):
            return self._get_node_edges_via_ngql(
                node_id, direction=direction, edge_type=edge_type, limit=limit, offset=offset
            )
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if offset:
            params["offset"] = offset
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/edges", params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [_trs_edge_to_model(e) for e in items]

    def _get_node_via_ngql(self, node_id: Any) -> GraphNode | None:
        """含 ``/`` 的 VID（DOI 类）经 nGQL FETCH 取节点。

        trs-graph REST 的 ``/nodes/{id}`` 是单段路径参数，斜杠 VID 直接
        路由 404，必须走查询端点。
        """
        result = self.execute_query(f"FETCH PROP ON * {_ngql_quote(node_id)} YIELD vertex AS v")
        for record in result.records:
            vertex = record.get("v")
            if isinstance(vertex, dict) and vertex.get("id") is not None:
                return _trs_node_to_model(vertex)
        return None

    def _get_node_edges_via_ngql(
        self,
        node_id: Any,
        *,
        direction: str,
        edge_type: str | None,
        limit: int,
        offset: int,
    ) -> list[GraphEdge]:
        """含 ``/`` 的 VID（DOI 类）经 nGQL GO 取一跳边（REST 路径参数无法承载）。

        边不带属性（子图渲染只用类型与端点）；GO 不做服务端分页，Python 侧切片。
        edge_type 只放行字母数字下划线，防 nGQL 注入。
        """
        over = "*"
        if edge_type and edge_type.replace("_", "a").isalnum():
            over = edge_type
        direction_clause = {"in": "REVERSELY", "both": "BIDIRECT"}.get(direction, "")
        statement = (
            f"GO 1 STEP FROM {_ngql_quote(node_id)} OVER {over}"
            + (f" {direction_clause}" if direction_clause else "")
            + " YIELD id($^) AS src, id($$) AS dst, type(edge) AS etype"
        )
        result = self.execute_query(statement)
        edges = [
            GraphEdge(
                id=f"{record.get('src')}|{record.get('etype')}|{record.get('dst')}",
                type=str(record.get("etype")),
                source_id=record.get("src"),
                target_id=record.get("dst"),
            )
            for record in result.records
        ]
        return edges[offset : offset + limit]

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
            params["edgeType"] = edge_type
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

    def _scoped_query(self, query: str) -> str:
        if query.lstrip().upper().startswith("USE "):
            return query
        space = self._settings.space
        if not re.fullmatch(r"[A-Za-z_]\w*", space, flags=re.ASCII):
            raise GraphRequestError(
                "Invalid graph space name",
                status_code=400,
                body=space,
            )
        return f"USE {space}; {query}"

    @staticmethod
    def _query_result(data: dict[str, Any], path: str, *, expected_space: str) -> GraphQueryResult:
        summary = data.get("summary")
        if isinstance(summary, dict) and summary.get("errorCode") not in (None, 0, "0"):
            comment = summary.get("comment") or summary
            raise GraphRequestError(
                f"TRS Graph query failed on {path}: {comment}",
                status_code=200,
                body=json.dumps(data, ensure_ascii=False),
            )
        actual_space = summary.get("spaceName") if isinstance(summary, dict) else None
        if actual_space and actual_space != expected_space:
            raise GraphRequestError(
                f"TRS Graph space mismatch on {path}: expected {expected_space}, got {actual_space}",
                status_code=409,
                body=json.dumps(data, ensure_ascii=False),
            )
        return GraphQueryResult(records=data.get("records", []), summary=summary)

    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": self._scoped_query(query)}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query", json=body)
        data = resp.json()
        return self._query_result(data, "/api/v1/query", expected_space=self._settings.space)

    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": self._scoped_query(query)}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/read", json=body)
        data = resp.json()
        return self._query_result(data, "/api/v1/query/read", expected_space=self._settings.space)

    def execute_write(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": self._scoped_query(query)}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/write", json=body)
        data = resp.json()
        return self._query_result(data, "/api/v1/query/write", expected_space=self._settings.space)

    # ==================================================================
    # Batch operations
    # ==================================================================

    def batch_create_nodes(
        self,
        items: Sequence[dict[str, Any]],
        labels: list[str],
    ) -> list[GraphNode]:
        norm_items = []
        for item in items:
            norm_items.append(_ensure_vid(dict(item)))
        body = {"labels": labels if labels else ["Vertex"], "items": norm_items}
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
        self._request("POST", SCHEMA_INDEXES_PATH, json=body)

    def drop_index(self, label: str, properties: list[str]) -> None:
        params = {"label": label, "properties": ",".join(properties)}
        self._request("DELETE", SCHEMA_INDEXES_PATH, params=params)

    def list_indexes(self, label: str | None = None) -> list[GraphIndexSpec]:
        params: dict[str, Any] = {}
        if label:
            params["label"] = label
        resp = self._request("GET", SCHEMA_INDEXES_PATH, params=params)
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
                    except ValueError as exc:
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
            params["edgeType"] = edge_type
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

    def list_spaces(self) -> list[str]:
        """列出所有图空间（无 REST 端点，用 nGQL SHOW SPACES）。"""
        result = self.execute_write("SHOW SPACES;")
        names: list[str] = []
        for rec in result.records:
            name = rec.get("Name", rec.get("name", ""))
            if name:
                names.append(str(name))
        return names
