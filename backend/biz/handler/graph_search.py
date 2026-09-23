"""图谱搜索 API：支撑前端图谱查询展示，返回 JSON 格式的点边数据。

所有端点支持 ``space`` 参数指定图空间（如 dev/techkg），缺省用 .env 的 TRS_GRAPH_SPACE。
常规端点只调用 TRSGraphClient 的封装方法；受控路径查询把经过 Pydantic 白名单校验的
逐跳约束编译为只读 nGQL，不接受调用方传入任意查询语句。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from biz.dependencies.auth import CurrentActor
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from infra.graph_db import TRSGraphClient, get_space_client, get_trs_graph_client
from infra.graph_db.exceptions import GraphRequestError
from infra.graph_db.models import GraphEdge, GraphNode
from infra.graph_exec_budget import GraphExecOverloaded, graph_exec_slot
from infra.mysql import create_session

router = APIRouter(prefix="/graph-search", tags=["graph-search"])
logger = logging.getLogger(__name__)


def _graph_query_error(operation: str) -> ApiResponse:
    logger.exception("图数据查询失败 operation=%s", operation)
    return ApiResponse(code=500, success=False, msg="图数据查询失败")


def _graph_overloaded(exc: GraphExecOverloaded) -> ApiResponse:
    """过载快速拒绝（业务码 429）：让调用方立刻看到"图查询过载"并重试，
    而不是在无界排队里慢慢拖到上游超时（表现为网关 502）。"""
    logger.warning("图执行层过载拒绝：%s", exc)
    return ApiResponse(code=429, success=False, msg=str(exc))


# Nebula 的 count 是全量扫描，单个边类型就要 2~4 秒，全库统计一遍近 50 秒，
# 因此按空间缓存整份统计结果，并把扫描并行化。
_STATS_CACHE_TTL_SECONDS = 300.0
# 统计扫描并发。开太大会挤占图服务连接，把同时进来的其它查询（如全景图分层）压挂。
_STATS_SCAN_WORKERS = 4
_stats_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_stats_locks: dict[str, asyncio.Lock] = {}
_stats_refreshing: set[str] = set()
# 单标签 count 兜底路径（REST node-count）是全量扫描（秒级），按 (空间, 标签) 缓存；
# 首选 SHOW STATS（毫秒级，见 client.stats_tag_counts）。
_NODE_COUNT_TTL_SECONDS = 300.0
_node_count_cache: dict[tuple[str, str], tuple[float, int]] = {}


async def _node_count_cached(client: TRSGraphClient, space: str | None, label: str) -> int:
    """带 TTL 缓存的标签节点数（label_count 优先 SHOW STATS，毫秒级）。"""
    key = (space or "", label)
    cached = _node_count_cache.get(key)
    if cached and time.monotonic() - cached[0] < _NODE_COUNT_TTL_SECONDS:
        return cached[1]
    count = await asyncio.to_thread(client.label_count, label)
    _node_count_cache[key] = (time.monotonic(), count)
    return count


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
    countTotal: bool = Field(
        default=True,
        description=(
            "是否执行全量 count 聚合（无 LIMIT 的全路径枚举，是最重的查询）。"
            "翻页调用方对后续页传 false 可省掉重复统计，此时返回 total=-1（未统计）。"
        ),
    )
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
    指定 space 时用 infra.graph_db.get_space_client（按空间名缓存）。
    """
    if not space:
        return get_trs_graph_client()
    return get_space_client(space)


def _ensure_space_access(actor: Any, space: str | None) -> None:
    """默认业务空间允许登录用户读取；其他空间仍校验绑定关系。

    在端点 try 块之前调用，HTTPException 不会被 except Exception 吞成 500。
    """
    if not space or actor.is_admin:
        return
    from service.graph_space import GraphSpaceService, default_graph_space

    if space == default_graph_space():
        return

    session = create_session()
    try:
        bound = GraphSpaceService(session).is_bound(actor.user_id, space)
    finally:
        session.close()
    if not bound:
        raise HTTPException(status_code=403, detail=f"无权访问图空间 {space}，请先在配置页绑定")


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


