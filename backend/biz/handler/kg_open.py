"""kg-open 对外图谱查询：类驱动的三个只读接口。

设计口径（docs/kg-open-external-query-api.md）：
- 入口是 Schema 大类（实体类/关系类名），不暴露 VID 入参，不做属性条件过滤；
- 实体属性、边属性整体透传，契约不逐字段定义；
- 图调用统一走 graph_exec_slot 执行预算，与平台内部查询同护栏。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from application.schema_management import SchemaManagementApplication
from biz.dependencies.kg_open_auth import KgOpenAuth

# 复用 graph_search 的客户端工厂/标签计数缓存/nGQL 字面量转义：与平台内部
# 查询同一份实现与缓存，避免两套口径各算各的。
from biz.handler.graph_search import _get_client, _ngql_literal, _node_count_cached
from biz.schemas.common import ApiResponse
from infra.graph_exec_budget import GraphExecOverloaded, graph_exec_slot
from infra.workflow_mysql import get_workflow_session

router = APIRouter(prefix="/kg-open", tags=["kg-open"])
logger = logging.getLogger(__name__)

# 图上 TAG/EDGE 名与目录 name 同源，均为 nGQL 标识符；其余输入直接拒绝。
_SCHEMA_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
# FETCH 批量取点分块：单条语句 VID 数上限，防止超长语句。
_FETCH_VERTEX_CHUNK = 100


def _require_schema_name(name: str) -> str:
    if not _SCHEMA_NAME_PATTERN.fullmatch(name):
        raise HTTPException(status_code=400, detail=f"不合法的类型名: {name}")
    return name


def _overloaded() -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="图查询执行过载，请稍后重试",
        headers={"Retry-After": "1"},
    )


def _entity_payload(entity: Any) -> dict[str, Any]:
    """GraphNode / FETCH 顶点行 → 对外实体结构（id/type/name/全属性）。"""
    if isinstance(entity, dict):
        vid = entity.get("id")
        labels = list(entity.get("labels") or [])
        properties = dict(entity.get("properties") or {})
    else:
        vid = entity.id
        labels = list(entity.labels or [])
        properties = dict(entity.properties or {})
    return {
        "id": str(vid),
        "type": labels[0] if labels else "",
        "name": str(properties.get("name") or ""),
        "properties": properties,
    }


def _fetch_entities_by_vids(client: Any, vids: list[str]) -> dict[str, dict[str, Any]]:
    """按 VID 批量取实体：FETCH PROP ON * ... YIELD vertex（TRS 定制必须带 YIELD）。

    端点不存在的 VID 不出现在结果里，调用方据此把悬挂边端点置 null。
    """
    found: dict[str, dict[str, Any]] = {}
    for start in range(0, len(vids), _FETCH_VERTEX_CHUNK):
        chunk = vids[start : start + _FETCH_VERTEX_CHUNK]
        literals = ", ".join(_ngql_literal(vid) for vid in chunk)
        result = client.execute_read(f"FETCH PROP ON * {literals} YIELD vertex AS v")
        for row in result.records or []:
            vertex = row.get("v") if isinstance(row, dict) else None
            if isinstance(vertex, dict) and vertex.get("id") is not None:
                payload = _entity_payload(vertex)
                found[payload["id"]] = payload
    return found


def _catalog(session: Session, space: str) -> dict[str, Any]:
    return SchemaManagementApplication(session).external_catalog(space)


@router.get("/schema")
async def get_open_schema(
    ctx: KgOpenAuth,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    """图谱地图：实体/关系类、属性定义、关系端点类型与图上数量。"""
    catalog = _catalog(session, ctx.space)
    try:
        async with graph_exec_slot():
            stats = await asyncio.to_thread(_get_client(ctx.space).stats_snapshot)
    except GraphExecOverloaded as exc:
        raise _overloaded() from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kg-open schema 查询失败")
        raise HTTPException(status_code=502, detail="图数据服务暂时不可用，请稍后重试") from exc
    tag_counts = stats.get("tags") or {}
    edge_counts = stats.get("edges") or {}
    for item in catalog["entityTypes"]:
        item["count"] = int(tag_counts.get(item["name"], 0))
    for item in catalog["relationTypes"]:
        item["count"] = int(edge_counts.get(item["name"], 0))
    return ApiResponse(data={"space": ctx.space, **catalog})


@router.get("/entity-types/{name}/entities")
async def list_entities_by_type(
    ctx: KgOpenAuth,
    name: str,
    session: Annotated[Session, Depends(get_workflow_session)],
    limit: int = Query(20, ge=1, le=500, description="每页实体数"),
    offset: int = Query(0, ge=0, le=10_000_000, description="翻页偏移"),
) -> ApiResponse:
    """按实体类分页拉实体（全属性）；relationTypes 为该类参与的关系类清单。"""
    _require_schema_name(name)
    catalog = _catalog(session, ctx.space)
    if name not in {item["name"] for item in catalog["entityTypes"]}:
        raise HTTPException(status_code=404, detail=f"实体类型不存在: {name}")
    client = _get_client(ctx.space)
    try:
        async with graph_exec_slot():
            nodes = await asyncio.to_thread(
                client.paged_nodes_by_label, name, limit=limit, offset=offset
            )
            total = await _node_count_cached(client, ctx.space, name)
    except GraphExecOverloaded as exc:
        raise _overloaded() from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kg-open 实体类查询失败 type=%s", name)
        raise HTTPException(status_code=502, detail="图数据服务暂时不可用，请稍后重试") from exc
    relation_types = sorted(
        item["name"]
        for item in catalog["relationTypes"]
        if item["sourceType"] == name or item["targetType"] == name
    )
    return ApiResponse(
        data={
            "space": ctx.space,
            "entityType": name,
            "entities": [_entity_payload(node) for node in nodes],
            "total": total,
            "limit": limit,
            "offset": offset,
            "relationTypes": relation_types,
        }
    )


@router.get("/relation-types/{name}/edges")
async def list_edges_by_type(
    ctx: KgOpenAuth,
    name: str,
    session: Annotated[Session, Depends(get_workflow_session)],
    limit: int = Query(20, ge=1, le=500, description="每页边数"),
    offset: int = Query(0, ge=0, le=10_000_000, description="翻页偏移"),
    include_entities: bool = Query(
        True, alias="includeEntities", description="false 时只返回边不补端点实体"
    ),
) -> ApiResponse:
    """按关系类分页拉边；includeEntities=true 时补两端实体（悬挂端点为 null）。"""
    _require_schema_name(name)
    catalog = _catalog(session, ctx.space)
    if name not in {item["name"] for item in catalog["relationTypes"]}:
        raise HTTPException(status_code=404, detail=f"关系类型不存在: {name}")
    client = _get_client(ctx.space)
    try:
        async with graph_exec_slot():
            # 边列表走 LOOKUP 边索引分页：REST /edges/type 耗时与边总量正相关
            # （实测两万级及无索引小类型 30s+ 超时），无边索引自动回退 MATCH。
            edges_page = await asyncio.to_thread(
                client.paged_edges_by_type, name, limit=limit, offset=offset
            )
            # trs-graph REST 的 page.total 对部分边类型恒为 0（实测返回行非空仍报 0），
            # total 用 SHOW STATS 口径（与 /schema 的 count 同源，含悬挂边），
            # 空间从未跑过统计时回退当页行数。
            stats_total = int(
                (await asyncio.to_thread(client.stats_snapshot)).get("edges", {}).get(name, 0)
            )
            total = stats_total or len(edges_page)
            entity_by_vid: dict[str, dict[str, Any]] = {}
            if include_entities and edges_page:
                # 边端点 VID 与 /nodes/{id} 同口径去引号后再拼 FETCH 字面量。
                vids = sorted(
                    {str(edge.source_id).strip('"') for edge in edges_page}
                    | {str(edge.target_id).strip('"') for edge in edges_page}
                )
                entity_by_vid = await asyncio.to_thread(_fetch_entities_by_vids, client, vids)
    except GraphExecOverloaded as exc:
        raise _overloaded() from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kg-open 关系类查询失败 type=%s", name)
        raise HTTPException(status_code=502, detail="图数据服务暂时不可用，请稍后重试") from exc
    edges: list[dict[str, Any]] = []
    for edge in edges_page:
        source = str(edge.source_id).strip('"')
        target = str(edge.target_id).strip('"')
        entry: dict[str, Any] = {
            "type": edge.type,
            "source": source,
            "target": target,
            "properties": dict(edge.properties or {}),
        }
        if include_entities:
            entry["sourceEntity"] = entity_by_vid.get(source)
            entry["targetEntity"] = entity_by_vid.get(target)
        edges.append(entry)
    return ApiResponse(
        data={
            "space": ctx.space,
            "relationType": name,
            "edges": edges,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )
