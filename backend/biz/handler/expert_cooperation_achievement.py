from fastapi import APIRouter, HTTPException

from application.expert_cooperation_achievement import ExpertCooperationAchievementApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_cooperation_achievement import ExpertCooperationAchievementRequest

router = APIRouter(prefix="/kg-construction/expert-cooperation-achievements")
application = ExpertCooperationAchievementApplication()


@router.get("")
def describe_expert_cooperation_achievement() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
def query_expert_cooperation_achievement(
    request: ExpertCooperationAchievementRequest,
) -> ApiResponse:
    try:
        return ApiResponse(data=application.query(**request.model_dump()))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
