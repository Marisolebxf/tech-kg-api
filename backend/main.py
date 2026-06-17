from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from biz.router.register import register_routers
from infra.graph_db import close_trs_graph_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """trs-graph client connects lazily on first use; close on shutdown."""
    try:
        yield
    finally:
        close_trs_graph_client()


app = FastAPI(
    title="Tech KG API",
    description="Backend service for the technology knowledge graph.",
    version="0.1.0",
    lifespan=lifespan,
)

register_routers(app)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
