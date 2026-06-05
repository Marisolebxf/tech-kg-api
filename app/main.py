from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.routers.entity_linking import router as entity_linking_router
from app.routers.entity_extraction import router as entity_extraction_router
from app.routers.graphrag_demo import router as graphrag_demo_router
from app.routers.relation_extraction import router as relation_extraction_router
from app.routers.entity_binding import router as entity_binding_router

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


@app.get("/hello")
def hello():
    return {"message": "Hello, Tech KG!"}


@app.get("/api")
def api_root():
    return {"message": "API is running", "version": "0.1.0"}


@app.get("/binding")
def binding_demo():
    """Serve the binding demo page."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "binding.html")
    if os.path.exists(static_path):
        return FileResponse(static_path)
    return {"message": "Binding demo page not found. Create app/static/binding.html"}
