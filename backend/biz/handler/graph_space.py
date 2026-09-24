"""图空间 API：列出（按用户隔离）、创建（真实 CREATE SPACE）、绑定/解绑。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from biz.dependencies.auth import CurrentActor, CurrentAdmin
from biz.schemas.common import ApiResponse
from infra.mysql import get_session
from service.graph_space import GraphSpaceError, GraphSpaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph-spaces", tags=["graph-space"])
# 顶栏图空间选择器对所有登录用户可用：仅空间列表（普通用户按可工作空间收敛），
# 创建/绑定/删除仍走管理端路由组。
readonly_router = APIRouter(prefix="/graph-spaces", tags=["graph-space-readonly"])


class GraphSpaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


def _service(session: Session) -> GraphSpaceService:
    return GraphSpaceService(session)


def _require_legacy_binding() -> None:
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        raise HTTPException(409, "图空间归属由管理员通过业务绑定 SQL 配置")


def _to_response(exc: GraphSpaceError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=ApiResponse)
def list_graph_spaces(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data={"items": _service(session).list_spaces_for_actor(actor)})


readonly_router.get("", response_model=ApiResponse)(list_graph_spaces)


@router.post("", response_model=ApiResponse)
def create_graph_space(
    payload: GraphSpaceCreateRequest,
    actor: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        data = _service(session).create_space(actor, payload.name)
    except GraphSpaceError as exc:
        raise _to_response(exc) from exc
    return ApiResponse(data=data, msg="图空间已创建，业务归属请由管理员核实配置")


@router.post("/{space_name}/bind", response_model=ApiResponse)
def bind_graph_space(
    space_name: str,
    actor: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _require_legacy_binding()
    try:
        data = _service(session).bind(actor, space_name)
    except GraphSpaceError as exc:
        raise _to_response(exc) from exc
    return ApiResponse(data=data, msg="图空间已绑定")


@router.delete("/{space_name}", response_model=ApiResponse)
def unbind_graph_space(
    space_name: str,
    actor: CurrentAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _require_legacy_binding()
    if not _service(session).unbind(actor, space_name):
        raise HTTPException(status_code=404, detail="未绑定该图空间")
    return ApiResponse(data={"unbound": True}, msg="已解除绑定（图空间数据保留）")
