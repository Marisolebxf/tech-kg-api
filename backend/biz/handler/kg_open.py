"""对外图查询：类型目录、按实体类型与关系类型分页查询。"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from biz.dependencies.kg_open_auth import KgOpenAuth
from biz.schemas.common import ApiResponse
from infra.graph_db import get_space_client
from infra.graph_exec_budget import GraphExecOverloaded, graph_exec_slot
from infra.workflow_mysql import get_workflow_session
from service.kg_open import OpenGraphQueries, OpenQueryError

router = APIRouter(prefix="/kg-open", tags=["kg-open"])
logger = logging.getLogger(__name__)
SessionDependency = Annotated[Session, Depends(get_workflow_session)]


def _get_client(space):
    return get_space_client(space)


def _catalog(session: Session, space: str) -> dict:
    from application.schema_management import SchemaManagementApplication

    try:
        return SchemaManagementApplication(session).external_catalog(space)
    except SQLAlchemyError as exc:
        raise OpenQueryError("图谱目录暂时不可用，请稍后重试", 503) from exc


async def _run(ctx, session, operation):
    # 目录与图 I/O 顺序在 worker 中执行，不阻塞事件循环。
    def work():
        catalog = _catalog(session, ctx.space)
        queries = OpenGraphQueries(_get_client(ctx.space), catalog, ctx.space)
        return operation(queries)

    try:
        async with graph_exec_slot():
            data = await asyncio.to_thread(work)
        return ApiResponse(data={"space": ctx.space, **data})
    except OpenQueryError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except GraphExecOverloaded as exc:
        raise HTTPException(
            429, "图查询执行过载，请稍后重试", headers={"Retry-After": "1"}
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kg-open 查询失败")
        raise HTTPException(502, "图数据服务暂时不可用，请稍后重试") from exc


def _with_estimate(queries, data, kind, name):
    stats = queries.stats()
    data.update(total=(stats or {}).get(kind, {}).get(name, -1), totalIsEstimate=True)
    return data


@router.get("/schema")
async def get_open_schema(ctx: KgOpenAuth, session: SessionDependency) -> ApiResponse:
    def query(queries):
        stats = queries.stats()
        for field, kind in (("entityTypes", "tags"), ("relationTypes", "edges")):
            for item in queries.catalog[field]:
                item.update(
                    count=(stats or {}).get(kind, {}).get(item["name"], -1), countIsEstimate=True
                )
        return {**queries.catalog, "statsAvailable": stats is not None}

    return await _run(ctx, session, query)


@router.get("/entity-types/{name}/entities")
async def list_entities_by_type(
    ctx: KgOpenAuth,
    name: str,
    session: SessionDependency,
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000_000),
    cursor: str = Query("", max_length=4096),
) -> ApiResponse:
    def query(queries):
        data = queries.entities(name, limit, cursor, offset)
        data["relationTypes"] = sorted(
            item["name"]
            for item in queries.catalog["relationTypes"]
            if name in item["sourceType"].split("|") or name in item["targetType"].split("|")
        )
        return _with_estimate(queries, data, "tags", name)

    return await _run(ctx, session, query)


@router.get("/relation-types/{name}/edges")
async def list_edges_by_type(
    ctx: KgOpenAuth,
    name: str,
    session: SessionDependency,
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000_000),
    cursor: str = Query("", max_length=4096),
    include_entities: bool = Query(True, alias="includeEntities"),
) -> ApiResponse:
    return await _run(
        ctx,
        session,
        lambda q: _with_estimate(
            q, q.edges(name, limit, cursor, offset, include_entities), "edges", name
        ),
    )
