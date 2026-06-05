"""Entity binding API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from graph_db import connect, GraphDBConfig
from app.schemas.entity_binding import (
    BindingExecuteRequest,
    BindingResult,
    BindingStatsResponse,
    BindingGraphResponse,
    InitDataResponse,
    ClearResponse,
)
from app.services.entity_binding import EntityBindingService

router = APIRouter(prefix="/binding", tags=["Entity Binding"])


def _get_service() -> EntityBindingService:
    """Create an EntityBindingService with TRS Graph backend."""
    config = GraphDBConfig(
        backend="trs_graph",
        uri="http://localhost:8090",
        database="entity_binding_demo",
        connection_timeout=30,
    )
    db = connect(config)
    try:
        return EntityBindingService(db)
    except Exception:
        db.close()
        raise


@router.post("/init-data", response_model=InitDataResponse)
def init_data():
    try:
        service = _get_service()
        result = service.init_data()
        service.db.close()
        return InitDataResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"初始化数据失败: {exc}") from exc


@router.post("/execute")
def execute_binding(body: BindingExecuteRequest):
    try:
        service = _get_service()
        if body.binding_type == "all":
            result = service.bind_all()
        elif body.binding_type == "talent_paper":
            result = service.bind_talent_paper().model_dump()
        elif body.binding_type == "talent_patent":
            result = service.bind_talent_patent().model_dump()
        elif body.binding_type == "org_org":
            result = service.bind_org_org().model_dump()
        else:
            service.db.close()
            raise HTTPException(status_code=400, detail=f"Unknown binding_type: {body.binding_type}")
        service.db.close()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"绑定执行失败: {exc}") from exc


@router.get("/stats")
def get_stats():
    try:
        service = _get_service()
        result = service.get_binding_stats()
        service.db.close()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {exc}") from exc


@router.get("/detail")
def get_detail(binding_type: str = Query("talent_paper"), limit: int = Query(100), offset: int = Query(0)):
    try:
        service = _get_service()
        result = service.get_binding_detail(binding_type, limit=limit, offset=offset)
        service.db.close()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取详情失败: {exc}") from exc


@router.get("/graph", response_model=BindingGraphResponse)
def get_graph():
    try:
        service = _get_service()
        result = service.get_binding_graph()
        service.db.close()
        return BindingGraphResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取图数据失败: {exc}") from exc


@router.delete("/clear", response_model=ClearResponse)
def clear_bindings(clear_data: bool = Query(False)):
    try:
        service = _get_service()
        result = service.clear_bindings(clear_data=clear_data)
        service.db.close()
        return ClearResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清除失败: {exc}") from exc
