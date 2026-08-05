"""Read-only graph search endpoints for the frontend graph explorer."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from biz.schemas.common import ApiResponse
from infra.graph_db import get_graph_client
from infra.graph_db.exceptions import GraphRequestError

router = APIRouter(prefix="/graph-search", tags=["graph-search"])


class GraphNodeData(BaseModel):
    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeData(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class SubgraphData(BaseModel):
    nodes: list[GraphNodeData]
    edges: list[GraphEdgeData]


class NodeDetailData(BaseModel):
    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class NodeListData(BaseModel):
    items: list[NodeDetailData]
    total: int


class PathData(BaseModel):
    nodes: list[GraphNodeData]
    edges: list[GraphEdgeData]
    found: bool


class StatsData(BaseModel):
    nodes: dict[str, int]
    edges: dict[str, int]


def _node_to_data(node: Any) -> GraphNodeData:
    if isinstance(node, dict):
        return GraphNodeData(
            id=str(node.get("id", "")),
            labels=node.get("labels", []),
            properties=node.get("properties", {}),
        )
    return GraphNodeData(id=str(node.id), labels=node.labels, properties=node.properties)


def _edge_to_data(edge: Any) -> GraphEdgeData:
    if isinstance(edge, dict):
        return GraphEdgeData(
            id=str(edge.get("id", "")),
            type=edge.get("type", ""),
            source=str(edge.get("sourceId", "")),
            target=str(edge.get("targetId", "")),
            properties=edge.get("properties", {}),
        )
    return GraphEdgeData(
        id=str(edge.id),
        type=edge.type,
        source=str(edge.source_id),
        target=str(edge.target_id),
        properties=edge.properties,
    )


@router.get("/nodes/{node_id}", response_model=ApiResponse)
def get_node(
    node_id: str,
    space: str | None = Query(None, description="图空间，缺省使用 TRS_GRAPH_SPACE"),
) -> ApiResponse:
    node = get_graph_client(space).get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")
    return ApiResponse(data=_node_to_data(node).model_dump())


@router.get("/nodes", response_model=ApiResponse)
def list_nodes(
    label: str = Query(..., description="节点标签"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    client = get_graph_client(space)
    try:
        result = client.get_nodes_by_label(label, limit=limit, offset=offset)
        items = [_node_to_data(node).model_dump() for node in result.items]
        total = client.node_count(label)
    except GraphRequestError as exc:
        # An empty or partially initialized graph space can legitimately lack
        # one of the explorer's optional labels. Treat that case as an empty
        # collection so the homepage remains usable while schema/data are
        # being initialized. Other upstream failures must still surface.
        if exc.status_code != 400 or "Unknown tag" not in exc.body:
            raise
        items = []
        total = 0
    return ApiResponse(data=NodeListData(items=items, total=total).model_dump())


@router.post("/nodes/search", response_model=ApiResponse)
def search_nodes(
    label: str = Query(..., description="节点标签"),
    properties: dict[str, Any] | None = None,
    limit: int = Query(20, ge=1, le=500),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    result = get_graph_client(space).find_nodes([label], properties or {}, limit=limit)
    items = [_node_to_data(node).model_dump() for node in result.items]
    return ApiResponse(data=NodeListData(items=items, total=len(items)).model_dump())


@router.get("/subgraph/{node_id}", response_model=ApiResponse)
def get_subgraph(
    node_id: str,
    depth: int = Query(1, ge=1, le=3, description="跳数 1-3"),
    limit: int = Query(50, ge=1, le=200, description="最大返回点边数"),
    edge_type: str | None = Query(None, description="边类型过滤"),
    direction: Literal["out", "in", "both"] = Query("both"),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    client = get_graph_client(space)
    center = client.get_node(node_id)
    if center is None:
        raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")

    nodes = [_node_to_data(center)]
    edges: list[GraphEdgeData] = []
    seen_edge_ids: set[str] = set()
    seen_vids = {str(center.id)}
    frontier = [node_id]

    for _ in range(depth):
        next_frontier: list[str] = []
        for vid in frontier:
            for edge in client.get_node_edges(
                vid, direction=direction, edge_type=edge_type, limit=limit
            ):
                edge_data = _edge_to_data(edge)
                edge_key = edge_data.id or f"{edge_data.source}|{edge_data.type}|{edge_data.target}"
                if edge_key not in seen_edge_ids:
                    seen_edge_ids.add(edge_key)
                    edges.append(edge_data)
                neighbor_id = edge_data.target if edge_data.source == vid else edge_data.source
                if neighbor_id in seen_vids:
                    continue
                neighbor = client.get_node(neighbor_id)
                if neighbor is not None:
                    node_data = _node_to_data(neighbor)
                    nodes.append(node_data)
                    seen_vids.add(node_data.id)
                    next_frontier.append(node_data.id)
        frontier = next_frontier

    nodes = nodes[:limit]
    returned_ids = {node.id for node in nodes}
    edges = [edge for edge in edges if edge.source in returned_ids and edge.target in returned_ids][
        :limit
    ]
    return ApiResponse(data=SubgraphData(nodes=nodes, edges=edges).model_dump())


@router.get("/node/{node_id}/edges", response_model=ApiResponse)
def get_node_edges(
    node_id: str,
    direction: Literal["out", "in", "both"] = Query("both"),
    edge_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    space: str | None = Query(None),
) -> ApiResponse:
    edge_list = get_graph_client(space).get_node_edges(
        node_id, direction=direction, edge_type=edge_type, limit=limit
    )
    edges = [_edge_to_data(edge).model_dump() for edge in edge_list]
    return ApiResponse(data={"edges": edges, "total": len(edges)})


@router.get("/node/{node_id}/neighbours", response_model=ApiResponse)
def get_neighbours(
    node_id: str,
    direction: Literal["out", "in", "both"] = Query("both"),
    edge_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    space: str | None = Query(None),
) -> ApiResponse:
    neighbours = get_graph_client(space).get_neighbours(
        node_id, direction=direction, edge_type=edge_type, limit=limit
    )
    nodes = [_node_to_data(node).model_dump() for node in neighbours]
    return ApiResponse(data={"nodes": nodes, "total": len(nodes)})


@router.get("/shortest-path", response_model=ApiResponse)
def shortest_path(
    source: str = Query(..., description="起始节点 VID"),
    target: str = Query(..., description="目标节点 VID"),
    max_depth: int = Query(10, ge=1, le=20),
    space: str | None = Query(None),
) -> ApiResponse:
    path = get_graph_client(space).shortest_path(source, target, max_depth=max_depth)
    if path is None:
        return ApiResponse(data=PathData(nodes=[], edges=[], found=False).model_dump())
    nodes = [_node_to_data(node).model_dump() for node in path.nodes]
    edges = [_edge_to_data(edge).model_dump() for edge in path.edges]
    return ApiResponse(data=PathData(nodes=nodes, edges=edges, found=True).model_dump())


@router.get("/spaces", response_model=ApiResponse)
def list_spaces() -> ApiResponse:
    return ApiResponse(data={"spaces": get_graph_client().list_spaces()})


@router.get("/stats", response_model=ApiResponse)
def get_stats(space: str | None = Query(None)) -> ApiResponse:
    client = get_graph_client(space)
    node_counts = {label: client.node_count(label) for label in client.labels()}
    edge_counts = {edge_type: client.edge_count(edge_type) for edge_type in client.edge_types()}
    return ApiResponse(data=StatsData(nodes=node_counts, edges=edge_counts).model_dump())
