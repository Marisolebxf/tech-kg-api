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
from biz.dependencies.shared_configs import ensure_shared_config_read
from biz.schemas.common import ApiResponse
from biz.schemas.llm_config import LlmConfigCreate, LlmConfigUpdate, LlmConfigVerifyRequest
from db_model.config_ownership import ConfigOwnership
from infra.mysql import get_session
from service.config_ownership import (
    assigned_config_business,
    config_output,
    ensure_config_access,
    guard_default_change,
    visible_configurations,
)
from service.llm_defaults import decorate_defaults, set_default_for_actor

LLM_CONFIG_NOT_FOUND = "LLM 配置不存在"


# 配置列表为读多写少的轻查询，加短 TTL 响应缓存扛读并发；键含用户身份
# 缓存仅保存脱敏配置原始数据；每次返回前重新校验业务归属，不缓存授权结果。
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


def _readable_config(
    app: LlmConfigApplication,
    actor: CurrentActor,
    config_id: str,
    session: Session,
    *,
    manage: bool = False,
) -> dict:
    ensure_shared_config_read(actor)
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    ensure_config_access(session, actor, "llm", config_id, manage=manage)
    return decorate_defaults(session, actor, [config_output(session, actor, "llm", data)])[0]


@router.get("/llm-configs")
def list_llm_configs(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    ensure_shared_config_read(actor)
    owner = None
    cache_key = f"llm-configs:{owner}:{actor.user_id}:{actor.is_admin}"
    from service.business_access_control import rbac_enabled

    cached = None if rbac_enabled() or not actor.is_admin else _config_cache_get(cache_key)
    configs = (
        json.loads(cached)
        if cached is not None
        else _application(session).list_configs(owner=owner)
    )
    if cached is None:
        _config_cache_put(cache_key, json.dumps(configs, ensure_ascii=False, default=str))
    payload = json.dumps(
        {
            "code": 200,
            "success": True,
            "data": decorate_defaults(
                session, actor, visible_configurations(session, actor, "llm", configs)
            ),
            "msg": "success",
        },
        ensure_ascii=False,
        default=str,
    )
    return Response(payload, media_type="application/json")


@router.get("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def get_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_readable_config(_application(session), actor, config_id, session))


@router.post("/llm-configs")
def create_llm_config(
    payload: LlmConfigCreate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    business_id = assigned_config_business(session, actor)
    data = payload.model_dump()
    guard_default_change(actor, data)
    data["owner"] = actor.user_id
    data["_business_id"] = business_id
    result = _application(session).create_config(data, scope_owner=None)
    _config_cache_clear()
    return ApiResponse(
        data=decorate_defaults(session, actor, [config_output(session, actor, "llm", result)])[0],
        msg="LLM 配置已创建",
    )


@router.put("/llm-configs/{config_id}", responses={404: {"description": "请求的资源不存在"}})
def update_llm_config(
    config_id: str,
    payload: LlmConfigUpdate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _readable_config(_application(session), actor, config_id, session, manage=True)
    data = payload.model_dump(exclude_unset=True)
    guard_default_change(actor, data)
    if not actor.is_admin:
        data.pop("is_default", None)
    # Keep historical ownership metadata; it no longer grants configuration access.
    data.pop("owner", None)
    updated = _application(session).update_config(config_id, data, scope_owner=None)
    if updated is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    _config_cache_clear()
    return ApiResponse(
        data=decorate_defaults(session, actor, [config_output(session, actor, "llm", updated)])[0],
        msg="LLM 配置已更新",
    )


@router.delete(
    "/llm-configs/{config_id}",
    responses={404: {"description": "请求的资源不存在"}, 409: {"description": "默认配置不可删除"}},
)
def delete_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    config = _readable_config(_application(session), actor, config_id, session, manage=True)
    # 默认必须恒有一条：删掉当前默认会让"全都不是默认"，LLM 只能回退 env——先转移默认再删
    if config.get("defaultReferenced"):
        raise HTTPException(status_code=409, detail="默认配置不能删除：请先将其他配置设为默认")
    policy = session.get(ConfigOwnership, ("llm", config_id))
    if policy is not None:
        session.delete(policy)
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
    _readable_config(_application(session), actor, config_id, session)
    set_default_for_actor(session, actor, config_id)
    data = _application(session).get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail=LLM_CONFIG_NOT_FOUND)
    _config_cache_clear()
    return ApiResponse(
        data=decorate_defaults(session, actor, [config_output(session, actor, "llm", data)])[0],
        msg="已设为默认",
    )


@router.post("/llm-configs/{config_id}/test")
def test_llm_config(
    config_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _readable_config(_application(session), actor, config_id, session, manage=True)
    return ApiResponse(data=_application(session).test_connection(config_id))


@router.post("/llm-configs/verify", response_model=ApiResponse)
def verify_llm_config(
    payload: LlmConfigVerifyRequest,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    """新建弹窗保存前验证：直接用未落库的 baseUrl/model/apiKey 探活。"""
    assigned_config_business(session, actor)
    result = _application(session).verify_connection(
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
    )
    return ApiResponse(data=result)
