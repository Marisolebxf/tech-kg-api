"""Schema 管理 API。"""

from __future__ import annotations

from typing import Annotated, TypeVar
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from application.schema_management import SchemaManagementApplication
from biz.schemas.common import ApiResponse
from biz.schemas.schema_management import EntitySchemaCreate, RelationSchemaCreate
from infra.mysql import get_session
from service.schema_management import (
    SchemaConflictError,
    SchemaManagementError,
    SchemaNotFoundError,
    SchemaPermissionError,
    SchemaScriptError,
    SchemaStorageError,
    max_script_bytes,
)

router = APIRouter(prefix="/schema-management", tags=["schema-management"])
PayloadT = TypeVar("PayloadT", bound=BaseModel)


def _application(session: Session) -> SchemaManagementApplication:
    return SchemaManagementApplication(session)


def _parse_metadata(raw: str, model: type[PayloadT]) -> PayloadT:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        errors = [
            {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=errors) from exc


def _read_script(script: UploadFile) -> bytes:
    return script.file.read(max_script_bytes() + 1)


def _raise_domain_error(exc: SchemaManagementError) -> None:
    if isinstance(exc, SchemaNotFoundError):
        status_code = 404
    elif isinstance(exc, SchemaPermissionError):
        status_code = 403
    elif isinstance(exc, SchemaConflictError):
        status_code = 409
    elif isinstance(exc, SchemaScriptError):
        status_code = 400
    elif isinstance(exc, SchemaStorageError):
        status_code = 502
    else:
        status_code = 400
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/overview", response_model=ApiResponse)
def get_schema_overview(session: Annotated[Session, Depends(get_session)]) -> ApiResponse:
    return ApiResponse(data=_application(session).overview())


@router.get("/schemas", response_model=ApiResponse)
def list_schemas(
    session: Annotated[Session, Depends(get_session)],
    kind: Annotated[str | None, Query(pattern="^(entity|relation)$")] = None,
    keyword: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    include_details: Annotated[bool, Query(alias="includeDetails")] = False,
    user_id: Annotated[str | None, Header(alias="X-User-Id", max_length=128)] = None,
) -> ApiResponse:
    data = _application(session).list_schemas(
        kind=kind,
        keyword=keyword.strip() if keyword else None,
        page=page,
        page_size=page_size,
        user_id=user_id,
        include_details=include_details,
    )
    return ApiResponse(data=data)


@router.get("/schemas/topology", response_model=ApiResponse)
def get_schema_topology(
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str | None, Header(alias="X-User-Id", max_length=128)] = None,
) -> ApiResponse:
    return ApiResponse(data=_application(session).topology(user_id))


@router.get("/schemas/{schema_id}", response_model=ApiResponse)
def get_schema_detail(
    schema_id: str,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str | None, Header(alias="X-User-Id", max_length=128)] = None,
) -> ApiResponse:
    try:
        return ApiResponse(data=_application(session).get_schema(schema_id, user_id))
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/entities", response_model=ApiResponse, status_code=201)
def create_entity_schema(
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
    metadata: Annotated[str, Form(...)],
    script: Annotated[UploadFile, File(...)],
) -> ApiResponse:
    payload = _parse_metadata(metadata, EntitySchemaCreate)
    try:
        data = _application(session).create_entity(
            payload=payload.model_dump(),
            user_id=user_id,
            filename=script.filename or "",
            content_type=script.content_type,
            script_data=_read_script(script),
        )
        return ApiResponse(data=data, msg="实体 Schema 创建成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/relations", response_model=ApiResponse, status_code=201)
def create_relation_schema(
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
    metadata: Annotated[str, Form(...)],
    script: Annotated[UploadFile, File(...)],
) -> ApiResponse:
    payload = _parse_metadata(metadata, RelationSchemaCreate)
    try:
        data = _application(session).create_relation(
            payload=payload.model_dump(),
            user_id=user_id,
            filename=script.filename or "",
            content_type=script.content_type,
            script_data=_read_script(script),
        )
        return ApiResponse(data=data, msg="关系 Schema 创建成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.delete("/schemas/{schema_id}", response_model=ApiResponse)
def delete_schema(
    schema_id: str,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
) -> ApiResponse:
    try:
        data = _application(session).delete_schema(schema_id, user_id)
        return ApiResponse(data=data, msg="Schema 删除成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.put("/schemas/{schema_id}/script", response_model=ApiResponse)
def replace_schema_script(
    schema_id: str,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
    script: Annotated[UploadFile, File(...)],
) -> ApiResponse:
    try:
        data = _application(session).replace_script(
            schema_id=schema_id,
            user_id=user_id,
            filename=script.filename or "",
            content_type=script.content_type,
            script_data=_read_script(script),
        )
        return ApiResponse(data=data, msg="Schema 脚本上传成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.get("/schemas/{schema_id}/script")
def download_schema_script(
    schema_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    try:
        script, body = _application(session).get_script(schema_id)
    except SchemaManagementError as exc:
        _raise_domain_error(exc)
    encoded_filename = quote(script.original_filename)
    return StreamingResponse(
        body.iter_chunks(chunk_size=64 * 1024),
        media_type=script.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(script.size_bytes),
            "X-Content-SHA256": script.sha256,
        },
        background=BackgroundTask(body.close),
    )
