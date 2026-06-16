from fastapi import APIRouter, HTTPException

from application.kg_construction import KGConstructionApplication

router = APIRouter(prefix="/kg-construction", tags=["knowledge-graph-construction"])
application = KGConstructionApplication()


@router.get("/modules")
async def list_modules() -> dict[str, object]:
    return {"items": application.list_modules()}


@router.get("/modules/{module_code}")
async def get_module(module_code: str) -> dict[str, object]:
    module = application.get_module(module_code)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    return module
