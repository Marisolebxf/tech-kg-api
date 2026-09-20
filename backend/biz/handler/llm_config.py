"""平台 LLM 配置 API。"""

from __future__ import annotations

import json
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from application.llm_config import LlmConfigApplication
from biz.dependencies.auth import CurrentActor
from biz.dependencies.resources import ensure_owner_access, resource_owner_filter
from biz.schemas.common import ApiResponse
from biz.schemas.llm_config import LlmConfigCreate, LlmConfigUpdate, LlmConfigVerifyRequest
from infra.mysql import get_session

LLM_CONFIG_NOT_FOUND = "LLM 配置不存在"


# 配置列表为读多写少的轻查询，加短 TTL 响应缓存扛读并发；键含用户身份
# （列表按 owner 隔离：管理员全量/普通用户仅自己），不会跨用户串数据。
# 配置创建/更新/删除后缓存最长 15s 内滞后。TTL 环境变量 CONFIG_CACHE_SECONDS 可调，0=关闭。
_CONFIG_CACHE_SECONDS = float(os.getenv("CONFIG_CACHE_SECONDS", "15"))
_config_payload_cache: dict[str, tuple[float, str]] = {}


def _config_cache_get(key: str) -> str | None:
    entry = _config_payload_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _config_cache_put(key: str, payload: str) -> None:
    if len(_config_payload_cache) > 512:
        now = time.monotonic()
        for stale in [k for k, v in _config_payload_cache.items() if v[0] <= now]:
            _config_payload_cache.pop(stale, None)
    _config_payload_cache[key] = (time.monotonic() + _CONFIG_CACHE_SECONDS, payload)


def _config_cache_clear() -> None:
    _config_payload_cache.clear()


router = APIRouter(prefix="/llm-config", tags=["llm-config"])


def _application(session: Session) -> LlmConfigApplication:
    return LlmConfigApplication(session)


def _owned_config(app: LlmConfigApplication, actor: CurrentActor, config_id: str) -> dict:
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    ensure_owner_access(actor, data.get("owner", ""))
    return data


@router.get("/llm-configs")
def list_llm_configs(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    owner = resource_owner_filter(actor)
    cache_key = f"llm-configs:{owner}:{actor.user_id}:{actor.is_admin}"
    cached = _config_cache_get(cache_key)
    if cached is not None:
        return Response(cached, media_type="application/json")
    payload = json.dumps(
        {
            "code": 200,
            "success": True,
            "data": _application(session).list_configs(owner=owner),
            "msg": "success",
        },
        ensure_ascii=False,
        default=str,
    )
    _config_cache_put(cache_key, payload)
    return Response(payload, media_type="application/json")


@router.get("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def get_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    ensure_owner_access(actor, data.get("owner", ""))
    return ApiResponse(data=data)


@router.post("/llm-configs")
def create_llm_config(
    payload: LlmConfigCreate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = payload.model_dump()
    data["owner"] = actor.user_id if not actor.is_admin else (data.get("owner") or actor.user_id)
    result = _application(session).create_config(data, scope_owner=resource_owner_filter(actor))
    _config_cache_clear()
    return ApiResponse(data=result, msg="LLM 配置已创建")


@router.put("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
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
    updated = _application(session).update_config(
        config_id, data, scope_owner=resource_owner_filter(actor)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    _config_cache_clear()
    return ApiResponse(data=updated, msg="LLM 配置已更新")


@router.delete("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def delete_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    ok = _application(session).delete_config(config_id)
    if not ok:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    _config_cache_clear()
    return ApiResponse(data={"deleted": True}, msg="LLM 配置已删除")


@router.post(
    "/llm-configs/{config_id}/set-default", responses={404: {"description": "请求的资源不存在"}}
)
def set_default_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, config_id)
    data = _application(session).set_default(config_id, scope_owner=resource_owner_filter(actor))
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    _config_cache_clear()
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/llm-configs/{config_id}/test")
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
