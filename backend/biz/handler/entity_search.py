"""实体检索 API：图直查浏览 + Milvus 混合搜索（embedding + BM25 关键词）。"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from application.entity_search import EntitySearchApplication
from biz.dependencies.auth import CurrentActor
from biz.schemas.common import ApiResponse
from biz.schemas.entity_search import EntityReindexRequest, EntitySearchRequest
from infra.workflow_mysql import get_workflow_session
from service.entity_search import (
    EntitySearchError,
    EntitySearchReindexInProgressError,
)

router = APIRouter(prefix="/entity-search", tags=["entity-search"])

# 实体列表浏览是重查询（Nebula 分页扫描+排序，dev2 空间 52 万实体），
# 500 并发下 api 连接积压产生 502。结果按 查询参数 做 15s TTL 缓存
# （同参数结果一致）；实体数据由 ETL 持续写入，15s 滞后可接受。
# TTL 环境变量 ENTITY_BROWSE_CACHE_SECONDS 可调，0=关闭。
_BROWSE_CACHE_SECONDS = float(os.getenv("ENTITY_BROWSE_CACHE_SECONDS", "15"))
_browse_payload_cache: dict[str, tuple[float, str]] = {}


def _browse_cache_get(key: str) -> str | None:
    entry = _browse_payload_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _browse_cache_put(key: str, payload: str) -> None:
    if len(_browse_payload_cache) > 1024:
        now = time.monotonic()
        for stale in [k for k, v in _browse_payload_cache.items() if v[0] <= now]:
            _browse_payload_cache.pop(stale, None)
    _browse_payload_cache[key] = (time.monotonic() + _BROWSE_CACHE_SECONDS, payload)



def _application(session: Session) -> EntitySearchApplication:
    return EntitySearchApplication(session)


def _raise_domain_error(exc: EntitySearchError) -> None:
    if isinstance(exc, EntitySearchReindexInProgressError):
        status_code = 409
    else:
        status_code = 400
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _ensure_space_access(actor: CurrentActor, space: str | None) -> None:
    """非管理员访问指定图空间时校验绑定关系；space=None（默认空间）与管理员放行。

    与 graph-search 同一规则，复用其实现。
    """
    from biz.handler.graph_search import _ensure_space_access as graph_space_access

    graph_space_access(actor, space)


@router.get("/entities", response_model=ApiResponse)
async def browse_entities(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    space: str | None = Query(None, max_length=64, description="图空间，缺省当前空间"),
    entityType: str | None = Query(None, max_length=64, description="实体类型过滤"),
    limit: int = Query(10, ge=1, le=100, description="每页条数"),
    offset: int = Query(0, ge=0, le=100000),
) -> ApiResponse:
    """浏览实体（关键词为空的默认视图）：图空间直查分页，页内按 vid 排序。"""
    _ensure_space_access(actor, space)
    cache_key = f"browse:{space}:{entityType}:{limit}:{offset}"
    cached = _browse_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    app = _application(session)
    try:
        data = await asyncio.to_thread(
            app.browse,
            space=space,
            entity_type=entityType,
            limit=limit,
            offset=offset,
        )
    except EntitySearchError as exc:
        _raise_domain_error(exc)
    payload = json.dumps(
        {"code": 200, "success": True, "data": data, "msg": "success"},
        ensure_ascii=False,
        default=str,
    )
    _browse_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


@router.get("/types", response_model=ApiResponse)
def list_entity_types(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    space: str | None = Query(None, max_length=64, description="图空间"),
) -> ApiResponse:
    """索引内实体类型 + 数量（前端类型过滤下拉）。"""
    return ApiResponse(data={"items": _application(session).types(space=space)})


@router.get("/index-status", response_model=ApiResponse)
def get_index_status(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    space: str | None = Query(None, max_length=64, description="图空间"),
) -> ApiResponse:
    """实体索引状态（是否已建、实体数、类型统计、更新时间、是否重建中）。"""
    return ApiResponse(data=_application(session).status(space=space))


@router.post("/search")
async def search_entities(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: EntitySearchRequest,
) -> Response:
    """实体混合检索：m3e 语义向量 + BM25 关键词（RRF 融合），支持实体类型过滤。

    混合检索为重查询（m3e 向量化 + Milvus + 图直查），同关键词+空间+分页的
    重复检索做 15s TTL 缓存（实体由 ETL 持续写入，15s 滞后可接受）。"""
    _ensure_space_access(actor, payload.space)
    cache_key = f"search:{payload.space}:{payload.entityType}:{payload.keyword}:{payload.limit}:{payload.offset}"
    cached = _browse_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    app = _application(session)
    try:
        # 图/Milvus/embedding 均为同步 IO，放线程池避免阻塞事件循环
        data = await asyncio.to_thread(
            app.search,
            keyword=payload.keyword,
            space=payload.space,
            entity_type=payload.entityType,
            limit=payload.limit,
            offset=payload.offset,
        )
    except EntitySearchError as exc:
        _raise_domain_error(exc)
    payload_json = json.dumps(
        {"code": 200, "success": True, "data": data, "msg": "success"},
        ensure_ascii=False,
        default=str,
    )
    _browse_cache_put(cache_key, payload_json)
    return Response(payload_json, media_type="application/json")


@router.post("/reindex", response_model=ApiResponse)
async def reindex_entities(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: EntityReindexRequest | None = None,
) -> ApiResponse:
    """全量重建图空间实体 Milvus 索引（管理员）：图 → embedding + BM25 → kg_entity。"""
    if not actor.is_admin:
        raise HTTPException(status_code=403, detail="仅平台管理员可以重建实体索引")
    app = _application(session)
    request = payload or EntityReindexRequest()
    try:
        data = await asyncio.to_thread(
            app.reindex,
            space=request.space,
            entity_types=request.entityTypes,
        )
        return ApiResponse(data=data, msg="实体索引重建完成")
    except EntitySearchError as exc:
        _raise_domain_error(exc)
