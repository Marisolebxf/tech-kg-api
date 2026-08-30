"""平台 embedding 模型配置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from application.embedding_config import EmbeddingConfigApplication
from biz.dependencies.auth import CurrentActor
from biz.dependencies.resources import ensure_owner_access, resource_owner_filter
from biz.schemas.common import ApiResponse
from biz.schemas.embedding_config import EmbeddingConfigCreate, EmbeddingConfigUpdate
from infra.mysql import get_session

router = APIRouter(prefix="/embedding-config", tags=["embedding-config"])


def _application(session: Session) -> EmbeddingConfigApplication:
    return EmbeddingConfigApplication(session)


def _owned_config(app: EmbeddingConfigApplication, actor: CurrentActor, config_id: str) -> dict:
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return data


@router.get("", response_model=ApiResponse)
def list_embedding_configs(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs(owner=resource_owner_filter(actor)))


@router.get("/{config_id}", response_model=ApiResponse)
def get_embedding_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse)
def create_embedding_config(
    payload: EmbeddingConfigCreate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = payload.model_dump()
    data["owner"] = actor.user_id if not actor.is_admin else (data.get("owner") or actor.user_id)
    result = _application(session).create_config(data)
    return ApiResponse(data=result, msg="embedding 配置已创建")


@router.put("/{config_id}", response_model=ApiResponse)
def update_embedding_config(
    config_id: str,
    payload: EmbeddingConfigUpdate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    data = payload.model_dump(exclude_unset=True)
    if not actor.is_admin:
        data.pop("owner", None)
    updated = _application(session).update_config(config_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data=updated, msg="embedding 配置已更新")


@router.delete("/{config_id}", response_model=ApiResponse)
def delete_embedding_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data={"deleted": True}, msg="embedding 配置已删除")


@router.post("/{config_id}/set-default", response_model=ApiResponse)
def set_default_embedding_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    data = _application(session).set_default(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/{config_id}/test", response_model=ApiResponse)
def test_embedding_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    return ApiResponse(data=_application(session).test_connection(config_id))
