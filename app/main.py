from fastapi import FastAPI

from app.routers.entity_linking import router as entity_linking_router

app = FastAPI(
    title="Tech KG API",
    description="亿级知识图谱 API 接口",
    version="0.1.0",
)

app.include_router(entity_linking_router, prefix="/api/v1")


@app.get("/hello")
def hello():
    return {"message": "Hello, Tech KG!"}


@app.get("/api")
def api_root():
    return {"message": "API is running", "version": "0.1.0"}
