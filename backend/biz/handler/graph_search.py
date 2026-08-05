"""图谱搜索 API：支撑前端图谱查询展示，返回 JSON 格式的点边数据。

所有端点支持 ``space`` 参数指定图空间（如 dev/techkg），缺省用 .env 的 TRS_GRAPH_SPACE。
常规端点只调用 TRSGraphClient 的封装方法；受控路径查询把经过 Pydantic 白名单校验的
逐跳约束编译为只读 nGQL，不接受调用方传入任意查询语句。
"""

from __future__ import annotations

import json
import threading
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

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


GraphDirection = Literal["out", "in"]
FilterOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte"]
GRAPH_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"


class PathPropertyFilter(BaseModel):
    """路径节点属性过滤；字段名和操作符均由服务端校验。"""

    property: str = Field(..., pattern=GRAPH_IDENTIFIER_PATTERN)
    operator: FilterOperator = "eq"
    value: str | int | float | bool


class TypedPathStep(BaseModel):
    """一跳路径约束。direction 以当前节点为参照。"""

    edgeType: str = Field(..., pattern=GRAPH_IDENTIFIER_PATTERN)
    direction: GraphDirection
    targetLabel: str = Field(..., pattern=GRAPH_IDENTIFIER_PATTERN)
    targetFilters: list[PathPropertyFilter] = Field(default_factory=list, max_length=10)


class TypedPathSearchRequest(BaseModel):
    """受控的多跳路径查询请求，避免向调用方开放任意 nGQL。"""

    sourceId: str = Field(..., min_length=1, max_length=256)
    targetId: str | None = Field(default=None, min_length=1, max_length=256)
    steps: list[TypedPathStep] = Field(..., min_length=1, max_length=4)
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    space: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=GRAPH_IDENTIFIER_PATTERN,
    )


class TypedPathListData(BaseModel):
    items: list[PathData]
    total: int
    limit: int
    offset: int


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


def _ngql_literal(value: Any) -> str:
    """将已通过 Pydantic 校验的标量安全转换为 nGQL 字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", " ").replace("\r", " ")
    return f'"{escaped}"'


def _as_properties(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _build_typed_path_query(body: TypedPathSearchRequest, *, count_only: bool = False) -> str:
    """把受控路径模型编译为只读 MATCH 查询。"""
    pattern = "(n0)"
    conditions = [f"id(n0) == {_ngql_literal(body.sourceId)}"]

    for index, step in enumerate(body.steps):
        edge = f"[e{index}:`{step.edgeType}`]"
        target = f"(n{index + 1}:`{step.targetLabel}`)"
        if step.direction == "out":
            pattern += f"-{edge}->{target}"
        else:
            pattern += f"<-{edge}-{target}"

        for item in step.targetFilters:
            operator = {
                "eq": "==",
                "ne": "!=",
                "gt": ">",
                "gte": ">=",
                "lt": "<",
                "lte": "<=",
            }[item.operator]
            conditions.append(
                f"n{index + 1}.`{step.targetLabel}`.`{item.property}` "
                f"{operator} {_ngql_literal(item.value)}"
            )

    last_index = len(body.steps)
    if body.targetId is not None:
        conditions.append(f"id(n{last_index}) == {_ngql_literal(body.targetId)}")

    where = " AND ".join(conditions)
    if count_only:
        return f"MATCH {pattern} WHERE {where} RETURN count(*) AS total"

    projections: list[str] = []
    for index in range(last_index + 1):
        projections.extend(
            [
                f"id(n{index}) AS node_{index}_id",
                f"properties(n{index}) AS node_{index}_properties",
            ]
        )
    for index in range(last_index):
        projections.extend(
            [
                f"properties(e{index}) AS edge_{index}_properties",
                f"rank(e{index}) AS edge_{index}_rank",
            ]
        )
    return (
        f"MATCH {pattern} WHERE {where} RETURN {', '.join(projections)} "
        f"SKIP {body.offset} LIMIT {body.limit}"
    )


def _typed_path_from_record(
    body: TypedPathSearchRequest,
    record: dict[str, Any],
    source_labels: list[str],
) -> PathData:
    nodes: list[GraphNodeData] = []
    edges: list[GraphEdgeData] = []

    for index in range(len(body.steps) + 1):
        raw_id = record.get(f"node_{index}_id", "")
        node_id = str(raw_id).strip('"')
        labels = source_labels if index == 0 else [body.steps[index - 1].targetLabel]
        nodes.append(
            GraphNodeData(
                id=node_id,
                labels=labels,
                properties=_as_properties(record.get(f"node_{index}_properties")),
            )
        )

    for index, step in enumerate(body.steps):
        current_id = nodes[index].id
        next_id = nodes[index + 1].id
        if step.direction == "out":
            source_id, target_id = current_id, next_id
        else:
            source_id, target_id = next_id, current_id
        ranking = int(record.get(f"edge_{index}_rank") or 0)
        edges.append(
            GraphEdgeData(
                id=f"{source_id}->{target_id}@{ranking}",
                type=step.edgeType,
                source=source_id,
                target=target_id,
                properties=_as_properties(record.get(f"edge_{index}_properties")),
            )
        )

    return PathData(nodes=nodes, edges=edges, found=True)


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


@router.post("/paths/search", response_model=ApiResponse)
async def search_typed_paths(body: TypedPathSearchRequest) -> ApiResponse:
    """按逐跳边类型和方向查询全部匹配路径，支持中间节点属性过滤与分页。"""
    try:
        client = _get_client(body.space)
        source = client.get_node(body.sourceId)
        if source is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {body.sourceId}")

        query_result = client.execute_read(_build_typed_path_query(body))
        count_result = client.execute_read(_build_typed_path_query(body, count_only=True))
        total = 0
        if count_result.records:
            total = int(count_result.records[0].get("total") or 0)

        items = [
            _typed_path_from_record(body, record, source.labels) for record in query_result.records
        ]
        data = TypedPathListData(
            items=items,
            total=total,
            limit=body.limit,
            offset=body.offset,
        )
        return ApiResponse(data=data.model_dump())
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=str(exc))


@router.get("/subgraph/{node_id}", response_model=ApiResponse)
async def get_subgraph(
    node_id: str,
    depth: int = Query(1, ge=1, le=3, description="跳数 1-3"),
    limit: int = Query(50, ge=1, le=200, description="每跳最大边数"),
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
                    vid, direction=direction, edge_type=edge_type, limit=limit
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

        # 限制返回量
        if len(nodes) > limit:
            nodes = nodes[:limit]
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
