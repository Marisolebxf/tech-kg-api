"""科技两点合作成果 路由。"""

from fastapi import APIRouter

from application.expert_cooperation_achievement import ExpertCooperationAchievementApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_cooperation_achievement import CooperationAchievementQueryRequest

router = APIRouter(prefix="/kg-construction/expert-cooperation-achievements")
application = ExpertCooperationAchievementApplication()


@router.get("")
async def describe_expert_cooperation_achievement() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
async def query_expert_cooperation_achievement(
    body: CooperationAchievementQueryRequest,
) -> ApiResponse:
    try:
        result = application.query(
            source_expert_id=body.sourceExpertId,
            target_expert_id=body.targetExpertId,
            achievement_types=body.achievementTypes,
            time_range_start=body.timeRangeStart,
            time_range_end=body.timeRangeEnd,
            limit_per_type=body.limitPerType,
        )
        return ApiResponse(data=result)
    except ValueError as exc:
        return ApiResponse(code=400, success=False, msg=str(exc))
    except KeyError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))
