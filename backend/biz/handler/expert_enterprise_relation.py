from fastapi import APIRouter

from application.expert_enterprise_relation import ExpertEnterpriseRelationApplication

router = APIRouter(prefix="/kg-construction/expert-enterprise-relations")
application = ExpertEnterpriseRelationApplication()


@router.get("")
async def describe_expert_enterprise_relation() -> dict[str, object]:
    return application.describe()
