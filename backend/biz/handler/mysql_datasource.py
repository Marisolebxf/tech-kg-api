"""平台 MySQL 数据源 API。"""

from __future__ import annotations

import json
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from application.mysql_datasource import MysqlDatasourceApplication
from biz.dependencies.auth import CurrentActor
from biz.dependencies.shared_configs import ensure_shared_config_manage, ensure_shared_config_read
from biz.schemas.common import ApiResponse
from biz.schemas.mysql_datasource import MysqlDatasourceCreate, MysqlDatasourceUpdate
from db_model.config_ownership import ConfigOwnership
from infra.mysql import get_session
from service.config_ownership import (
    assigned_config_business,
    config_output,
    ensure_config_access,
    guard_default_change,
    visible_configurations,
)

# 数据源列表为读多写少的轻查询，加短 TTL 响应缓存扛读并发；键含用户身份
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


router = APIRouter(prefix="/mysql-datasources", tags=["mysql-datasource"])


def _application(session: Session) -> MysqlDatasourceApplication:
    return MysqlDatasourceApplication(session)


def _readable_config(
    app: MysqlDatasourceApplication,
    actor: CurrentActor,
    config_id: str,
    session: Session,
    *,
    manage: bool = False,
) -> dict:
    ensure_shared_config_read(actor)
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    ensure_config_access(session, actor, "mysql", config_id, manage=manage)
    return config_output(session, actor, "mysql", data)


@router.get("")
def list_mysql_datasources(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    ensure_shared_config_read(actor)
    owner = None
    cache_key = f"mysql-datasources:{owner}:{actor.user_id}:{actor.is_admin}"
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
            "data": visible_configurations(session, actor, "mysql", configs),
            "msg": "success",
        },
        ensure_ascii=False,
        default=str,
    )
    return Response(payload, media_type="application/json")


@router.get("/{datasource_id}", response_model=ApiResponse)
def get_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_readable_config(_application(session), actor, datasource_id, session))


@router.post("", response_model=ApiResponse)
def create_mysql_datasource(
    payload: MysqlDatasourceCreate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    business_id = assigned_config_business(session, actor)
    _config_cache_clear()
    data = payload.model_dump()
    guard_default_change(actor, data)
    data["owner"] = actor.user_id
    data["_business_id"] = business_id
    result = _application(session).create_config(data, scope_owner=None)
    return ApiResponse(
        data=config_output(session, actor, "mysql", result), msg="MySQL 数据源已创建"
    )


@router.put("/{datasource_id}", response_model=ApiResponse)
def update_mysql_datasource(
    datasource_id: str,
    payload: MysqlDatasourceUpdate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _config_cache_clear()
    current = _readable_config(_application(session), actor, datasource_id, session, manage=True)
    data = payload.model_dump(exclude_unset=True)
    guard_default_change(actor, data, current)
    # Keep historical ownership metadata; it no longer grants configuration access.
    data.pop("owner", None)
    updated = _application(session).update_config(datasource_id, data, scope_owner=None)
    if updated is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(
        data=config_output(session, actor, "mysql", updated), msg="MySQL 数据源已更新"
    )


@router.delete("/{datasource_id}", response_model=ApiResponse)
def delete_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _config_cache_clear()
    _readable_config(_application(session), actor, datasource_id, session, manage=True)
    policy = session.get(ConfigOwnership, ("mysql", datasource_id))
    if policy is not None:
        session.delete(policy)
    ok = _application(session).delete_config(datasource_id)
    if not ok:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data={"deleted": True}, msg="MySQL 数据源已删除")


@router.post("/{datasource_id}/set-default", response_model=ApiResponse)
def set_default_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    ensure_shared_config_manage(actor)
    _config_cache_clear()
    _readable_config(_application(session), actor, datasource_id, session)
    data = _application(session).set_default(datasource_id, scope_owner=None)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=config_output(session, actor, "mysql", data), msg="已设为默认")


@router.post("/{datasource_id}/test", response_model=ApiResponse)
def test_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _readable_config(_application(session), actor, datasource_id, session, manage=True)
    return ApiResponse(data=_application(session).test_connection(datasource_id))


@router.get("/{datasource_id}/databases", response_model=ApiResponse)
def list_mysql_databases(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _readable_config(_application(session), actor, datasource_id, session)
    return ApiResponse(data={"items": _application(session).list_databases(datasource_id)})


@router.get("/{datasource_id}/tables", response_model=ApiResponse)
def list_mysql_tables(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
    database: Annotated[str | None, Query(max_length=128)] = None,
) -> ApiResponse:
    """列出指定库（缺省为数据源默认库）的表，供 Schema 来源表绑定选择。"""
    _readable_config(_application(session), actor, datasource_id, session)
    return ApiResponse(data={"items": _application(session).list_tables(datasource_id, database)})


@router.get("/{datasource_id}/tables/{table_name}/columns", response_model=ApiResponse)
def list_mysql_table_columns(
    datasource_id: str,
    table_name: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
    database: Annotated[str | None, Query(max_length=128)] = None,
) -> ApiResponse:
    """列出指定表的列，供选主键列/时间列。"""
    _readable_config(_application(session), actor, datasource_id, session)
    return ApiResponse(
        data={"items": _application(session).list_columns(datasource_id, table_name, database)}
    )
