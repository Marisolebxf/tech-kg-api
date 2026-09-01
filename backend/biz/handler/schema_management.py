"""Schema 管理 API。"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from application.schema_management import SchemaManagementApplication
from biz.dependencies.auth import CurrentActor
from biz.schemas.common import ApiResponse
from biz.schemas.schema_management import (
    EntitySchemaCreate,
    RelationSchemaCreate,
    SchemaExtractRequest,
    SchemaPropertyInput,
    SchemaSourcesReplace,
)
from infra.workflow_mysql import get_workflow_session
from service.schema_management import (
    SchemaConflictError,
    SchemaDdlError,
    SchemaManagementError,
    SchemaNotFoundError,
    SchemaPermissionError,
    SchemaScriptError,
    SchemaStorageError,
    max_script_bytes,
)

router = APIRouter(prefix="/schema-management", tags=["schema-management"])


def _application(session: Session) -> SchemaManagementApplication:
    return SchemaManagementApplication(session)


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
    elif isinstance(exc, SchemaDdlError):
        status_code = 502
    else:
        status_code = 400
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/overview", response_model=ApiResponse)
def get_schema_overview(session: Annotated[Session, Depends(get_workflow_session)]) -> ApiResponse:
    return ApiResponse(data=_application(session).overview())


@router.get("/schemas", response_model=ApiResponse)
def list_schemas(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    kind: Annotated[str | None, Query(pattern="^(entity|relation)$")] = None,
    keyword: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    include_details: Annotated[bool, Query(alias="includeDetails")] = False,
) -> ApiResponse:
    data = _application(session).list_schemas(
        kind=kind,
        keyword=keyword.strip() if keyword else None,
        page=page,
        page_size=page_size,
        user_id=actor.user_id,
        include_details=include_details,
        is_platform_admin=actor.is_admin,
    )
    return ApiResponse(data=data)


@router.get("/schemas/topology", response_model=ApiResponse)
def get_schema_topology(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    return ApiResponse(
        data=_application(session).topology(
            actor.user_id,
            is_platform_admin=actor.is_admin,
        )
    )


@router.get("/schemas/{schema_id}", response_model=ApiResponse)
def get_schema_detail(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    try:
        return ApiResponse(
            data=_application(session).get_schema(
                schema_id,
                actor.user_id,
                is_platform_admin=actor.is_admin,
            )
        )
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/entities", response_model=ApiResponse, status_code=201)
def create_entity_schema(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: EntitySchemaCreate,
) -> ApiResponse:
    try:
        data = _application(session).create_entity(
            payload=payload.model_dump(),
            user_id=actor.user_id,
        )
        return ApiResponse(data=data, msg="实体 Schema 创建成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/relations", response_model=ApiResponse, status_code=201)
def create_relation_schema(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: RelationSchemaCreate,
) -> ApiResponse:
    try:
        data = _application(session).create_relation(
            payload=payload.model_dump(),
            user_id=actor.user_id,
        )
        return ApiResponse(data=data, msg="关系 Schema 创建成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.delete("/schemas/{schema_id}", response_model=ApiResponse)
def delete_schema(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    try:
        data = _application(session).delete_schema(
            schema_id,
            actor.user_id,
            is_platform_admin=actor.is_admin,
        )
        return ApiResponse(data=data, msg="Schema 删除成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/{schema_id}/properties", response_model=ApiResponse, status_code=201)
def add_schema_property(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: SchemaPropertyInput,
) -> ApiResponse:
    """新增属性：目录插入 + 图 ALTER ADD；DDL 失败回滚目录行（目录与图保持一致）。"""
    try:
        data = _application(session).add_property(
            schema_id=schema_id,
            payload=payload.model_dump(),
            user_id=actor.user_id,
            is_platform_admin=actor.is_admin,
        )
        return ApiResponse(data=data, msg="属性新增成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.delete("/schemas/{schema_id}/properties/{property_name}", response_model=ApiResponse)
def delete_schema_property(
    schema_id: str,
    property_name: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    """目录级软删属性：置 is_deleted flag，不发图 DDL。必选属性不可删除。"""
    try:
        data = _application(session).delete_property(
            schema_id=schema_id,
            property_name=property_name,
            user_id=actor.user_id,
            is_platform_admin=actor.is_admin,
        )
        return ApiResponse(data=data, msg="属性已删除")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.put("/schemas/{schema_id}/sources", response_model=ApiResponse)
def replace_schema_sources(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: SchemaSourcesReplace,
) -> ApiResponse:
    """全量替换来源表绑定（实体/关系可绑多张表，每表独立水位）。"""
    try:
        data = _application(session).replace_sources(
            schema_id=schema_id,
            sources=[item.model_dump() for item in payload.sources],
            user_id=actor.user_id,
            is_platform_admin=actor.is_admin,
        )
        return ApiResponse(data=data, msg="来源表绑定已保存")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/{schema_id}/extract", response_model=ApiResponse, status_code=201)
async def trigger_schema_extraction(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: SchemaExtractRequest | None = None,
) -> ApiResponse:
    """触发平台喂数抽取（kg.schema.extract）：按来源表水位分批读取 → 脚本转换 → 写图。

    要求已上传脚本且已绑定 ≥1 来源表，否则 409。执行记录可在任务中心查看。
    """
    try:
        data = await _application(session).trigger_extraction(
            schema_id=schema_id,
            user_id=actor.user_id,
            is_platform_admin=actor.is_admin,
            graph_space=payload.graph_space if payload else None,
            batch_size=payload.batch_size if payload else None,
        )
        return ApiResponse(data=data, msg="抽取已触发")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.put("/schemas/{schema_id}/script", response_model=ApiResponse)
def replace_schema_script(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    script: Annotated[UploadFile, File(...)],
) -> ApiResponse:
    try:
        data = _application(session).replace_script(
            schema_id=schema_id,
            user_id=actor.user_id,
            is_platform_admin=actor.is_admin,
            filename=script.filename or "",
            content_type=script.content_type,
            script_data=_read_script(script),
        )
        return ApiResponse(data=data, msg="Schema 脚本上传成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


def _format_sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


_SENTINEL = object()


@router.post("/schemas/{schema_id}/script/verify")
async def verify_and_save_script(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    script: Annotated[UploadFile, File(...)],
) -> StreamingResponse:
    """上传脚本 → LLM 安全校验 → 保存，以 SSE 流式回传进度。

    流前失败（schema 不存在 / 无权限）→ HTTP 4xx；流中失败 → ``type=error`` 事件。
    整个校验/保存流程在单一专用线程中驱动，使用独立 Session，避免跨线程会话。
    """
    app = _application(session)
    script_data = await script.read(max_script_bytes() + 1)

    queue: asyncio.Queue[Any] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run() -> None:
        try:
            for event in app.verify_and_save_script(
                schema_id=schema_id,
                user_id=actor.user_id,
                is_platform_admin=actor.is_admin,
                filename=script.filename or "",
                content_type=script.content_type,
                script_data=script_data,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "type": "error",
                    "code": "internal",
                    "stage": "unknown",
                    "message": f"内部错误: {exc}",
                    "issues": [f"内部错误: {exc}"],
                },
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    worker = loop.run_in_executor(None, run)

    first = await queue.get()
    if first is _SENTINEL:
        await worker
        raise HTTPException(status_code=500, detail="校验未产生任何事件")
    if (
        isinstance(first, dict)
        and first.get("type") == "error"
        and first.get("code")
        in (
            "not_found",
            "permission",
        )
    ):
        await queue.get()  # drain SENTINEL
        await worker
        status_code = 404 if first["code"] == "not_found" else 403
        raise HTTPException(status_code=status_code, detail=first["message"])

    async def event_stream():
        try:
            yield _format_sse(first)
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield _format_sse(item)
        finally:
            await worker

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/schemas/{schema_id}/script/content", response_model=ApiResponse)
def get_schema_script_content(
    schema_id: str,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    try:
        data = _application(session).get_script_content(schema_id)
        return ApiResponse(data=data)
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.get("/schemas/{schema_id}/script")
def download_schema_script(
    schema_id: str,
    session: Annotated[Session, Depends(get_workflow_session)],
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
