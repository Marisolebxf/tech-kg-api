"""实体检索 API：图直查浏览 + Milvus 混合搜索（embedding + BM25 关键词）。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from application.entity_search import EntitySearchApplication
from biz.dependencies.auth import CurrentActor
from biz.dependencies.selected_graph_space import bind_selected_graph_space, resolve_selected_space
from biz.schemas.common import ApiResponse
from biz.schemas.entity_search import EntityReindexRequest, EntitySearchRequest
from infra.entity_response_cache import build_cache_key
from infra.graph_db.config import TRSGraphSettings
from infra.workflow_mysql import get_workflow_session
from service.entity_search import (
    EntitySearchError,
    EntitySearchReindexInProgressError,
    clear_entity_caches,
)
from service.entity_search import browse_cache as _browse_cache
from service.entity_search import search_cache as _search_cache

router = APIRouter(
    prefix="/entity-search",
    tags=["entity-search"],
    dependencies=[Depends(bind_selected_graph_space)],
)
logger = logging.getLogger(__name__)


class TemporaryCsvResponse(FileResponse):
    """成功下载或客户端断开后均回收临时文件。"""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            os.unlink(self.path)


# 浏览页默认缓存 5 分钟；关键词搜索仍使用较短 TTL，避免索引变化后旧命中保留过久。
# 两者都是 L1 进程缓存 + L2 Redis 共享缓存，Redis 不可用时自动降级到 L1。
# 实例定义在 service.entity_search（写图联动也要失效同一批缓存——FUNC-00813）。
_request_locks: dict[str, asyncio.Lock] = {}
_request_locks_guard = asyncio.Lock()


async def _request_lock(key: str) -> asyncio.Lock:
    async with _request_locks_guard:
        return _request_locks.setdefault(key, asyncio.Lock())


async def _release_request_lock(key: str, lock: asyncio.Lock) -> None:
    async with _request_locks_guard:
        if not lock.locked():
            _request_locks.pop(key, None)


async def _clear_entity_cache() -> None:
    """重建完成后清掉所有 worker 可见的旧搜索/浏览响应。"""
    await clear_entity_caches()


def _resolved_space(space: str | None) -> str:
    return resolve_selected_space(space) or TRSGraphSettings.from_env().space


def _serialized_success(data: dict) -> str:
    return json.dumps(
        {"code": 200, "success": True, "data": data, "msg": "success"},
        ensure_ascii=False,
        default=str,
    )


async def _load_browse_payload(
    session: Session,
    *,
    space: str | None,
    entity_type: str | None,
    limit: int,
    offset: int,
) -> tuple[str, bool]:
    """Return serialized browse response and whether it came from cache.

    The per-key lock collapses a burst of identical cold requests into one graph
    query. Other requests wait for that result and then read the freshly cached
    payload instead of repeating the expensive scan.
    """
    key = build_cache_key(
        "browse",
        space=_resolved_space(space),
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )
    cached = await _browse_cache.get(key)
    if cached is not None:
        return cached, True

    lock = await _request_lock(key)
    try:
        async with lock:
            cached = await _browse_cache.get(key)
            if cached is not None:
                return cached, True
            data = await asyncio.to_thread(
                _application(session).browse,
                space=space,
                entity_type=entity_type,
                limit=limit,
                offset=offset,
            )
            payload = _serialized_success(data)
            await _browse_cache.put(key, payload)
            return payload, False
    finally:
        await _release_request_lock(key, lock)


async def prewarm_entity_browse() -> None:
    """Best-effort startup warm-up for the default entity-list first page."""
    if (
        os.getenv("ENTITY_BROWSE_PREWARM_ENABLED", "true").lower()
        not in {
            "1",
            "true",
            "yes",
            "on",
        }
        or not _browse_cache.enabled
    ):
        return
    from infra.workflow_mysql import workflow_session_scope

    space = _resolved_space(None)
    try:
        with workflow_session_scope() as session:
            _, hit = await _load_browse_payload(
                session,
                space=space,
                entity_type=None,
                limit=10,
                offset=0,
            )
        logger.info("实体列表默认首页预热完成 space=%s cache_hit=%s", space, hit)
    except Exception:  # noqa: BLE001 - startup warm-up must never block API startup
        logger.warning("实体列表默认首页预热失败，首次请求将按正常路径加载", exc_info=True)


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
    # 跳页框直跳深页：图空间实体量已达十万级（yunfei_test 17.6 万），旧 10 万上限
    # 会让末尾页区间直接 422；放大为千万级护栏，越界页由图侧自然返回空。
    offset: int = Query(0, ge=0, le=10_000_000),
) -> ApiResponse:
    """浏览实体（关键词为空的默认视图）：图空间直查分页，页内按 vid 排序。"""
    space = resolve_selected_space(space)
    _ensure_space_access(actor, space)
    try:
        payload, cache_hit = await _load_browse_payload(
            session,
            space=space,
            entity_type=entityType,
            limit=limit,
            offset=offset,
        )
    except EntitySearchError as exc:
        _raise_domain_error(exc)
    return Response(
        payload,
        media_type="application/json",
        headers={"X-Entity-Cache": "HIT" if cache_hit else "MISS"},
    )


@router.get("/export", response_class=FileResponse)
def export_entities_csv(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    space: str | None = Query(None, max_length=64, description="图空间"),
    entityType: str | None = Query(None, max_length=64, description="实体类型；为空导出全部类型"),
) -> FileResponse:
    """导出所选图空间/类型的全部实体，不受列表分页上限或关键词影响。"""
    space = resolve_selected_space(space)
    _ensure_space_access(actor, space)
    try:
        path = _application(session).export_csv(space=space, entity_type=entityType)
    except EntitySearchError as exc:
        _raise_domain_error(exc)
    return TemporaryCsvResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=f"entities_{entityType or 'all'}.csv",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/types", response_model=ApiResponse)
def list_entity_types(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    space: str | None = Query(None, max_length=64, description="图空间"),
) -> ApiResponse:
    """索引内实体类型 + 数量（前端类型过滤下拉）。"""
    space = resolve_selected_space(space)
    _ensure_space_access(actor, space)
    return ApiResponse(data={"items": _application(session).types(space=space)})


@router.get("/index-status", response_model=ApiResponse)
def get_index_status(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    space: str | None = Query(None, max_length=64, description="图空间"),
) -> ApiResponse:
    """实体索引状态（是否已建、实体数、类型统计、更新时间、是否重建中）。"""
    space = resolve_selected_space(space)
    _ensure_space_access(actor, space)
    return ApiResponse(data=_application(session).status(space=space))


@router.post("/search")
async def search_entities(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: EntitySearchRequest,
) -> Response:
    """实体混合检索：m3e 语义向量 + BM25 关键词（RRF 融合），支持实体类型过滤。

    混合检索为重查询（m3e 向量化 + Milvus + 图直查），同关键词+空间+分页的
    重复检索使用短 TTL 共享缓存（默认 60 秒，可通过环境变量调整）。"""
    payload = payload.model_copy(update={"space": resolve_selected_space(payload.space)})
    _ensure_space_access(actor, payload.space)
    cache_key = build_cache_key(
        "search",
        space=_resolved_space(payload.space),
        entity_type=payload.entityType,
        keyword=payload.keyword,
        limit=payload.limit,
        offset=payload.offset,
    )
    cached = await _search_cache.get(cache_key)
    if cached is not None:
        return Response(
            cached,
            media_type="application/json",
            headers={"X-Entity-Cache": "HIT"},
        )
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
    payload_json = _serialized_success(data)
    await _search_cache.put(cache_key, payload_json)
    return Response(
        payload_json,
        media_type="application/json",
        headers={"X-Entity-Cache": "MISS"},
    )


@router.post("/reindex", response_model=ApiResponse)
async def reindex_entities(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: EntityReindexRequest | None = None,
) -> ApiResponse:
    """全量重建图空间实体 Milvus 索引（管理员）：图 → embedding + BM25 → kg_entity。"""
    from service.business_access_control import ensure_space_access, rbac_enabled

    if not (actor.can_develop if rbac_enabled() else actor.is_admin):
        raise HTTPException(status_code=403, detail="仅平台管理员可以重建实体索引")
    app = _application(session)
    request = payload or EntityReindexRequest()
    request = request.model_copy(update={"space": resolve_selected_space(request.space)})
    if rbac_enabled():
        ensure_space_access(actor, request.space, "write")
    try:
        data = await asyncio.to_thread(
            app.reindex,
            space=request.space,
            entity_types=request.entityTypes,
        )
        await _clear_entity_cache()
        return ApiResponse(data=data, msg="实体索引重建完成")
    except EntitySearchError as exc:
        _raise_domain_error(exc)
