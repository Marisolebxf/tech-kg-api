"""企业背景关联分析 路由。"""

from fastapi import APIRouter, HTTPException

from application.enterprise_background_analysis import EnterpriseBackgroundAnalysisApplication
from biz.schemas.enterprise_background_analysis import (
    EnterpriseBackgroundAnalysisRequest,
    EnterpriseBackgroundAnalysisResponse,
)

router = APIRouter(prefix="/kg-construction/enterprise-background-analyses")
application = EnterpriseBackgroundAnalysisApplication()


@router.get("")
async def describe_enterprise_background_analysis() -> dict[str, object]:
    return application.describe()


@router.post("/analyze", response_model=EnterpriseBackgroundAnalysisResponse)
async def analyze_enterprise_background(
    req: EnterpriseBackgroundAnalysisRequest,
) -> EnterpriseBackgroundAnalysisResponse:
    try:
        return application.analyze(req.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
