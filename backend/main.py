import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from biz.router.register import register_routers
from biz.schemas.common import ApiResponse
from infra.graph_db import close_techkg_client, close_trs_graph_client
from infra.graph_db.exceptions import GraphRepoError
from infra.mysql import session_scope
from infra.redis import close_redis_client
from service.correction import process_due_sync_tasks
from service.operator_registry import REGISTRY

logger = logging.getLogger(__name__)


def _dispatch_corrections_once() -> int:
    with session_scope() as session:
        return process_due_sync_tasks(session)


async def _run_correction_dispatcher() -> None:
    interval = max(5, int(os.getenv("CORRECTION_SYNC_INTERVAL_SECONDS", "30")))
    while True:
        try:
            await asyncio.to_thread(_dispatch_corrections_once)
        except Exception:
            logger.exception("人工修正同步轮询失败，将在下一周期重试")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化 Schema 和算子服务，并在退出时释放基础设施资源。"""
    await asyncio.to_thread(REGISTRY.initialize_store)
    REGISTRY.start_watcher()
    correction_dispatcher = None
    if os.getenv("CORRECTION_SYNC_WORKER_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        correction_dispatcher = asyncio.create_task(_run_correction_dispatcher())
    try:
        # 确保 platform_llm_config 表存在（LLM 配置持久化，schema 作业默认 LLM 绑定依赖）。
        # MySQL 不可达时跳过建表：CI 无 MySQL 服务，运行期访问 LLM 配置接口会单独报错。
        from db_model.base import Base
        from db_model.llm_config import LlmConfig
        from infra.mysql import get_engine

        try:
            Base.metadata.create_all(get_engine(), tables=[LlmConfig.__table__])
        except Exception as exc:
            logger.warning("跳过 platform_llm_config 建表：MySQL 不可达 %s", exc)
        if os.getenv("SCHEMA_AUTO_INIT", "false").lower() == "true":
            from script.init_schema_management import initialize_schema_management

            inserted = initialize_schema_management()
            logger.info("Schema 管理初始化完成，新增系统 Schema: %s", inserted)
        # 后台预热全库统计缓存：count 是全量扫描要几十秒，等首个用户请求
        # 触发会把图服务压挂、拖慢同时进来的其它查询。
        from biz.handler.graph_search import prewarm_stats

        asyncio.get_running_loop().create_task(prewarm_stats())
        # 后台预热九大业务模块结果缓存（PREWARM_BUSINESS=true 时生效），
        # 使每个 worker 在压测稳态下命中缓存，避免冷启动击穿 trs-graph。
        from biz.prewarm_business import prewarm_business

        asyncio.get_running_loop().create_task(prewarm_business(app))
        yield
    finally:
        if correction_dispatcher is not None:
            correction_dispatcher.cancel()
            with suppress(asyncio.CancelledError):
                await correction_dispatcher
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
    path = request.url.path
    indirect_relation_path = (
        path == "/api/v1/kg-construction/expert-indirect-relations/demo/structured-result"
    )
    paper_cooperation_path = (
        path == "/api/v1/kg-construction/expert-paper-cooperation-relations/structured-result"
    )
    uses_http_422 = (
        indirect_relation_path
        or paper_cooperation_path
        or path == ("/api/v1/kg-construction/expert-cooperation-achievements/query")
        or (path.startswith("/api/v1/workflow-system/definitions/") and path.endswith("/execute"))
    )
    validation_message = "接口参数校验错误" if indirect_relation_path else "请求参数校验失败"
    if paper_cooperation_path:
        first_error = errors[0]["msg"] if errors else "请求参数校验失败"
        detail_message = first_error.removeprefix("Value error, ")
        validation_message = f"接口参数校验错误：{detail_message}"
    return JSONResponse(
        status_code=422 if uses_http_422 else 200,
        content=ApiResponse(
            code=422,
            success=False,
            msg=validation_message,
            data=errors,
        ).model_dump(),
    )


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
