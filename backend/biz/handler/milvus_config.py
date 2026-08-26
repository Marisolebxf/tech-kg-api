"""平台 Milvus 配置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from application.milvus_config import MilvusConfigApplication
from biz.schemas.common import ApiResponse
from biz.schemas.milvus_config import MilvusConfigCreate, MilvusConfigUpdate
from infra.mysql import get_session

router = APIRouter(prefix="/milvus-configs", tags=["milvus-config"])


def _application(session: Session) -> MilvusConfigApplication:
    return MilvusConfigApplication(session)


@router.get("", response_model=ApiResponse)
def list_milvus_configs(session: Annotated[Session, Depends(get_session)]) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs())


@router.get("/{config_id}", response_model=ApiResponse)
def get_milvus_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Milvus 配置不存在")
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse)
def create_milvus_config(
    payload: MilvusConfigCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).create_config(payload.model_dump())
    return ApiResponse(data=data, msg="Milvus 配置已创建")


@router.put("/{config_id}", response_model=ApiResponse)
def update_milvus_config(
    config_id: str,
    payload: MilvusConfigUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).update_config(config_id, payload.model_dump(exclude_unset=True))
    if data is None:
        raise HTTPException(status_code=404, detail="Milvus 配置不存在")
    return ApiResponse(data=data, msg="Milvus 配置已更新")


@router.delete("/{config_id}", response_model=ApiResponse)
def delete_milvus_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Milvus 配置不存在")
    return ApiResponse(data={"deleted": True}, msg="Milvus 配置已删除")


@router.post("/{config_id}/set-default", response_model=ApiResponse)
def set_default_milvus_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).set_default(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Milvus 配置不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/{config_id}/test", response_model=ApiResponse)
def test_milvus_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).test_connection(config_id))


@router.get("/{config_id}/databases", response_model=ApiResponse)
def list_milvus_databases(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data={"items": _application(session).list_databases(config_id)})
