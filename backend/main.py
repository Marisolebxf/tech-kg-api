from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from biz.router.register import register_routers
from biz.schemas.common import ApiResponse
from infra.graph_db import close_techkg_client, close_trs_graph_client
from infra.graph_db.exceptions import GraphRepoError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """trs-graph clients connect lazily on first use; close on shutdown."""
    try:
        yield
    finally:
        close_techkg_client()
        close_trs_graph_client()


app = FastAPI(
    title="Tech KG API",
    description="Backend service for the technology knowledge graph.",
    version="0.1.0",
    lifespan=lifespan,
)

register_routers(app)


@app.exception_handler(GraphRepoError)
async def graph_error_handler(request, exc: GraphRepoError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"status": "error", "message": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    # exc.errors() 的 ctx 可能含不可序列化对象（如 ValueError），只取可序列化字段
    errors = [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=200,
        content=ApiResponse(
            code=422, success=False, msg="请求参数校验失败", data=errors
        ).model_dump(),
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
