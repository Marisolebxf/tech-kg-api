"""GraphRAG demo HTTP endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas.graphrag_demo import (
    GraphRAGDemoInitRequest,
    GraphRAGDemoInitResponse,
    GraphRAGDemoOverviewResponse,
    GraphRAGDemoQueryRequest,
    GraphRAGDemoQueryResponse,
)
from app.services.graphrag_demo import demo_overview, init_demo_graph, query_demo_graph

router = APIRouter(prefix="/graphrag/demo", tags=["GraphRAG Demo"])


@router.get("/overview", response_model=GraphRAGDemoOverviewResponse)
def get_demo_overview() -> GraphRAGDemoOverviewResponse:
    return GraphRAGDemoOverviewResponse(**demo_overview())


@router.post("/init", response_model=GraphRAGDemoInitResponse)
def init_demo(body: GraphRAGDemoInitRequest) -> GraphRAGDemoInitResponse:
    try:
        return GraphRAGDemoInitResponse(**init_demo_graph(reset=body.reset))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Neo4j demo 初始化失败: {exc}") from exc


@router.post("/query", response_model=GraphRAGDemoQueryResponse)
def run_demo_query(body: GraphRAGDemoQueryRequest) -> GraphRAGDemoQueryResponse:
    try:
        return GraphRAGDemoQueryResponse(
            **query_demo_graph(
                query=body.query,
                top_k=body.top_k,
                max_related=body.max_related,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GraphRAG demo 查询失败: {exc}") from exc
