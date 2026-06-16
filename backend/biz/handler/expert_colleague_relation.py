from fastapi import APIRouter

from application.expert_colleague_relation import ExpertColleagueRelationApplication

router = APIRouter(prefix="/kg-construction/expert-colleague-relations")
application = ExpertColleagueRelationApplication()


@router.get("")
async def describe_expert_colleague_relation() -> dict[str, object]:
    return application.describe()
