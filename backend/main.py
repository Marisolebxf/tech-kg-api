"""FastAPI application entry point."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress

from fastapi import FastAPI

from biz.errors import register_exception_handlers
from biz.router.register import register_routers
from infra.lifecycle import close_infrastructure
from service.operator_registry import REGISTRY
from service.workflow_operations import workflow_operations_service

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize application services and release all resources on shutdown."""
    await asyncio.to_thread(REGISTRY.initialize_store)
    REGISTRY.start_watcher()
    retry_task = asyncio.create_task(
        workflow_operations_service.run_fallback_dispatcher(),
        name="workflow-fallback-dispatcher",
    )
    try:
        if os.getenv("SCHEMA_AUTO_INIT", "false").lower() == "true":
            from script.init_schema_management import initialize_schema_management

            inserted = await asyncio.to_thread(initialize_schema_management)
            logger.info("Schema 管理初始化完成，新增系统 Schema: %s", inserted)
        yield
    finally:
        retry_task.cancel()
        with suppress(asyncio.CancelledError):
            await retry_task
        REGISTRY.stop_watcher()
        close_infrastructure()


def create_app(*, app_lifespan: Lifespan = lifespan) -> FastAPI:
    """Build an isolated application instance for servers and tests."""
    app = FastAPI(
        title="Tech KG API",
        description="Backend service for the technology knowledge graph.",
        version="0.1.0",
        lifespan=app_lifespan,
    )
    register_exception_handlers(app)
    register_routers(app)
    return app


app = create_app()
