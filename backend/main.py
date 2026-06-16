from fastapi import FastAPI

from biz.router.register import register_routers

app = FastAPI(
    title="Tech KG API",
    description="Backend service for the technology knowledge graph.",
    version="0.1.0",
)

register_routers(app)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
