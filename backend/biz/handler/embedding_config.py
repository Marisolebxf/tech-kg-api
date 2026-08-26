"""平台 embedding 模型配置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from application.embedding_config import EmbeddingConfigApplication
from biz.schemas.common import ApiResponse
from biz.schemas.embedding_config import EmbeddingConfigCreate, EmbeddingConfigUpdate
from infra.mysql import get_session

router = APIRouter(prefix="/embedding-config", tags=["embedding-config"])


def _application(session: Session) -> EmbeddingConfigApplication:
    return EmbeddingConfigApplication(session)


@router.get("", response_model=ApiResponse)
def list_embedding_configs(session: Annotated[Session, Depends(get_session)]) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs())


@router.get("/{config_id}", response_model=ApiResponse)
def get_embedding_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse)
def create_embedding_config(
    payload: EmbeddingConfigCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).create_config(payload.model_dump())
    return ApiResponse(data=data, msg="embedding 配置已创建")


@router.put("/{config_id}", response_model=ApiResponse)
def update_embedding_config(
    config_id: str,
    payload: EmbeddingConfigUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).update_config(config_id, payload.model_dump(exclude_unset=True))
    if data is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data=data, msg="embedding 配置已更新")


@router.delete("/{config_id}", response_model=ApiResponse)
def delete_embedding_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data={"deleted": True}, msg="embedding 配置已删除")


@router.post("/{config_id}/set-default", response_model=ApiResponse)
def set_default_embedding_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).set_default(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="embedding 配置不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/{config_id}/test", response_model=ApiResponse)
def test_embedding_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).test_connection(config_id))
