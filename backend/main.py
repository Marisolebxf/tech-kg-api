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
        # 确保 platform_llm_config 表存在（LLM 配置持久化，schema 作业默认 LLM 绑定依赖）
        from db_model.base import Base
        from db_model.llm_config import LlmConfig
        from infra.mysql import get_engine

        Base.metadata.create_all(get_engine(), tables=[LlmConfig.__table__])
        if os.getenv("SCHEMA_AUTO_INIT", "false").lower() == "true":
            from script.init_schema_management import initialize_schema_management

            inserted = initialize_schema_management()
            logger.info("Schema 管理初始化完成，新增系统 Schema: %s", inserted)
        # 后台启动 Temporal Worker：执行 kg.* workflow 与 execute_python_script activity。
        # 与 uvicorn 同进程，dev/单 worker 部署可用；生产建议独立 worker 进程。
        from service.temporal_runtime import temporal_runtime

        worker_task = asyncio.create_task(temporal_runtime.run_worker())

        async def _log_worker_failure(task: asyncio.Task) -> None:
            try:
                await task
            except Exception:
                logger.exception("Temporal Worker 异常退出")

        asyncio.create_task(_log_worker_failure(worker_task))
        # 后台预热全库统计缓存：count 是全量扫描要几十秒，等首个用户请求
        # 触发会把图服务压挂、拖慢同时进来的其它查询。
        from biz.handler.graph_search import prewarm_stats

        asyncio.get_running_loop().create_task(prewarm_stats())
        yield
    finally:
        REGISTRY.stop_watcher()
        if "worker_task" in locals():
            worker_task.cancel()
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
