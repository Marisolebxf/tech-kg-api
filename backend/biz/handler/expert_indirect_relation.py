from fastapi import APIRouter

from application.expert_indirect_relation import ExpertIndirectRelationApplication

router = APIRouter(prefix="/kg-construction/expert-indirect-relations")
application = ExpertIndirectRelationApplication()


@router.get("")
async def describe_expert_indirect_relation() -> dict[str, object]:
    return application.describe()
