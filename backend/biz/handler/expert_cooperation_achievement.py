"""科技两点合作成果 路由。"""

from fastapi import APIRouter, HTTPException

from application.expert_cooperation_achievement import ExpertCooperationAchievementApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_cooperation_achievement import CooperationAchievementQueryRequest

router = APIRouter(prefix="/kg-construction/expert-cooperation-achievements")
legacy_router = APIRouter(prefix="/kg-service/two-point-achievements")
application = ExpertCooperationAchievementApplication()


async def _describe() -> dict[str, object]:
    return application.describe()


def _query(body: CooperationAchievementQueryRequest) -> ApiResponse:
    # service.query 是同步实现（直连 infra graph client）；用 def 让 FastAPI 放进线程池，
    # 每个 worker 可并发处理多请求，而不是 async 阻塞事件循环。
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
async def describe_expert_cooperation_achievement() -> dict[str, object]:
    return await _describe()


@router.post("/query", response_model=ApiResponse)
def query_expert_cooperation_achievement(
    body: CooperationAchievementQueryRequest,
) -> ApiResponse:
    return _query(body)


@legacy_router.get("")
async def legacy_describe_two_point_achievements() -> dict[str, object]:
    return await _describe()


@legacy_router.post("", response_model=ApiResponse)
def legacy_query_two_point_achievements(
    body: CooperationAchievementQueryRequest,
) -> ApiResponse:
    return _query(body)
