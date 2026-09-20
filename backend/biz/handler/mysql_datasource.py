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
from biz.dependencies.resources import ensure_owner_access, resource_owner_filter
from biz.schemas.common import ApiResponse
from biz.schemas.mysql_datasource import MysqlDatasourceCreate, MysqlDatasourceUpdate
from infra.mysql import get_session

# 数据源列表为读多写少的轻查询，加短 TTL 响应缓存扛读并发；键含用户身份
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


router = APIRouter(prefix="/mysql-datasources", tags=["mysql-datasource"])


def _application(session: Session) -> MysqlDatasourceApplication:
    return MysqlDatasourceApplication(session)


def _owned_config(app: MysqlDatasourceApplication, actor: CurrentActor, config_id: str) -> dict:
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return data


@router.get("")
def list_mysql_datasources(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    owner = resource_owner_filter(actor)
    cache_key = f"mysql-datasources:{owner}:{actor.user_id}:{actor.is_admin}"
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


@router.get("/{datasource_id}", response_model=ApiResponse)
def get_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(datasource_id)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse)
def create_mysql_datasource(
    payload: MysqlDatasourceCreate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _config_cache_clear()
    data = payload.model_dump()
    data["owner"] = actor.user_id if not actor.is_admin else (data.get("owner") or actor.user_id)
    result = _application(session).create_config(data, scope_owner=resource_owner_filter(actor))
    return ApiResponse(data=result, msg="MySQL 数据源已创建")


@router.put("/{datasource_id}", response_model=ApiResponse)
def update_mysql_datasource(
    datasource_id: str,
    payload: MysqlDatasourceUpdate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _config_cache_clear()
    _owned_config(_application(session), actor, datasource_id)
    data = payload.model_dump(exclude_unset=True)
    if not actor.is_admin:
        data.pop("owner", None)
    updated = _application(session).update_config(
        datasource_id, data, scope_owner=resource_owner_filter(actor)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=updated, msg="MySQL 数据源已更新")


@router.delete("/{datasource_id}", response_model=ApiResponse)
def delete_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _config_cache_clear()
    _owned_config(_application(session), actor, datasource_id)
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
    _config_cache_clear()
    _owned_config(_application(session), actor, datasource_id)
    data = _application(session).set_default(
        datasource_id, scope_owner=resource_owner_filter(actor)
    )
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/{datasource_id}/test", response_model=ApiResponse)
def test_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, datasource_id)
    return ApiResponse(data=_application(session).test_connection(datasource_id))


@router.get("/{datasource_id}/databases", response_model=ApiResponse)
def list_mysql_databases(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, datasource_id)
    return ApiResponse(data={"items": _application(session).list_databases(datasource_id)})


@router.get("/{datasource_id}/tables", response_model=ApiResponse)
def list_mysql_tables(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
    database: Annotated[str | None, Query(max_length=128)] = None,
) -> ApiResponse:
    """列出指定库（缺省为数据源默认库）的表，供 Schema 来源表绑定选择。"""
    _owned_config(_application(session), actor, datasource_id)
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
    _owned_config(_application(session), actor, datasource_id)
    return ApiResponse(
        data={"items": _application(session).list_columns(datasource_id, table_name, database)}
    )
