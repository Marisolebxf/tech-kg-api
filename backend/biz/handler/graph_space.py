"""图空间 API：列出（按用户隔离）、创建（真实 CREATE SPACE）、绑定/解绑。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from biz.dependencies.auth import CurrentActor
from biz.schemas.common import ApiResponse
from infra.mysql import get_session
from service.graph_space import GraphSpaceError, GraphSpaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph-spaces", tags=["graph-space"])


class GraphSpaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


def _service(session: Session) -> GraphSpaceService:
    return GraphSpaceService(session)


def _to_response(exc: GraphSpaceError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=ApiResponse)
def list_graph_spaces(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data={"items": _service(session).list_spaces_for_actor(actor)})


@router.post("", response_model=ApiResponse)
def create_graph_space(
    payload: GraphSpaceCreateRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        data = _service(session).create_space(actor, payload.name)
    except GraphSpaceError as exc:
        raise _to_response(exc) from exc
    return ApiResponse(data=data, msg="图空间已创建并绑定")


@router.post("/{space_name}/bind", response_model=ApiResponse)
def bind_graph_space(
    space_name: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    try:
        data = _service(session).bind(actor, space_name)
    except GraphSpaceError as exc:
        raise _to_response(exc) from exc
    return ApiResponse(data=data, msg="图空间已绑定")


@router.delete("/{space_name}", response_model=ApiResponse)
def unbind_graph_space(
    space_name: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    if not _service(session).unbind(actor, space_name):
        raise HTTPException(status_code=404, detail="未绑定该图空间")
    return ApiResponse(data={"unbound": True}, msg="已解除绑定（图空间数据保留）")
