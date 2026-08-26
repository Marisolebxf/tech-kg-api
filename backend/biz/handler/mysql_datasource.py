"""平台 MySQL 数据源 API。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from application.mysql_datasource import MysqlDatasourceApplication
from biz.schemas.common import ApiResponse
from biz.schemas.mysql_datasource import MysqlDatasourceCreate, MysqlDatasourceUpdate
from infra.mysql import get_session

router = APIRouter(prefix="/mysql-datasources", tags=["mysql-datasource"])


def _application(session: Session) -> MysqlDatasourceApplication:
    return MysqlDatasourceApplication(session)


@router.get("", response_model=ApiResponse)
def list_mysql_datasources(session: Annotated[Session, Depends(get_session)]) -> ApiResponse:
    return ApiResponse(data=_application(session).list_configs())


@router.get("/{datasource_id}", response_model=ApiResponse)
def get_mysql_datasource(
    datasource_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).get_config(datasource_id)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse)
def create_mysql_datasource(
    payload: MysqlDatasourceCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).create_config(payload.model_dump())
    return ApiResponse(data=data, msg="MySQL 数据源已创建")


@router.put("/{datasource_id}", response_model=ApiResponse)
def update_mysql_datasource(
    datasource_id: str,
    payload: MysqlDatasourceUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).update_config(
        datasource_id, payload.model_dump(exclude_unset=True)
    )
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=data, msg="MySQL 数据源已更新")


@router.delete("/{datasource_id}", response_model=ApiResponse)
def delete_mysql_datasource(
    datasource_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    ok = _application(session).delete_config(datasource_id)
    if not ok:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data={"deleted": True}, msg="MySQL 数据源已删除")


@router.post("/{datasource_id}/set-default", response_model=ApiResponse)
def set_default_mysql_datasource(
    datasource_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    data = _application(session).set_default(datasource_id)
    if data is None:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return ApiResponse(data=data, msg="已设为默认")


@router.post("/{datasource_id}/test", response_model=ApiResponse)
def test_mysql_datasource(
    datasource_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data=_application(session).test_connection(datasource_id))


@router.get("/{datasource_id}/databases", response_model=ApiResponse)
def list_mysql_databases(
    datasource_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ApiResponse:
    return ApiResponse(data={"items": _application(session).list_databases(datasource_id)})
