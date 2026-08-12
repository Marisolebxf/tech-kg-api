"""图谱搜索 API：支撑前端图谱查询展示，返回 JSON 格式的点边数据。

所有端点支持 ``space`` 参数指定图空间（如 dev/techkg），缺省用 .env 的 TRS_GRAPH_SPACE。
handler 层只调 TRSGraphClient 方法，不直接写 nGQL。
"""

from __future__ import annotations

import threading
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from biz.schemas.common import ApiResponse
from infra.graph_db import TRSGraphClient, get_trs_graph_client
from infra.graph_db.config import TRSGraphSettings

router = APIRouter(prefix="/graph-search", tags=["graph-search"])

# 按空间缓存客户端（避免每次请求重建连接）
_space_clients: dict[str, TRSGraphClient] = {}
_space_lock = threading.Lock()


# ---------- 响应模型 ----------


class GraphNodeData(BaseModel):
    id: str
    labels: list[str] = []
    properties: dict[str, Any] = {}


class GraphEdgeData(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any] = {}


class SubgraphData(BaseModel):
    nodes: list[GraphNodeData]
    edges: list[GraphEdgeData]


class NodeDetailData(BaseModel):
    id: str
    labels: list[str] = []
    properties: dict[str, Any] = {}


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


# ---------- 辅助函数 ----------


def _get_client(space: str | None = None) -> TRSGraphClient:
    """获取指定空间的 trs-graph 客户端。

    space=None 时用 get_trs_graph_client() 单例（.env 的 TRS_GRAPH_SPACE）。
    指定 space 时按空间名缓存客户端。
    """
    if not space:
        return get_trs_graph_client()

    if space in _space_clients:
        return _space_clients[space]

    with _space_lock:
        if space in _space_clients:
            return _space_clients[space]
        settings = TRSGraphSettings.from_env()
        settings.space = space
        client = TRSGraphClient(settings)
        client.connect()
        _space_clients[space] = client
        return client


def _node_to_data(n: Any) -> GraphNodeData:
    """将 GraphNode / dict 转为前端 JSON 格式。"""
    if isinstance(n, dict):
        return GraphNodeData(
            id=str(n.get("id", "")),
            labels=n.get("labels", []),
            properties=n.get("properties", {}),
        )
    return GraphNodeData(
        id=str(n.id),
        labels=n.labels,
        properties=n.properties,
    )


def _edge_to_data(e: Any) -> GraphEdgeData:
    """将 GraphEdge / dict 转为前端 JSON 格式。"""
    if isinstance(e, dict):
        return GraphEdgeData(
            id=str(e.get("id", "")),
            type=e.get("type", ""),
            source=str(e.get("sourceId", "")),
            target=str(e.get("targetId", "")),
            properties=e.get("properties", {}),
        )
    return GraphEdgeData(
        id=str(e.id),
        type=e.type,
        source=str(e.source_id),
        target=str(e.target_id),
        properties=e.properties,
    )


# ---------- API 端点 ----------


