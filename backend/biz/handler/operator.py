"""算子注册、查询、调用和内部重载 API。"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from application.operator import OperatorApplication
from biz.handler import get_cache
from biz.schemas.operator import (
    OperatorInvokeRequest,
    OperatorInvokeResponse,
    OperatorListResponse,
    OperatorManifestResponse,
    OperatorReloadResponse,
    OperatorSyncRequest,
    OperatorUpdateRequest,
    OperatorUploadRequest,
)
from service.operator_registry import (
    OperatorConflictError,
    OperatorExecutionError,
    OperatorKind,
    OperatorNotFoundError,
    OperatorRegistryError,
    OperatorStorageError,
    OperatorValidationError,
)

router = APIRouter(prefix="/operators", tags=["operators"])
internal_router = APIRouter(prefix="/internal/operators", tags=["internal-operators"])
application = OperatorApplication()


def get_operator_application() -> OperatorApplication:
    return application


OperatorApplicationDependency = Annotated[OperatorApplication, Depends(get_operator_application)]


def _raise_http_error(exc: OperatorRegistryError) -> None:
    if isinstance(exc, OperatorNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, OperatorConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, (OperatorValidationError, OperatorExecutionError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, OperatorStorageError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="算子服务内部错误") from exc


@router.get("", response_model=OperatorListResponse)
async def list_operators(
    request: Request,
    app: OperatorApplicationDependency,
    kind: OperatorKind | None = None,
) -> Response:
    cached = get_cache.try_get("operator:list", request)
    if cached is not None:
        return cached
    return get_cache.store("operator:list", request, {"items": app.list(kind)})


@router.get("/{name}", response_model=OperatorManifestResponse)
async def get_operator(name: str, app: OperatorApplicationDependency) -> dict[str, object]:
    try:
        return app.get(name)
    except OperatorRegistryError as exc:
        _raise_http_error(exc)


@router.post("", response_model=OperatorManifestResponse, status_code=status.HTTP_201_CREATED)
async def create_operator(
    body: OperatorUploadRequest, app: OperatorApplicationDependency
) -> dict[str, object]:
    try:
        result = await app.create(**body.model_dump())
    except OperatorRegistryError as exc:
        _raise_http_error(exc)
    get_cache.invalidate("operator:list")
    return result


@router.put("/{name}", response_model=OperatorManifestResponse)
async def update_operator(
    name: str, body: OperatorUpdateRequest, app: OperatorApplicationDependency
) -> dict[str, object]:
    try:
        result = await app.update(name=name, **body.model_dump())
    except OperatorRegistryError as exc:
        _raise_http_error(exc)
    get_cache.invalidate("operator:list")
    return result


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operator(name: str, app: OperatorApplicationDependency) -> Response:
    try:
        await app.delete(name)
    except OperatorRegistryError as exc:
        _raise_http_error(exc)
    get_cache.invalidate("operator:list")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{name}/invoke", response_model=OperatorInvokeResponse)
async def invoke_operator(
    name: str, body: OperatorInvokeRequest, app: OperatorApplicationDependency
) -> dict[str, object]:
    try:
        return await app.invoke(name, body.data, body.ctx)
    except OperatorRegistryError as exc:
        _raise_http_error(exc)


@internal_router.post(
    "/reload",
    response_model=OperatorReloadResponse,
    responses={401: {"description": "身份认证失败"}, 503: {"description": "服务暂不可用"}},
)
async def reload_operators(
    app: OperatorApplicationDependency,
    body: OperatorSyncRequest | None = None,
    reload_token: Annotated[str | None, Header(alias="X-Operator-Reload-Token")] = None,
) -> dict[str, object]:
    expected_token = os.getenv("OPERATOR_RELOAD_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=503, detail="算子重载令牌尚未配置")
    if not (reload_token and secrets.compare_digest(reload_token, expected_token)):
        raise HTTPException(status_code=401, detail="重载令牌无效")
    try:
        loaded = (
            app.sync_user_operators(
                [bundle.model_dump(mode="json") for bundle in body.operators],
                replace=body.replace,
            )
            if body is not None
            else app.reload_all()
        )
    except OperatorRegistryError as exc:
        _raise_http_error(exc)
    return {"loaded": loaded, "count": len(loaded)}
