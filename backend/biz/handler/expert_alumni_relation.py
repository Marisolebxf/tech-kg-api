from fastapi import APIRouter

from application.expert_alumni_relation import ExpertAlumniRelationApplication

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
application = ExpertAlumniRelationApplication()


@router.get("")
async def describe_expert_alumni_relation() -> dict[str, object]:
    return application.describe()
