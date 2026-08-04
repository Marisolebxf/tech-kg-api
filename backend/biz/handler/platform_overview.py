"""平台首页总览路由。"""

from fastapi import APIRouter

from application.platform_overview import PlatformOverviewApplication
from biz.schemas.platform_overview import PlatformOverviewResponse

router = APIRouter(prefix="/platform/overview", tags=["platform-overview"])
application = PlatformOverviewApplication()


@router.get("", response_model=PlatformOverviewResponse)
def get_platform_overview() -> PlatformOverviewResponse:
    return PlatformOverviewResponse(data=application.get_overview())
