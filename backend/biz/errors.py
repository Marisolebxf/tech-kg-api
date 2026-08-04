"""Application-wide exception handlers and the canonical error envelope."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from biz.schemas.common import ApiResponse
from infra.graph_db.exceptions import GraphRepoError

logger = logging.getLogger(__name__)


def _error_response(status_code: int, message: str, data: Any = None) -> JSONResponse:
    response = ApiResponse(code=status_code, success=False, msg=message, data=data)
    return JSONResponse(status_code=status_code, content=response.model_dump())


async def graph_error_handler(_request: Request, exc: GraphRepoError) -> JSONResponse:
    return _error_response(502, str(exc))


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
    data = None if isinstance(exc.detail, str) else exc.detail
    response = _error_response(exc.status_code, message, data)
    response.headers.update(exc.headers or {})
    return response


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return the project's stable response envelope for validation failures."""
    errors = [
        {
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    return _error_response(422, "请求参数校验失败", errors)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error: %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response(500, "服务器内部错误")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GraphRepoError, graph_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
