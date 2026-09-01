"""平台 MySQL 数据源 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from application.mysql_datasource import MysqlDatasourceApplication
from biz.dependencies.auth import CurrentActor
from biz.dependencies.resources import ensure_owner_access, resource_owner_filter
from biz.schemas.common import ApiResponse
from biz.schemas.mysql_datasource import MysqlDatasourceCreate, MysqlDatasourceUpdate
from infra.mysql import get_session

router = APIRouter(prefix="/mysql-datasources", tags=["mysql-datasource"])


def _application(session: Session) -> MysqlDatasourceApplication:
    return MysqlDatasourceApplication(session)


def _owned_config(app: MysqlDatasourceApplication, actor: CurrentActor, config_id: str) -> dict:
    data = app.get_config(config_id)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    ensure_owner_access(actor, data.get("owner", ""))
    return data


@router.get("", response_model=ApiResponse)
def list_mysql_datasources(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs(owner=resource_owner_filter(actor)))


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
    data = payload.model_dump()
    data["owner"] = actor.user_id if not actor.is_admin else (data.get("owner") or actor.user_id)
    result = _application(session).create_config(data)
    return ApiResponse(data=result, msg="MySQL 数据源已创建")


@router.put("/{datasource_id}", response_model=ApiResponse)
def update_mysql_datasource(
    datasource_id: str,
    payload: MysqlDatasourceUpdate,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    _owned_config(_application(session), actor, datasource_id)
    data = payload.model_dump(exclude_unset=True)
    if not actor.is_admin:
        data.pop("owner", None)
    updated = _application(session).update_config(datasource_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=updated, msg="MySQL 数据源已更新")


@router.delete("/{datasource_id}", response_model=ApiResponse)
def delete_mysql_datasource(
    datasource_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
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
    _owned_config(_application(session), actor, datasource_id)
    data = _application(session).set_default(datasource_id)
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
