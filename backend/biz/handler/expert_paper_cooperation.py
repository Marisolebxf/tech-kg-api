from fastapi import APIRouter, HTTPException

from application.expert_paper_cooperation import ExpertPaperCooperationApplication
from biz.schema.expert_paper_cooperation import (
    ExpertPaperCooperationDemoRequest,
    ExpertPaperCooperationDemoResponse,
    ExpertPaperCooperationGraphViewResponse,
    ExpertPaperCooperationStructuredResultOnlyResponse,
)

router = APIRouter(prefix="/kg-construction/expert-paper-cooperation-relations")
application = ExpertPaperCooperationApplication()


@router.get("")
async def describe_expert_paper_cooperation() -> dict[str, object]:
    return application.describe()


@router.post("/demo/analyze", response_model=ExpertPaperCooperationDemoResponse)
async def analyze_expert_paper_cooperation_demo(
    body: ExpertPaperCooperationDemoRequest,
) -> ExpertPaperCooperationDemoResponse:
    try:
        return ExpertPaperCooperationDemoResponse(**application.analyze_demo(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"专家论文合作关系分析失败: {exc}") from exc


@router.post("/mysql/analyze", response_model=ExpertPaperCooperationDemoResponse)
async def analyze_expert_paper_cooperation_mysql(
    body: ExpertPaperCooperationDemoRequest,
) -> ExpertPaperCooperationDemoResponse:
    try:
        return ExpertPaperCooperationDemoResponse(**application.analyze_mysql_demo(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"专家论文合作关系 MySQL 分析失败: {exc}") from exc


@router.post("/demo/structured-result", response_model=ExpertPaperCooperationStructuredResultOnlyResponse)
async def analyze_expert_paper_cooperation_structured_result(
    body: ExpertPaperCooperationDemoRequest,
) -> ExpertPaperCooperationStructuredResultOnlyResponse:
    try:
        return ExpertPaperCooperationStructuredResultOnlyResponse(**application.build_structured_result_only(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"专家论文合作关系结构化结果生成失败: {exc}") from exc


@router.post("/demo/graph-view", response_model=ExpertPaperCooperationGraphViewResponse)
async def analyze_expert_paper_cooperation_graph_view(
    body: ExpertPaperCooperationDemoRequest,
) -> ExpertPaperCooperationGraphViewResponse:
    try:
        return ExpertPaperCooperationGraphViewResponse(**application.build_graph_view(body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"专家论文合作关系图谱视图生成失败: {exc}") from exc