@router.get("/nodes/{node_id}", response_model=ApiResponse)
async def get_node(
    node_id: str,
    space: str | None = Query(None, description="图空间，如 dev/techkg，缺省用默认空间"),
) -> ApiResponse:
    """按 VID 查单个节点详情。"""
    try:
        node = _get_client(space).get_node(node_id)
        if node is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {node_id}")
        return ApiResponse(data=_node_to_data(node).model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/nodes", response_model=ApiResponse)
async def list_nodes(
    label: str = Query(..., description="节点标签，如 Paper/Person/Journal/Report"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """按标签分页查询节点列表（total 为库里真实总数）。"""
    try:
        client = _get_client(space)
        result = client.get_nodes_by_label(label, limit=limit, offset=offset)
        items = [_node_to_data(n).model_dump() for n in result.items]
        total = client.node_count(label)
        return ApiResponse(data=NodeListData(items=items, total=total).model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.post("/nodes/search", response_model=ApiResponse)
async def search_nodes(
    label: str = Query(..., description="节点标签"),
    properties: dict[str, Any] | None = None,
    limit: int = Query(20, ge=1, le=500),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """按属性搜索节点（如 {"doi": "10.xxx"} 查论文）。"""
    try:
        result = _get_client(space).find_nodes([label], properties or {}, limit=limit)
        items = [_node_to_data(n).model_dump() for n in result.items]
        return ApiResponse(data=NodeListData(items=items, total=len(items)).model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/subgraph/{node_id}", response_model=ApiResponse)
async def get_subgraph(
    node_id: str,
    depth: int = Query(1, ge=1, le=3, description="跳数 1-3"),
    limit: int = Query(50, ge=1, le=200, description="每页最大边数"),
    offset: int = Query(0, ge=0, description="一跳遍历分页偏移量"),
    edge_type: str | None = Query(None, description="边类型过滤，如 AUTHORED_BY"),
    direction: Literal["out", "in", "both"] = Query("both", description="方向: out/in/both"),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的 N 跳子图（点 + 边），前端直接渲染图谱。"""
    try:
        client = _get_client(space)

        # 中心节点
        center = client.get_node(node_id)
        if center is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {node_id}")

        nodes: list[GraphNodeData] = [_node_to_data(center)]
        edges: list[GraphEdgeData] = []
        seen_edge_ids: set[str] = set()
        seen_vids = {str(center.id)}

        # 逐跳扩展
        frontier = [node_id]
        for _hop in range(depth):
            next_frontier: list[str] = []
            for vid in frontier:
                edge_list = client.get_node_edges(
                    vid, direction=direction, edge_type=edge_type, limit=limit, offset=offset
                )
                for e in edge_list:
                    edge_data = _edge_to_data(e)

                    edge_key = (
                        edge_data.id or f"{edge_data.source}|{edge_data.type}|{edge_data.target}"
                    )

                    if edge_key not in seen_edge_ids:
                        seen_edge_ids.add(edge_key)
                        edges.append(edge_data)
                    neighbor_id = str(e.target_id if str(e.source_id) == vid else e.source_id)
                    if neighbor_id not in seen_vids:
                        neighbor = client.get_node(neighbor_id)
                        if neighbor:
                            n_data = _node_to_data(neighbor)
                            nodes.append(n_data)
                            seen_vids.add(n_data.id)
                            next_frontier.append(n_data.id)
            frontier = next_frontier

        # 边按页限制；节点需包含中心点和本页所有边端点。
        if len(edges) > limit:
            edges = edges[:limit]

        return ApiResponse(data=SubgraphData(nodes=nodes, edges=edges).model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/node/{node_id}/edges", response_model=ApiResponse)
async def get_node_edges(
    node_id: str,
    direction: Literal["out", "in", "both"] = Query("both", description="out/in/both"),
    edge_type: str | None = Query(None, description="边类型过滤"),
    limit: int = Query(50, ge=1, le=200),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的所有边（不含邻居节点属性，轻量）。"""
    try:
        edge_list = _get_client(space).get_node_edges(
            node_id, direction=direction, edge_type=edge_type, limit=limit
        )
        edges = [_edge_to_data(e).model_dump() for e in edge_list]
        return ApiResponse(data={"edges": edges, "total": len(edges)})
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/node/{node_id}/neighbours", response_model=ApiResponse)
async def get_neighbours(
    node_id: str,
    direction: Literal["out", "in", "both"] = Query("both", description="out/in/both"),
    edge_type: str | None = Query(None, description="边类型过滤"),
    limit: int = Query(50, ge=1, le=200),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的邻居节点（含属性）。"""
    try:
        neighbours = _get_client(space).get_neighbours(
            node_id, direction=direction, edge_type=edge_type, limit=limit
        )
        nodes = [_node_to_data(n).model_dump() for n in neighbours]
        return ApiResponse(data={"nodes": nodes, "total": len(nodes)})
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/shortest-path", response_model=ApiResponse)
async def shortest_path(
    source: str = Query(..., description="起始节点 VID"),
    target: str = Query(..., description="目标节点 VID"),
    max_depth: int = Query(10, ge=1, le=20, description="最大搜索深度"),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查两个节点之间的最短路径。"""
    try:
        path = _get_client(space).shortest_path(source, target, max_depth=max_depth)
        if path is None:
            return ApiResponse(data=PathData(nodes=[], edges=[], found=False).model_dump())
        nodes = [_node_to_data(n).model_dump() for n in path.nodes]
        edges = [_edge_to_data(e).model_dump() for e in path.edges]
        return ApiResponse(data=PathData(nodes=nodes, edges=edges, found=True).model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/spaces", response_model=ApiResponse)
async def list_spaces() -> ApiResponse:
    """列出所有可用的图空间。"""
    try:
        names = _get_client(None).list_spaces()
        return ApiResponse(data={"spaces": names})
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/stats", response_model=ApiResponse)
async def get_stats(
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """图统计：各标签节点数 + 各边类型边数（前端仪表盘用）。"""
    try:
        client = _get_client(space)
        tag_names = client.labels()
        edge_names = client.edge_types()

        node_counts: dict[str, int] = {}
        for tag in tag_names:
            node_counts[tag] = client.node_count(tag)

        edge_counts: dict[str, int] = {}
        for etype in edge_names:
            edge_counts[etype] = client.edge_count(etype)

        return ApiResponse(data=StatsData(nodes=node_counts, edges=edge_counts).model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))
