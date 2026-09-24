"""Schema 管理 API。"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from application.schema_management import SchemaManagementApplication
from biz.dependencies.auth import CurrentActor
from biz.schemas.common import ApiResponse
from biz.schemas.schema_management import (
    EntitySchemaCreate,
    RelationSchemaCreate,
    SchemaBackfillRequest,
    SchemaExtractRequest,
    SchemaPropertyInput,
    SchemaSourcesReplace,
)
from dao.schema_management import SchemaManagementDAO
from infra.workflow_mysql import get_workflow_session
from service.business_access_control import allowed_space_names, ensure_space_access, rbac_enabled
from service.schema_ddl import default_graph_space
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


def _scoped_space(actor, space):
    if not rbac_enabled():
        return space
    if not space:
        spaces = allowed_space_names(actor)
        if not spaces:
            raise HTTPException(status_code=403, detail="尚未分配可访问图空间")
        space = spaces[0]
    ensure_space_access(actor, space)
    return space


def _schema_access(actor, session, schema_id, action="read", target_space=None):
    if not rbac_enabled():
        return
    row = SchemaManagementDAO(session).get(schema_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Schema 不存在")
    ensure_space_access(actor, row.graph_space, action)
    if target_space and target_space != row.graph_space:
        raise HTTPException(status_code=403, detail="目标空间必须与 Schema 所属空间一致")


def _can_manage(actor):
    return actor.is_admin or (rbac_enabled() and actor.can_develop)


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


@router.get("/overview")
def get_schema_overview(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    graph_space: Annotated[str | None, Query(alias="graphSpace", max_length=64)] = None,
) -> Response:
    graph_space = _scoped_space(actor, graph_space)
    return Response(
        _application(session).overview_payload(graph_space), media_type="application/json"
    )


@router.get("/schemas")
def list_schemas(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    kind: Annotated[str | None, Query(pattern="^(entity|relation)$")] = None,
    keyword: Annotated[str | None, Query(max_length=128)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    include_details: Annotated[bool, Query(alias="includeDetails")] = False,
    graph_space: Annotated[str | None, Query(alias="graphSpace", max_length=64)] = None,
) -> Response:
    # 高频列表接口：直接返回预构建 JSON（绕开 pydantic 响应校验的 GIL 瓶颈），
    # 响应体与 ApiResponse 信封逐字段一致。用户隔离只影响 canDelete/
    # canManageProperties 两个展示位，服务端各写接口仍强制校验归属。
    graph_space = _scoped_space(actor, graph_space)
    payload = _application(session).list_schemas_payload(
        kind=kind,
        keyword=keyword.strip() if keyword else None,
        page=page,
        page_size=page_size,
        user_id=actor.user_id,
        include_details=include_details,
        is_platform_admin=_can_manage(actor),
        graph_space=graph_space,
    )
    return Response(payload, media_type="application/json")


@router.get("/schemas/topology")
def get_schema_topology(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    graph_space: Annotated[str | None, Query(alias="graphSpace", max_length=64)] = None,
) -> Response:
    graph_space = _scoped_space(actor, graph_space)
    return Response(
        _application(session).topology_payload(
            actor.user_id,
            is_platform_admin=_can_manage(actor),
            graph_space=graph_space,
        ),
        media_type="application/json",
    )


@router.get("/schemas/{schema_id}")
def get_schema_detail(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> Response:
    _schema_access(actor, session, schema_id, "read")
    try:
        return Response(
            _application(session).get_schema_payload(
                schema_id,
                actor.user_id,
                is_platform_admin=_can_manage(actor),
            ),
            media_type="application/json",
        )
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/entities", status_code=201)
def create_entity_schema(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: EntitySchemaCreate,
) -> ApiResponse:
    if rbac_enabled():
        ensure_space_access(actor, payload.graph_space or default_graph_space(), "write")
    try:
        data = _application(session).create_entity(
            payload=payload.model_dump(),
            user_id=actor.user_id,
        )
        return ApiResponse(data=data, msg="实体 Schema 创建成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/relations", status_code=201)
def create_relation_schema(
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: RelationSchemaCreate,
) -> ApiResponse:
    if rbac_enabled():
        ensure_space_access(actor, payload.graph_space or default_graph_space(), "write")
        for endpoint in (payload.source_schema_id, payload.target_schema_id):
            if endpoint:
                _schema_access(
                    actor, session, endpoint, "read", payload.graph_space or default_graph_space()
                )
    try:
        data = _application(session).create_relation(
            payload=payload.model_dump(),
            user_id=actor.user_id,
        )
        return ApiResponse(data=data, msg="关系 Schema 创建成功")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.get("/schemas/{schema_id}/delete-impact")
def get_schema_delete_impact(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    """删除影响预览：实体返回仍引用它的关系清单（前端删除确认弹窗展示）。"""
    _schema_access(actor, session, schema_id, "read")
    try:
        return ApiResponse(
            data=_application(session).delete_impact(
                schema_id,
                actor.user_id,
                is_platform_admin=_can_manage(actor),
            )
        )
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.delete("/schemas/{schema_id}")
def delete_schema(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> ApiResponse:
    _schema_access(actor, session, schema_id, "write")
    try:
        data = _application(session).delete_schema(
            schema_id,
            actor.user_id,
            is_platform_admin=_can_manage(actor),
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
    _schema_access(actor, session, schema_id, "write")
    try:
        data = _application(session).add_property(
            schema_id=schema_id,
            payload=payload.model_dump(),
            user_id=actor.user_id,
            is_platform_admin=_can_manage(actor),
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
    """硬删除属性：图库 ALTER DROP 物理删列 + 目录删行，不可逆。

    required 属性与运行中抽取任务硬拦（409）；identity/关系表达式引用只随
    ``warnings`` 警告。列不存在时跳过 DDL 只删目录行。
    """
    _schema_access(actor, session, schema_id, "write")
    try:
        data = _application(session).delete_property(
            schema_id=schema_id,
            property_name=property_name,
            user_id=actor.user_id,
            is_platform_admin=_can_manage(actor),
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
    _schema_access(actor, session, schema_id, "write")
    if rbac_enabled():
        from biz.handler.workflow_system import _validate_resource_selectors

        for source in payload.sources:
            _validate_resource_selectors(actor, {"mysql_datasource_id": source.datasource_id})
    try:
        data = _application(session).replace_sources(
            schema_id=schema_id,
            sources=[item.model_dump() for item in payload.sources],
            user_id=actor.user_id,
            is_platform_admin=_can_manage(actor),
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
    _schema_access(actor, session, schema_id, "write", payload.graph_space if payload else None)
    if rbac_enabled() and payload and payload.graph_space:
        ensure_space_access(actor, payload.graph_space, "write")
    try:
        data = await _application(session).trigger_extraction(
            schema_id=schema_id,
            user_id=actor.user_id,
            is_platform_admin=_can_manage(actor),
            graph_space=payload.graph_space if payload else None,
            batch_size=payload.batch_size if payload else None,
            actor=actor,
        )
        return ApiResponse(data=data, msg="抽取已触发")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.post("/schemas/{schema_id}/backfill", response_model=ApiResponse, status_code=201)
async def backfill_schema_history(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    payload: SchemaBackfillRequest | None = None,
) -> ApiResponse:
    """回填历史数据：清空该 Schema 全部来源水位后触发全量重跑（可反复执行）。

    前置同触发抽取（已上传脚本 + ≥1 来源绑定）。脚本落后于 Schema 时回填可能
    无效，未带 ``force`` 返回 409，前端强确认后带 force 重发。
    """
    _schema_access(actor, session, schema_id, "write", payload.graph_space if payload else None)
    if rbac_enabled() and payload and payload.graph_space:
        ensure_space_access(actor, payload.graph_space, "write")
    try:
        data = await _application(session).backfill(
            schema_id=schema_id,
            user_id=actor.user_id,
            is_platform_admin=_can_manage(actor),
            force=payload.force if payload else False,
            graph_space=payload.graph_space if payload else None,
            batch_size=payload.batch_size if payload else None,
            actor=actor,
        )
        return ApiResponse(data=data, msg="历史数据回填已触发")
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.put("/schemas/{schema_id}/script", response_model=ApiResponse)
def replace_schema_script(
    schema_id: str,
    actor: CurrentActor,
    session: Annotated[Session, Depends(get_workflow_session)],
    script: Annotated[UploadFile, File(...)],
) -> ApiResponse:
    _schema_access(actor, session, schema_id, "write")
    try:
        data = _application(session).replace_script(
            schema_id=schema_id,
            user_id=actor.user_id,
            is_platform_admin=_can_manage(actor),
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


@router.post("/schemas/{schema_id}/script/verify", responses={500: {"description": "服务内部错误"}})
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
    _schema_access(actor, session, schema_id, "write")
    app = _application(session)
    script_data = await script.read(max_script_bytes() + 1)

    queue: asyncio.Queue[Any] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run() -> None:
        try:
            for event in app.verify_and_save_script(
                schema_id=schema_id,
                user_id=actor.user_id,
                is_platform_admin=_can_manage(actor),
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


@router.get("/schemas/{schema_id}/script/content")
def get_schema_script_content(
    actor: CurrentActor,
    schema_id: str,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> Response:
    _schema_access(actor, session, schema_id, "read")
    try:
        return Response(
            _application(session).get_script_content_payload(schema_id),
            media_type="application/json",
        )
    except SchemaManagementError as exc:
        _raise_domain_error(exc)


@router.get("/schemas/{schema_id}/script")
def download_schema_script(
    actor: CurrentActor,
    schema_id: str,
    session: Annotated[Session, Depends(get_workflow_session)],
) -> StreamingResponse:
    _schema_access(actor, session, schema_id, "read")
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
