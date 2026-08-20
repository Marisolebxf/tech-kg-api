"""平台 LLM 配置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from application.llm_config import LlmConfigApplication
from biz.schemas.common import ApiResponse
from biz.schemas.llm_config import LlmConfigCreate, LlmConfigUpdate
from infra.mysql import get_session

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


def _application(session: Session) -> LlmConfigApplication:
    return LlmConfigApplication(session)


@router.get("/llm-configs", response_model=ApiResponse)
def list_llm_configs(session: Annotated[Session, Depends(get_session)]) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs())


@router.get("/llm-configs/{config_id}", response_model=ApiResponse)
def get_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data=data)


@router.post("/llm-configs", response_model=ApiResponse)
def create_llm_config(
    payload: LlmConfigCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).create_config(payload.model_dump())
    return ApiResponse(data=data, msg="LLM 配置已创建")


@router.put("/llm-configs/{config_id}", response_model=ApiResponse)
def update_llm_config(
    config_id: str,
    payload: LlmConfigUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).update_config(config_id, payload.model_dump(exclude_unset=True))
    if data is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data=data, msg="LLM 配置已更新")


@router.delete("/llm-configs/{config_id}", response_model=ApiResponse)
def delete_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data={"deleted": True}, msg="LLM 配置已删除")


@router.post("/llm-configs/{config_id}/set-default", response_model=ApiResponse)
def set_default_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).set_default(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/llm-configs/{config_id}/test", response_model=ApiResponse)
def test_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).test_connection(config_id))
