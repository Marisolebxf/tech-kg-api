"""Schema 管理 API。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, TypeVar
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker
from starlette.background import BackgroundTask

from application.schema_management import SchemaManagementApplication
from biz.schemas.common import ApiResponse
from biz.schemas.schema_management import (
    EntitySchemaCreate,
    RelationSchemaCreate,
    SchemaExecuteRequest,
)
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


def _run_validation_background(validation_id: str, session_factory, storage) -> None:
    with session_factory() as session:
        SchemaManagementApplication(session, storage=storage).run_script_validation(validation_id)


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


@router.post("/script-validations", response_model=ApiResponse, status_code=202)
def start_script_validation(
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
    operation: Annotated[str, Form(pattern="^(replace|create_entity|create_relation)$")],
    script: Annotated[UploadFile, File(...)],
    schema_id: Annotated[str | None, Form(alias="schemaId", max_length=36)] = None,
    metadata: Annotated[str | None, Form()] = None,
) -> ApiResponse:
    if operation == "create_entity":
        parsed_metadata = _parse_metadata(metadata or "", EntitySchemaCreate).model_dump()
    elif operation == "create_relation":
        parsed_metadata = _parse_metadata(metadata or "", RelationSchemaCreate).model_dump()
    else:
        parsed_metadata = None

    application = _application(session)
    try:
        data = application.start_script_validation(
            operation=operation,
            schema_id=schema_id,
            metadata=parsed_metadata,
            user_id=user_id,
            filename=script.filename or "",
            content_type=script.content_type,
            script_data=_read_script(script),
        )
    except SchemaManagementError as exc:
        _raise_domain_error(exc)

    validation_session_factory = sessionmaker(
        bind=session.get_bind(), expire_on_commit=False, future=True
    )
    background_tasks.add_task(
        _run_validation_background,
        data["id"],
        validation_session_factory,
        application.storage,
    )
    return ApiResponse(code=202, data=data, msg="脚本安全校验已开始")


@router.get("/script-validations/{validation_id}", response_model=ApiResponse)
def get_script_validation(
    validation_id: str,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
) -> ApiResponse:
    try:
        return ApiResponse(data=_application(session).get_script_validation(validation_id, user_id))
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.get("/script-validations/{validation_id}/events")
def stream_script_validation(
    validation_id: str,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Query(alias="userId", min_length=1, max_length=128)],
) -> StreamingResponse:
    application = _application(session)
    try:
        application.get_script_validation(validation_id, user_id)
    except SchemaManagementError as exc:
        _raise_domain_error(exc)

    validation_session_factory = sessionmaker(
        bind=session.get_bind(), expire_on_commit=False, future=True
    )
    storage = application.storage

    async def event_stream():
        last_payload = ""
        last_heartbeat = time.monotonic()
        event_id = 0
        while True:
            with validation_session_factory() as poll_session:
                current = SchemaManagementApplication(
                    poll_session, storage=storage
                ).get_script_validation(validation_id, user_id)
            payload = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
            if payload != last_payload:
                event_id += 1
                event_name = (
                    "completed"
                    if current["status"] == "succeeded"
                    else "failed"
                    if current["status"] == "failed"
                    else "status"
                )
                yield f"id: {event_id}\nevent: {event_name}\ndata: {payload}\n\n"
                last_payload = payload
                last_heartbeat = time.monotonic()
            elif time.monotonic() - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
            if current["status"] in {"succeeded", "failed"}:
                break
            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/schemas/{schema_id}/execute", response_model=ApiResponse, status_code=202)
async def execute_schema_script(
    schema_id: str,
    request: SchemaExecuteRequest,
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128)],
) -> ApiResponse:
    try:
        data = await _application(session).execute_schema(schema_id, user_id, request.payload)
        return ApiResponse(code=202, data=data, msg="Schema 脚本执行请求已受理")
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
