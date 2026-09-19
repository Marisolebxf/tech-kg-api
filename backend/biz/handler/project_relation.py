"""项目关系对外业务接口。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from application.project_relation import ProjectRelationApplication
from biz.dependencies.auth import CurrentActor
from biz.schemas.common import ApiResponse
from biz.schemas.project_relation import ProjectRelationQueryRequest
from infra.graph_db import get_trs_graph_client
from service.project_relation import InvalidCursorError

router = APIRouter(prefix="/kg-service/project-relations", tags=["project-relations"])
logger = logging.getLogger(__name__)


@router.post("/query", response_model=ApiResponse)
async def query_project_relations(
    body: ProjectRelationQueryRequest,
    actor: CurrentActor,
) -> ApiResponse:
    """分页查询默认正式图空间中的项目出边关系。"""
    del actor
    try:
        application = ProjectRelationApplication(get_trs_graph_client())
        data = await asyncio.to_thread(application.query, body)
        return ApiResponse(data=data.model_dump())
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("项目关系查询失败")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="图数据服务暂时不可用，请稍后重试",
        ) from exc
