"""企业背景关联分析 路由。"""

from fastapi import APIRouter

from application.enterprise_background_analysis import EnterpriseBackgroundAnalysisApplication
from biz.schemas.common import ApiResponse
from biz.schemas.enterprise_background_analysis import EnterpriseBackgroundAnalysisRequest

router = APIRouter(prefix="/kg-construction/enterprise-background-analyses")
application = EnterpriseBackgroundAnalysisApplication()


@router.get("")
async def describe_enterprise_background_analysis() -> dict[str, object]:
    return application.describe()


@router.post("/analyze", response_model=ApiResponse)
async def analyze_enterprise_background(req: EnterpriseBackgroundAnalysisRequest) -> ApiResponse:
    try:
        result = application.analyze(req.model_dump())
        return ApiResponse(data=result)
    except KeyError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))
