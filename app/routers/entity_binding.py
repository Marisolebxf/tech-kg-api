"""Entity binding API endpoints."""

import os

from fastapi import APIRouter, HTTPException, Query

from graph_db import connect, GraphDBConfig
from app.schemas.entity_binding import (
    BindingExecuteRequest,
    BindingResult,
    BindingStatsResponse,
    BindingGraphResponse,
    InitDataResponse,
    ClearResponse,
    ExpertRelationDemoResponse,
)
from app.services.entity_binding import EntityBindingService
from app.services.expert_direct_cache import get_expert_direct_relation_demo_cached

router = APIRouter(prefix="/binding", tags=["Entity Binding"])


def _get_service() -> EntityBindingService:
    """Create an EntityBindingService using GRAPH_DB_* env vars.

    Env vars (with defaults):
        GRAPH_DB_BACKEND     - "trs_graph" (default) or "neo4j"
        GRAPH_DB_URI         - "http://localhost:8090" (trs) or "bolt://localhost:7687" (neo4j)
        GRAPH_DB_DATABASE    - "entity_binding_demo" (trs) or "neo4j" (neo4j)
        GRAPH_DB_CONNECTION_TIMEOUT - 30
    """
    config = GraphDBConfig.from_env(prefix="GRAPH_DB")
    # Sensible defaults when env vars are absent
    if not os.environ.get("GRAPH_DB_BACKEND"):
        config.backend = "trs_graph"
    if config.backend == "trs_graph":
        if config.uri == "bolt://localhost:7687":  # still the neo4j default
            config.uri = os.environ.get("GRAPH_DB_URI", "http://localhost:8090")
        if config.database == "neo4j":  # still the neo4j default
            config.database = os.environ.get("GRAPH_DB_DATABASE", "entity_binding_demo")
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
        if isinstance(result, InitDataResponse):
            return result
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
        if isinstance(result, BindingGraphResponse):
            return result
        return BindingGraphResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取图数据失败: {exc}") from exc


@router.delete("/clear", response_model=ClearResponse)
def clear_bindings(clear_data: bool = Query(False)):
    try:
        service = _get_service()
        result = service.clear_bindings(clear_data=clear_data)
        service.db.close()
        if isinstance(result, ClearResponse):
            return result
        return ClearResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清除失败: {exc}") from exc


def _get_expert_direct_demo(
    data_source: str = Query("all", alias="dataSource"),
    expert_a_id: str | None = Query(None, alias="expertAId"),
    expert_b_id: str | None = Query(None, alias="expertBId"),
    institution: str | None = Query(None),
    relation_type: str = Query("direct", alias="relationType"),
    start_time: str | None = Query(None, alias="startTime"),
    end_time: str | None = Query(None, alias="endTime"),
):
    try:
        result = get_expert_direct_relation_demo_cached(
            relation_type=relation_type,
            data_source=data_source,
            expert_a_id=expert_a_id,
            expert_b_id=expert_b_id,
            institution=institution,
            start_time=start_time,
            end_time=end_time,
        )
        if isinstance(result, ExpertRelationDemoResponse):
            return result
        return ExpertRelationDemoResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取专家直接关系Demo失败: {exc}") from exc


@router.get("/expert-direct", response_model=ExpertRelationDemoResponse)
@router.get("/expert-direct-demo", response_model=ExpertRelationDemoResponse)
def get_expert_direct_demo(
    data_source: str = Query("all", alias="dataSource"),
    expert_a_id: str | None = Query(None, alias="expertAId"),
    expert_b_id: str | None = Query(None, alias="expertBId"),
    institution: str | None = Query(None),
    relation_type: str = Query("direct", alias="relationType"),
    start_time: str | None = Query(None, alias="startTime"),
    end_time: str | None = Query(None, alias="endTime"),
):
    return _get_expert_direct_demo(
        data_source=data_source,
        expert_a_id=expert_a_id,
        expert_b_id=expert_b_id,
        institution=institution,
        relation_type=relation_type,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/expert-direct-two-hop", response_model=ExpertRelationDemoResponse)
def get_expert_direct_two_hop(
    data_source: str = Query("all", alias="dataSource"),
    expert_a_id: str | None = Query(None, alias="expertAId"),
    expert_b_id: str | None = Query(None, alias="expertBId"),
    institution: str | None = Query(None),
    start_time: str | None = Query(None, alias="startTime"),
    end_time: str | None = Query(None, alias="endTime"),
):
    return _get_expert_direct_demo(
        data_source=data_source,
        expert_a_id=expert_a_id,
        expert_b_id=expert_b_id,
        institution=institution,
        relation_type="two_hop",
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/expert-direct-three-hop", response_model=ExpertRelationDemoResponse)
def get_expert_direct_three_hop(
    data_source: str = Query("all", alias="dataSource"),
    expert_a_id: str | None = Query(None, alias="expertAId"),
    expert_b_id: str | None = Query(None, alias="expertBId"),
    institution: str | None = Query(None),
    start_time: str | None = Query(None, alias="startTime"),
    end_time: str | None = Query(None, alias="endTime"),
):
    return _get_expert_direct_demo(
        data_source=data_source,
        expert_a_id=expert_a_id,
        expert_b_id=expert_b_id,
        institution=institution,
        relation_type="three_hop",
        start_time=start_time,
        end_time=end_time,
    )
