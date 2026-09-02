"""平台 LLM 配置 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from application.llm_config import LlmConfigApplication
from biz.dependencies.auth import CurrentActor
from biz.dependencies.resources import ensure_owner_access, resource_owner_filter
from biz.schemas.common import ApiResponse
from biz.schemas.llm_config import LlmConfigCreate, LlmConfigUpdate, LlmConfigVerifyRequest
from infra.mysql import get_session

router = APIRouter(prefix="/llm-config", tags=["llm-config"])


def _application(session: Session) -> LlmConfigApplication:
    return LlmConfigApplication(session)


def _owned_config(app: LlmConfigApplication, actor: CurrentActor, config_id: str) -> dict:
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return data


@router.get("/llm-configs", response_model=ApiResponse)
def list_llm_configs(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs(owner=resource_owner_filter(actor)))


@router.get("/llm-configs/{config_id}", response_model=ApiResponse)
def get_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return ApiResponse(data=data)


@router.post("/llm-configs", response_model=ApiResponse)
def create_llm_config(
    payload: LlmConfigCreate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = payload.model_dump()
    data["owner"] = actor.user_id if not actor.is_admin else (data.get("owner") or actor.user_id)
    result = _application(session).create_config(data)
    return ApiResponse(data=result, msg="LLM 配置已创建")


@router.put("/llm-configs/{config_id}", response_model=ApiResponse)
def update_llm_config(
    config_id: str,
    payload: LlmConfigUpdate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    data = payload.model_dump(exclude_unset=True)
    if not actor.is_admin:
        data.pop("owner", None)
    updated = _application(session).update_config(config_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data=updated, msg="LLM 配置已更新")


@router.delete("/llm-configs/{config_id}", response_model=ApiResponse)
def delete_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data={"deleted": True}, msg="LLM 配置已删除")


@router.post("/llm-configs/{config_id}/set-default", response_model=ApiResponse)
def set_default_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    data = _application(session).set_default(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="LLM 配置不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/llm-configs/{config_id}/test", response_model=ApiResponse)
def test_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    return ApiResponse(data=_application(session).test_connection(config_id))


@router.post("/llm-configs/verify", response_model=ApiResponse)
def verify_llm_config(
    payload: LlmConfigVerifyRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    """新建弹窗保存前验证：直接用未落库的 baseUrl/model/apiKey 探活。"""
    result = _application(session).verify_connection(
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
    )
    return ApiResponse(data=result)
