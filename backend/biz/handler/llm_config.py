"""平台 LLM 配置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from application.llm_config import LlmConfigApplication
from biz.handler import get_cache
from biz.schemas.common import ApiResponse
from biz.schemas.llm_config import LlmConfigCreate, LlmConfigUpdate
from infra.mysql import get_session

LLM_CONFIG_NOT_FOUND = "LLM 配置不存在"

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


def _application(session: Session) -> LlmConfigApplication:
    return LlmConfigApplication(session)


@router.get("/llm-configs")
def list_llm_configs(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> Response:
    cached = get_cache.try_get("llm-config:list", request)
    if cached is not None:
        return cached
    return get_cache.store(
        "llm-config:list",
        request,
        ApiResponse(data=_application(session).list_configs()).model_dump(),
    )


@router.get("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def get_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    return ApiResponse(data=data)


@router.post("/llm-configs")
def create_llm_config(
    payload: LlmConfigCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).create_config(payload.model_dump())
    get_cache.invalidate("llm-config:list")
    return ApiResponse(data=data, msg="LLM 配置已创建")


@router.put("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def update_llm_config(
    config_id: str,
    payload: LlmConfigUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).update_config(config_id, payload.model_dump(exclude_unset=True))
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    get_cache.invalidate("llm-config:list")
    return ApiResponse(data=data, msg="LLM 配置已更新")


@router.delete("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def delete_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    get_cache.invalidate("llm-config:list")
    return ApiResponse(data={"deleted": True}, msg="LLM 配置已删除")


@router.post(
    "/llm-configs/{config_id}/set-default", responses={404: {"description": "请求的资源不存在"}}
)
def set_default_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).set_default(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    get_cache.invalidate("llm-config:list")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/llm-configs/{config_id}/test")
def test_llm_config(
    config_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).test_connection(config_id))
