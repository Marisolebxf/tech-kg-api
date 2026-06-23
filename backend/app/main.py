from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles
import swagger_ui_bundle

from app.routers.entity_extraction import router as entity_extraction_router
from app.routers.entity_linking import router as entity_linking_router
from app.routers.graphrag_demo import router as graphrag_demo_router
from app.routers.kg_visual import page_router as kg_visual_page_router
from app.routers.kg_visual import router as kg_visual_router
from app.routers.relation_extraction import router as relation_extraction_router
from app.routers.scholar_paper_cooperation import router as scholar_paper_cooperation_router

app = FastAPI(
    title="Tech KG API",
    description="亿级知识图谱 API 接口",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

app.mount("/static/swagger", StaticFiles(directory=swagger_ui_bundle.swagger_ui_path), name="swagger-static")

app.openapi_version = "3.0.3"

app.include_router(entity_linking_router, prefix="/api/v1")
app.include_router(entity_extraction_router, prefix="/api/v1")
app.include_router(graphrag_demo_router, prefix="/api/v1")
app.include_router(kg_visual_router, prefix="/api/v1")
app.include_router(kg_visual_page_router)
app.include_router(relation_extraction_router, prefix="/api/v1")
app.include_router(scholar_paper_cooperation_router, prefix="/api/v1")


@app.get("/hello")
def hello():
    return {"message": "Hello, Tech KG!"}


@app.get("/api")
def api_root():
    return {"message": "API is running", "version": "0.1.0"}


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()
