from fastapi import APIRouter

from application.expert_paper_cooperation import ExpertPaperCooperationApplication

router = APIRouter(prefix="/kg-construction/expert-paper-cooperation-relations")
application = ExpertPaperCooperationApplication()


@router.get("")
async def describe_expert_paper_cooperation() -> dict[str, object]:
    return application.describe()
