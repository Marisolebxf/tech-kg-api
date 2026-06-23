"""Scholar paper cooperation demo endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas.scholar_paper_cooperation import (
    ScholarPaperCooperationDemoRequest,
    ScholarPaperCooperationDemoResponse,
    ScholarPaperCooperationGraphViewResponse,
    ScholarPaperCooperationStructuredResultOnlyResponse,
)
from app.services.scholar_paper_cooperation import analyze_demo, analyze_mysql_demo, build_neo4j_graph_view, build_structured_result_only

router = APIRouter(prefix="/scholar-paper-cooperation", tags=["科技专家论文合作关系"])


@router.post(
    "/demo/analyze",
    response_model=ScholarPaperCooperationDemoResponse,
    summary="科技专家论文合作关系 Demo",
    description="用于在 FastAPI /docs 中测试科技专家论文合作关系模块的输入参数和完整输出。当前接口读取 MySQL techkg 库中的 scholar/paper/paper_author/venue/scholar_paper_cooperation 数据。",
)
def analyze_paper_cooperation_demo(
    body: ScholarPaperCooperationDemoRequest,
) -> ScholarPaperCooperationDemoResponse:
    try:
        return ScholarPaperCooperationDemoResponse(**analyze_demo(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MySQL demo 查询失败: {exc}") from exc


@router.post(
    "/demo/structured-result",
    response_model=ScholarPaperCooperationStructuredResultOnlyResponse,
    summary="科技专家论文合作关系结构化结果 Demo",
    description="用于在 FastAPI /docs 中测试仅返回 structuredResult 的科技专家论文合作关系接口，适合前端结构化结果/API 示例联动展示。",
)
def analyze_paper_cooperation_structured_result_only(
    body: ScholarPaperCooperationDemoRequest,
) -> ScholarPaperCooperationStructuredResultOnlyResponse:
    try:
        return ScholarPaperCooperationStructuredResultOnlyResponse(**build_structured_result_only(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MySQL structuredResult 查询失败: {exc}") from exc


@router.post(
    "/mysql/analyze",
    response_model=ScholarPaperCooperationDemoResponse,
    summary="科技专家论文合作关系 MySQL Demo",
    description="用于在 FastAPI /docs 中测试从 MySQL techkg 库查询科技专家论文合作关系。该接口与 /demo/analyze 使用同一套 MySQL 聚合逻辑。",
)
def analyze_paper_cooperation_mysql(
    body: ScholarPaperCooperationDemoRequest,
) -> ScholarPaperCooperationDemoResponse:
    try:
        return ScholarPaperCooperationDemoResponse(**analyze_mysql_demo(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MySQL demo 查询失败: {exc}") from exc


@router.post(
    "/demo/graph-view",
    response_model=ScholarPaperCooperationGraphViewResponse,
    summary="科技专家论文合作关系图谱视图 Demo",
    description="从 MySQL 合作论文数据生成图谱视图，返回适合前端绘制关系界面的 nodes、edges、metrics。",
)
def paper_cooperation_graph_view(
    body: ScholarPaperCooperationDemoRequest,
) -> ScholarPaperCooperationGraphViewResponse:
    try:
        return ScholarPaperCooperationGraphViewResponse(**build_neo4j_graph_view(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MySQL 图谱视图查询失败: {exc}") from exc
