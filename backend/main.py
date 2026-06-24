from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from biz.router.register import register_routers
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_SOURCE_INDEX = PROJECT_ROOT / "frontend" / "index.html"


@app.get("/", include_in_schema=False)
async def serve_frontend_index() -> FileResponse:
    index_file = FRONTEND_INDEX if FRONTEND_INDEX.exists() else FRONTEND_SOURCE_INDEX
    return FileResponse(index_file)


@app.get("/legacy/binding", include_in_schema=False)
async def serve_legacy_binding() -> FileResponse:
    legacy_file = PROJECT_ROOT / "frontend" / "public" / "legacy" / "binding.html"
    return FileResponse(legacy_file)


@app.exception_handler(GraphRepoError)
async def graph_error_handler(request, exc: GraphRepoError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"status": "error", "message": str(exc)})


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
