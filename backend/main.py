import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from biz.router.register import register_routers
from biz.schemas.common import ApiResponse
from infra.graph_db import close_techkg_client, close_trs_graph_client
from infra.graph_db.exceptions import GraphRepoError
from infra.redis import close_redis_client
from service.operator_registry import REGISTRY

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化 Schema 和算子服务，并在退出时释放基础设施资源。"""
    await asyncio.to_thread(REGISTRY.initialize_store)
    REGISTRY.start_watcher()
    try:
        if os.getenv("SCHEMA_AUTO_INIT", "false").lower() == "true":
            from script.init_schema_management import initialize_schema_management

            inserted = initialize_schema_management()
            logger.info("Schema 管理初始化完成，新增系统 Schema: %s", inserted)
        yield
    finally:
        REGISTRY.stop_watcher()
        await close_redis_client()
        close_techkg_client()
        close_trs_graph_client()


app = FastAPI(
    title="Tech KG API",
    description="Backend service for the technology knowledge graph.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
)

app.mount("/static/swagger", StaticFiles(directory="static/swagger"), name="swagger-static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
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
