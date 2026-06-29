from fastapi import APIRouter, HTTPException

from application.expert_paper_cooperation import ExpertPaperCooperationApplication
from biz.schema.expert_paper_cooperation import (
    ExpertPaperCooperationDemoRequest,
    ExpertPaperCooperationStructuredResultOnlyResponse,
)

router = APIRouter(prefix="/kg-construction/expert-paper-cooperation-relations")
application = ExpertPaperCooperationApplication()


@router.get("")
async def describe_expert_paper_cooperation() -> dict[str, object]:
    return application.describe()


@router.post(
    "/demo/structured-result", response_model=ExpertPaperCooperationStructuredResultOnlyResponse
)
async def analyze_expert_paper_cooperation_structured_result(
    body: ExpertPaperCooperationDemoRequest,
) -> ExpertPaperCooperationStructuredResultOnlyResponse:
    try:
        return ExpertPaperCooperationStructuredResultOnlyResponse(
            **application.build_structured_result_only(body)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"专家论文合作关系结构化结果生成失败: {exc}"
        ) from exc
