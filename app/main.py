import os
import logging
import threading

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routers.entity_linking import router as entity_linking_router
from app.routers.entity_extraction import router as entity_extraction_router
from app.routers.graphrag_demo import router as graphrag_demo_router
from app.routers.relation_extraction import router as relation_extraction_router
from app.routers.entity_binding import router as entity_binding_router
from app.services.extraction_job_runner import (
    start_extraction_job_runner,
    stop_extraction_job_runner,
)
from app.services.extraction_task_store import (
    start_extraction_task_store_scheduler,
    stop_extraction_task_store_scheduler,
)
from app.services.expert_direct_cache import (
    start_expert_direct_cache_scheduler,
    stop_expert_direct_cache_scheduler,
)
from app.services.semantic_matcher import SemanticMatcher


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Tech KG API",
    description="亿级知识图谱 API 接口",
    version="0.1.0",
)

app.include_router(entity_linking_router, prefix="/api/v1")
app.include_router(entity_extraction_router, prefix="/api/v1")
app.include_router(graphrag_demo_router, prefix="/api/v1")
app.include_router(relation_extraction_router, prefix="/api/v1")
app.include_router(entity_binding_router, prefix="/api/v1")

# Mount static files for binding demo
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def startup_event():
    start_extraction_task_store_scheduler()
    start_extraction_job_runner()
    start_expert_direct_cache_scheduler()
    threading.Thread(target=_warm_semantic_indexes, name="semantic-matcher-warmup", daemon=True).start()


@app.on_event("shutdown")
def shutdown_event():
    stop_extraction_job_runner()
    stop_extraction_task_store_scheduler()
    stop_expert_direct_cache_scheduler()


def _warm_semantic_indexes() -> None:
    try:
        warmed = SemanticMatcher().prewarm_binding_indexes()
        if warmed:
            logger.info("Semantic matcher indexes warmed: %s", ", ".join(sorted(warmed.keys())))
    except Exception as exc:  # pragma: no cover - best effort warmup
        logger.warning("Semantic matcher warmup failed: %s", exc)


@app.get("/hello")
def hello():
    return {"message": "Hello, Tech KG!"}


@app.get("/api")
def api_root():
    return {"message": "API is running", "version": "0.1.0"}


@app.get("/")
def root_page():
    """Serve the binding demo at the site root for convenience."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "binding.html")
    if os.path.exists(static_path):
        return FileResponse(static_path, headers={"Cache-Control": "no-store"})
    return {"message": "Binding demo page not found. Create app/static/binding.html"}


@app.get("/binding")
def binding_demo():
    """Serve the binding demo page."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "binding.html")
    if os.path.exists(static_path):
        return FileResponse(static_path, headers={"Cache-Control": "no-store"})
    return {"message": "Binding demo page not found. Create app/static/binding.html"}