@router.get("/nodes/{node_id:path}")
async def get_node(
    actor: CurrentActor,
    node_id: str,
    space: str | None = Query(None, description="图空间，如 dev/techkg，缺省用默认空间"),
) -> ApiResponse:
    """按 VID 查单个节点详情。

    路径参数用 path 转换器：DOI 等业务 VID 本身含 ``/``（如
    ``paper_ref_10.1111/jth.14768``），经网关/uvicorn 解码后是多个路径段，
    单段参数会直接 404 Not Found。
    """
    _ensure_space_access(actor, space)
    node_id = node_id.strip('"')
    try:
        async with graph_exec_slot():
            node = await asyncio.to_thread(_get_client(space).get_node, node_id)
        if node is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {node_id}")
        return ApiResponse(data=_node_to_data(node).model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("get_node")


@router.get("/nodes")
async def list_nodes(
    actor: CurrentActor,
    label: str = Query(..., description="节点标签，如 Paper/Person/Journal/Report"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """按标签分页查询节点列表（total 为库里真实总数）。"""
    _ensure_space_access(actor, space)
    try:
        client = _get_client(space)
        # TRSGraphClient 底层是同步 httpx.Client，直接在 async handler 里调会把
        # 事件循环卡住，进程内并发（如全景图分层并发拉取）全部退化成串行。
        # nGQL 直查分页 + SHOW STATS 计数：REST /nodes/label 与 node-count 在
        # trs-graph 侧均为全量扫描，大标签（Paper 十万级）30s+ 超时（2026-09-21）。
        # 整个分页+计数过程占用一个公共执行名额（含 _node_count_cached 的取数）。
        async with graph_exec_slot():
            nodes = await asyncio.to_thread(
                client.paged_nodes_by_label, label, limit=limit, offset=offset
            )
            items = [_node_to_data(n).model_dump() for n in nodes]
            total = await _node_count_cached(client, space, label)
        return ApiResponse(data=NodeListData(items=items, total=total).model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("list_nodes")


@router.post("/nodes/search")
async def search_nodes(
    actor: CurrentActor,
    label: str = Query(..., description="节点标签"),
    properties: dict[str, Any] | None = None,
    limit: int = Query(20, ge=1, le=500),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """按属性搜索节点（如 {"doi": "10.xxx"} 查论文）。"""
    _ensure_space_access(actor, space)
    try:
        async with graph_exec_slot():
            result = await asyncio.to_thread(
                _get_client(space).find_nodes, [label], properties or {}, limit=limit
            )
        items = [_node_to_data(n).model_dump() for n in result.items]
        return ApiResponse(data=NodeListData(items=items, total=len(items)).model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("search_nodes")


@router.post("/paths/search", response_model=ApiResponse)
async def search_typed_paths(body: TypedPathSearchRequest, actor: CurrentActor) -> ApiResponse:
    """按逐跳边类型和方向查询全部匹配路径，支持中间节点属性过滤与分页。"""
    _ensure_space_access(actor, body.space)
    try:
        client = _get_client(body.space)

        # TRSGraphClient 底层是同步 httpx.Client，直接在 async handler 里调用会
        # 冻结整个事件循环（论文合作经进程内 ASGI 回环翻页调用本端点，冻结期间
        # 该 worker 上所有请求与并发任务全部退化为串行）。三步打包进一次
        # to_thread：保序、单次线程跳转，与 list_nodes 等端点同口径。
        def _run_query() -> tuple[GraphNode | None, list[dict[str, Any]], int]:
            source = client.get_node(body.sourceId)
            if source is None:
                return None, [], 0
            records = client.execute_read(_build_typed_path_query(body)).records
            total = -1
            if body.countTotal:
                count_result = client.execute_read(_build_typed_path_query(body, count_only=True))
                if count_result.records:
                    total = int(count_result.records[0].get("total") or 0)
            return source, records, total

        async with graph_exec_slot():
            source, records, total = await asyncio.to_thread(_run_query)
        if source is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {body.sourceId}")

        # get_node 已验证该 VID 可用。dev 空间的真实 Person VID 保留 person_* 前缀；
        # techkg 请求本身传入无前缀 Scholar VID，因此两种空间都直接保留请求 ID。
        items = [_typed_path_from_record(body, record, source.labels) for record in records]
        data = TypedPathListData(
            items=items,
            total=total,
            limit=body.limit,
            offset=body.offset,
        )
        return ApiResponse(data=data.model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("search_typed_paths")


@router.get("/subgraph/{node_id:path}")
async def get_subgraph(
    actor: CurrentActor,
    node_id: str,
    depth: int = Query(1, ge=1, le=3, description="跳数 1-3"),
    limit: int = Query(50, ge=1, le=256, description="每跳最大新边数"),
    offset: int = Query(0, ge=0, description="一跳遍历分页偏移量"),
    edge_type: str | None = Query(None, description="边类型过滤，如 AUTHORED_BY"),
    direction: Literal["out", "in", "both"] = Query("both", description="方向: out/in/both"),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的 N 跳子图（点 + 边），前端直接渲染图谱。

    路径参数用 path 转换器：同 /nodes/{node_id}，兼容含 ``/`` 的 VID（DOI）。
    """
    _ensure_space_access(actor, space)
    node_id = node_id.strip('"')
    try:
        async with graph_exec_slot():
            subgraph = await asyncio.to_thread(
                _collect_subgraph,
                _get_client(space),
                node_id,
                depth,
                limit,
                offset,
                edge_type,
                direction,
            )
        if subgraph is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {node_id}")
        return ApiResponse(data=SubgraphData(**subgraph).model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("get_subgraph")


def _collect_subgraph(
    client: TRSGraphClient,
    node_id: str,
    depth: int,
    limit: int,
    offset: int,
    edge_type: str | None,
    direction: str,
) -> dict[str, Any] | None:
    """同步收集 N 跳子图（多步图查询，整体放线程里执行以免卡住事件循环）。"""
    # 中心节点；查不到属性但有边（Nebula 悬挂点，如引用边的 DOI 端点，
    # FETCH/MATCH 均不可见）时以占位节点继续，保证邻域子图仍可渲染。
    center = client.get_node(node_id)
    if center is None:
        if not client.get_node_edges(node_id, direction="both", limit=1):
            return None
        center = GraphNode(id=node_id, labels=[], properties={})

    nodes: list[GraphNodeData] = [_node_to_data(center)]
    edges: list[GraphEdgeData] = []
    seen_edge_ids: set[str] = set()
    seen_vids = {str(center.id)}

    # 逐跳扩展：limit 是「每跳上限」——每跳最多收录 limit 条新边（已收录过的边
    # 不占预算），预算逐跳重置。配额在跳内按前沿节点均分（向上取整）：每个节点
    # 都能分到可展示的出边名额，而不是 BFS 序靠前的节点吃光预算；某节点边数
    # 不足其配额时，剩余名额自动回流给后面的节点。查询页按 4 倍配额过采样：
    # 原始返回页里会混入已收录过的回边/重复边（不占预算但占查询页名额），
    # 只按配额取页会让「每跳最多 limit 条新边」达不到，收集侧再按配额截断。
    frontier = [node_id]
    for _hop in range(depth):
        next_frontier: list[str] = []
        # 本跳新邻居只记 VID，跳末一次批量取点：遍历只用 ID。旧实现每邻居
        # 一次 get_node，一跳 200 个邻居就是 200 次 TRS 往返（会话池高频
        # 借用 + 单请求数秒级串行时延）；批量后每跳 ceil(n/块) 次。
        discovered: list[str] = []
        remaining = limit
        pending = len(frontier)
        for vid in frontier:
            if remaining <= 0 or pending <= 0:
                break
            quota = min(remaining, -(-remaining // pending))
            edge_list = client.get_node_edges(
                vid,
                direction=direction,
                edge_type=edge_type,
                limit=min(256, quota * 4),
                offset=offset,
            )
            pending -= 1
            collected = 0
            for e in edge_list:
                if collected >= quota:
                    break
                edge_data = _edge_to_data(e)

                edge_key = edge_data.id or f"{edge_data.source}|{edge_data.type}|{edge_data.target}"

                if edge_key in seen_edge_ids:
                    continue
                seen_edge_ids.add(edge_key)
                edges.append(edge_data)
                collected += 1
                remaining -= 1
                neighbor_id = str(e.target_id if str(e.source_id) == vid else e.source_id)
                if neighbor_id not in seen_vids:
                    seen_vids.add(neighbor_id)
                    discovered.append(neighbor_id)
        found = client.get_nodes_bulk(discovered) if discovered else {}
        for vid in discovered:
            neighbor = found.get(vid)
            if neighbor is None:
                # 悬挂点邻居（边端点无 tag，FETCH/MATCH 不可见）：占位渲染。
                # 边已收集，端点必须出现在 nodes 里，否则画布上边指向幽灵节点。
                neighbor = GraphNode(id=vid, labels=[], properties={})
            nodes.append(_node_to_data(neighbor))
            next_frontier.append(vid)
        frontier = next_frontier

    return {"nodes": nodes, "edges": edges}


@router.get("/filtered-subgraph/{node_id}")
async def get_filtered_subgraph(
    actor: CurrentActor,
    node_id: str,
    edge_types: str = Query(..., description="逗号分隔的边类型，如 EXECUTIVE_OF,HAS_PARTICPTANT"),
    depth: int = Query(2, ge=1, le=3, description="跳数 1-3"),
    limit: int = Query(50, ge=1, le=256, description="每种边类型每跳最大边数"),
    direction: Literal["out", "in", "both"] = Query("both", description="方向: out/in/both"),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的 N 跳子图，只遍历指定边类型（多边类型），避免捞无关边。

    与 /subgraph 的区别：支持多边类型过滤（逗号分隔），每种边类型单独查，
    不会因 limit 截断把需要的边挤掉（论文/合作者等不会占名额）。
    """
    _ensure_space_access(actor, space)
    et_set = [et.strip() for et in edge_types.split(",") if et.strip()]
    if not et_set:
        return ApiResponse(code=422, success=False, msg="edge_types 不能为空")
    try:
        async with graph_exec_slot():
            subgraph = await asyncio.to_thread(
                _collect_filtered_subgraph,
                _get_client(space),
                node_id,
                et_set,
                depth,
                limit,
                direction,
            )
        if subgraph is None:
            return ApiResponse(code=404, success=False, msg=f"节点不存在: {node_id}")
        return ApiResponse(data=SubgraphData(**subgraph).model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("get_filtered_subgraph")


def _pair_rows(
    client: TRSGraphClient,
    pair_edges: dict[tuple[str, str], list[GraphEdge]],
    vid: str,
    et: str,
    *,
    direction: str,
    quota: int,
    rest_fallback: bool,
) -> Iterator[GraphEdge]:
    """(源, 边类型) 的候选边流：批量行优先，批量不完整时惰性回退单源 REST。

    批量页被行数上限截断（或批量语句失败）时，该源在该类型下的行可能被
    同批超高度数源挤掉，配额未必填满——回退单源 REST 补一页（4 倍配额
    过采样，与旧逐组合路径同一口径），保证「每类型每跳上限」可达。惰性：
    消费方配额满足即停止拉取，REST 只在批量行不足以填满配额时才真正发出；
    完整批量（行数 < 上限）里没有的组合就是真无边，不回源。
    """
    yield from pair_edges.get((vid, et), [])
    if not rest_fallback:
        return
    try:
        yield from client.get_node_edges(
            vid, direction=direction, edge_type=et, limit=min(256, quota * 4)
        )
    except GraphRequestError:
        # 该边类型在当前图空间不存在（trs traversal 400）等查询失败，
        # 跳过该组合不阻断整个子图——与旧逐组合路径的取舍一致。
        return


def _collect_filtered_subgraph(
    client: TRSGraphClient,
    node_id: str,
    et_set: list[str],
    depth: int,
    limit: int,
    direction: str,
) -> dict[str, Any] | None:
    """同步收集多边类型过滤的 N 跳子图（整体放线程里执行以免卡住事件循环）。"""
    center = client.get_node(node_id)
    if center is None:
        return None

    nodes: list[GraphNodeData] = [_node_to_data(center)]
    edges: list[GraphEdgeData] = []
    seen_edge_ids: set[str] = set()
    seen_vids = {str(center.id)}
    frontier = [node_id]

    for _hop in range(depth):
        next_frontier: list[str] = []
        # 本跳新邻居只记 VID，跳末一次批量取点（同 _collect_subgraph：旧实现
        # 每邻居一次 get_node，重点企业关系 12 边类型 × 2 跳可达数百次往返）。
        discovered: list[str] = []
        # 邻接同样整跳批量：一条多源多类型 GO 覆盖全部 (源 × 边类型) 组合
        # （旧实现逐组合 REST，12 类型 × 46 前沿 = 552 次往返）。配额核算
        # 仍在下方逐源逐类型做，与旧实现的预算/均分/回流语义逐行等价，
        # 批量只是换取数通道：被行上限截断或语句失败时按组合惰性回退 REST。
        pair_edges: dict[tuple[str, str], list[GraphEdge]] = {}
        rest_fallback = False
        if frontier:
            try:
                pair_edges, truncated = client.get_edges_bulk(frontier, et_set, direction=direction)
                rest_fallback = truncated
            except GraphRequestError as exc:
                # 批量语句失败（如临时语义/会话错误）不整体 500：置空批量并
                # 放开单源回退，退化为旧逐组合 REST 路径。
                logger.warning("批量邻接失败，本跳退回逐组合 REST: %s", exc)
                pair_edges, rest_fallback = {}, True
        # 批量行是裸 Nebula 结果，而 REST /traversal 会静默滤掉悬挂端点的边
        # （2026-09-23 实测 person→悬挂org 的 AFFILIATED_WITH 被 trs 吞掉）。
        # 先对本跳全部行端点做一次存在性批量取点，把悬挂端点的行在配额核算
        # 前剔除——与旧 REST 可见口径逐字一致：否则边画向 nodes 里不存在的
        # 端点（幽灵边），且悬挂行挤占配额挤掉真实边。REST 补查行已被 trs
        # 过滤，无需处理。已收录/前沿节点必真实，不必重复取点。
        row_nodes: dict[str, GraphNode] = {}
        if pair_edges:
            endpoints = [
                vid
                for vid in dict.fromkeys(
                    str(v)
                    for rows in pair_edges.values()
                    for e in rows
                    for v in (e.source_id, e.target_id)
                )
                if vid not in seen_vids
            ]
            row_nodes = client.get_nodes_bulk(endpoints) if endpoints else {}
            real_vids = set(seen_vids) | set(row_nodes)
            pair_edges = {
                key: [
                    e
                    for e in rows
                    if str(e.source_id) in real_vids and str(e.target_id) in real_vids
                ]
                for key, rows in pair_edges.items()
            }
        # limit 是「每种边类型每跳上限」：逐跳逐类型重置预算，已收录过的边
        # 不占预算；不做全局截断（否则第一跳吃光预算，深跳一条边进不来）。
        # 配额按前沿节点均分（向上取整）——每个节点都能分到可展示的出边名额，
        # 某节点边数不足时余量回流给后面的节点。查询页按 4 倍配额过采样
        # （跳过已见回边后再按配额截断），保证每类型每跳上限真正可达。
        type_budgets = {et: limit for et in et_set}
        pending = len(frontier)
        for vid in frontier:
            # 每种边类型单独核算配额，避免无关边占 limit 名额
            for et in et_set:
                budget = type_budgets[et]
                if budget <= 0 or pending <= 0:
                    continue
                quota = min(budget, -(-budget // pending))
                collected = 0
                for e in _pair_rows(
                    client,
                    pair_edges,
                    vid,
                    et,
                    direction=direction,
                    quota=quota,
                    rest_fallback=rest_fallback,
                ):
                    if collected >= quota:
                        break
                    edge_data = _edge_to_data(e)
                    edge_key = (
                        edge_data.id or f"{edge_data.source}|{edge_data.type}|{edge_data.target}"
                    )
                    if edge_key in seen_edge_ids:
                        continue
                    seen_edge_ids.add(edge_key)
                    edges.append(edge_data)
                    collected += 1
                    type_budgets[et] -= 1
                    neighbor_id = str(e.target_id if str(e.source_id) == vid else e.source_id)
                    if neighbor_id not in seen_vids:
                        seen_vids.add(neighbor_id)
                        discovered.append(neighbor_id)
            pending -= 1
        # 补点收尾：本跳新邻居优先复用批量行的存在性取点结果（row_nodes），
        # REST 补查行发现的邻居（仅截断/回退路径存在）再补一次批量取点。
        # 悬挂邻居不进 nodes/前沿——悬挂行已在上面按 REST 口径剔除，这里只
        # 处理确实真实存在的邻居。
        rest_discovered = [vid for vid in discovered if vid not in row_nodes]
        found = {
            **row_nodes,
            **(client.get_nodes_bulk(rest_discovered) if rest_discovered else {}),
        }
        for vid in discovered:
            neighbor = found.get(vid)
            if neighbor is None:
                continue
            nodes.append(_node_to_data(neighbor))
            next_frontier.append(vid)
        frontier = next_frontier

    return {"nodes": nodes, "edges": edges}


@router.get("/node/{node_id}/edges")
async def get_node_edges(
    actor: CurrentActor,
    node_id: str,
    direction: Literal["out", "in", "both"] = Query("both", description="out/in/both"),
    edge_type: str | None = Query(None, description="边类型过滤"),
    limit: int = Query(50, ge=1, le=200),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的所有边（不含邻居节点属性，轻量）。"""
    _ensure_space_access(actor, space)
    try:
        async with graph_exec_slot():
            edge_list = await asyncio.to_thread(
                _get_client(space).get_node_edges,
                node_id,
                direction=direction,
                edge_type=edge_type,
                limit=limit,
            )
        edges = [_edge_to_data(e).model_dump() for e in edge_list]
        return ApiResponse(data={"edges": edges, "total": len(edges)})
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("get_node_edges")


@router.get("/node/{node_id}/neighbours")
async def get_neighbours(
    actor: CurrentActor,
    node_id: str,
    direction: Literal["out", "in", "both"] = Query("both", description="out/in/both"),
    edge_type: str | None = Query(None, description="边类型过滤"),
    limit: int = Query(50, ge=1, le=200),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查某节点的邻居节点（含属性）。"""
    _ensure_space_access(actor, space)
    try:
        # 与其它端点同口径：同步客户端调用放线程执行（async handler 里直调会
        # 卡住整个事件循环），并占用一个公共执行名额。
        async with graph_exec_slot():
            neighbours = await asyncio.to_thread(
                _get_client(space).get_neighbours,
                node_id,
                direction=direction,
                edge_type=edge_type,
                limit=limit,
            )
        nodes = [_node_to_data(n).model_dump() for n in neighbours]
        return ApiResponse(data={"nodes": nodes, "total": len(nodes)})
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("get_neighbours")


@router.get("/shortest-path")
async def shortest_path(
    actor: CurrentActor,
    source: str = Query(..., description="起始节点 VID"),
    target: str = Query(..., description="目标节点 VID"),
    max_depth: int = Query(10, ge=1, le=20, description="最大搜索深度"),
    space: str | None = Query(None, description="图空间"),
) -> ApiResponse:
    """查两个节点之间的最短路径。"""
    _ensure_space_access(actor, space)
    try:
        # 与其它端点同口径：同步客户端调用放线程执行，并占用一个公共执行名额。
        async with graph_exec_slot():
            path = await asyncio.to_thread(
                _get_client(space).shortest_path, source, target, max_depth=max_depth
            )
        if path is None:
            return ApiResponse(data=PathData(nodes=[], edges=[], found=False).model_dump())
        nodes = [_node_to_data(n).model_dump() for n in path.nodes]
        edges = [_edge_to_data(e).model_dump() for e in path.edges]
        return ApiResponse(data=PathData(nodes=nodes, edges=edges, found=True).model_dump())
    except GraphExecOverloaded as exc:
        return _graph_overloaded(exc)
    except Exception:
        return _graph_query_error("shortest_path")


@router.get("/spaces", response_model=ApiResponse)
async def list_spaces(actor: CurrentActor) -> ApiResponse:
    """全局选择器数据源：所有用户均为默认业务空间 + 本人绑定（绑定对所有用户生效）。"""
    try:
        from service.graph_space import GraphSpaceService

        session = create_session()
        try:
            items = GraphSpaceService(session).list_work_spaces_for_actor(actor)
        finally:
            session.close()
        return ApiResponse(data={"spaces": [item["name"] for item in items]})
    except Exception:  # noqa: BLE001
        # 绑定库不可用时仅返回默认业务空间，不泄露其他空间列表。
        from service.graph_space import default_graph_space

        return ApiResponse(data={"spaces": [default_graph_space()]})


@router.get("/stats")
async def get_stats(
    actor: CurrentActor,
    request: Request,
    space: str | None = Query(None, description="图空间"),
    refresh: bool = Query(False, description="强制重新统计，忽略缓存"),
) -> Response:
    """图统计：各标签节点数 + 各边类型边数（前端仪表盘用）。

    结果按空间缓存 5 分钟：底层 count 是全量扫描，实时统计一次要几十秒。
    外层再套 GET 结果缓存（命中返回预序列化 JSON，跳过序列化开销）；
    ``refresh=true`` 表示调用方要最新数据，跳过外层缓存且不写入。
    """
    _ensure_space_access(actor, space)
    if not refresh:
        cached = get_cache.try_get("graph-search:stats", request)
        if cached is not None:
            return cached
    try:
        data = await _load_stats(space, refresh=refresh)
        payload = ApiResponse(data=data)
    except GraphExecOverloaded as exc:
        payload = _graph_overloaded(exc)
    except Exception:
        payload = _graph_query_error("get_stats")
    if refresh:
        return Response(
            content=json.dumps(payload.model_dump(), ensure_ascii=False),
            media_type="application/json",
        )
    return get_cache.store("graph-search:stats", request, payload.model_dump())


async def _load_stats(space: str | None, *, refresh: bool) -> dict[str, Any]:
    """取（可能来自缓存的）图统计。

    Args:
        space: 图空间，``None`` 表示用配置里的默认空间。
        refresh: 为 ``True`` 时跳过缓存重新统计。

    Returns:
        ``{"nodes": {label: count}, "edges": {type: count}}``。
    """
    key = space or ""
    cached = _stats_cache.get(key)
    if not refresh and cached:
        if time.monotonic() - cached[0] < _STATS_CACHE_TTL_SECONDS:
            return cached[1]
        # 过期但仍有旧值：立即返回旧值，后台刷新，避免统计过期后首个请求再等 20 秒。
        _refresh_stats_in_background(space)
        return cached[1]

    lock = _stats_locks.setdefault(key, asyncio.Lock())
    async with lock:
        # 并发请求里只让第一个真正去扫库，其余直接复用它的结果。
        cached = _stats_cache.get(key)
        if not refresh and cached and time.monotonic() - cached[0] < _STATS_CACHE_TTL_SECONDS:
            return cached[1]
        if not refresh and cached:
            _refresh_stats_in_background(space)
            return cached[1]
        # 扫描和写缓存都放在线程里：即使调用方（如全景图的 3 秒超时）中途取消
        # 请求，扫描结果也会落到缓存，下一个请求就能直接命中。扫描是全库 count，
        # 也占一个公共执行名额（锁内先锁后名额，与后台刷新同序，无环）。
        async with graph_exec_slot():
            data = await asyncio.to_thread(_collect_stats_and_store, key, space)
        if data is not None:
            return data
        return _stats_cache[key][1] if key in _stats_cache else {"nodes": {}, "edges": {}}


def _refresh_stats_in_background(space: str | None) -> None:
    """后台刷新统计缓存；已有刷新任务在跑时直接跳过。"""
    key = space or ""
    if key in _stats_refreshing:
        return
    _stats_refreshing.add(key)

    async def _run() -> None:
        try:
            lock = _stats_locks.setdefault(key, asyncio.Lock())
            async with lock:
                # 同 _load_stats：先锁后名额，占满时等待（超时则本次放弃刷新，
                # 保留旧缓存），不与前台查询抢队首。
                async with graph_exec_slot():
                    data = await asyncio.to_thread(_collect_stats, space)
                _stats_cache[key] = (time.monotonic(), data)
        except Exception:  # noqa: BLE001 - 后台刷新失败保留旧缓存即可
            pass
        finally:
            _stats_refreshing.discard(key)

    asyncio.get_running_loop().create_task(_run())


def _collect_stats(space: str | None) -> dict[str, Any]:
    """实际扫库统计，阻塞执行，由调用方放到线程里跑。"""
    client = _get_client(space)
    tag_names = client.labels()
    edge_names = client.edge_types()
    with ThreadPoolExecutor(max_workers=_STATS_SCAN_WORKERS) as pool:
        node_counts = dict(zip(tag_names, pool.map(client.node_count, tag_names), strict=True))
        edge_counts = dict(zip(edge_names, pool.map(client.edge_count, edge_names), strict=True))
    return StatsData(nodes=node_counts, edges=edge_counts).model_dump()


def _collect_stats_and_store(key: str, space: str | None) -> dict[str, Any]:
    """扫库统计并写入缓存（线程内执行，结果不随请求取消而丢失）。"""
    data = _collect_stats(space)
    _stats_cache[key] = (time.monotonic(), data)
    return data


async def prewarm_stats() -> None:
    """启动时后台预热默认空间的统计缓存，失败不影响服务。"""
    try:
        await _load_stats(None, refresh=False)
    except Exception:  # noqa: BLE001
        pass
