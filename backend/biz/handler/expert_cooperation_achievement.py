from fastapi import APIRouter

from application.expert_cooperation_achievement import ExpertCooperationAchievementApplication

router = APIRouter(prefix="/kg-construction/expert-cooperation-achievements")
application = ExpertCooperationAchievementApplication()


@router.get("")
async def describe_expert_cooperation_achievement() -> dict[str, object]:
    return application.describe()
