"""专家-企业关系构建 路由。"""

from fastapi import APIRouter

from application.expert_enterprise_relation import ExpertEnterpriseRelationApplication
from biz.schemas.expert_enterprise_relation import (
    ExpertEnterpriseBuildRequest,
    ExpertEnterpriseBuildResponse,
)

router = APIRouter(prefix="/kg-construction/expert-enterprise-relations")
application = ExpertEnterpriseRelationApplication()


@router.get("")
async def describe_expert_enterprise_relation() -> dict[str, object]:
    return application.describe()


@router.post("/build", response_model=ExpertEnterpriseBuildResponse)
async def build_expert_enterprise_relation(
    req: ExpertEnterpriseBuildRequest,
) -> ExpertEnterpriseBuildResponse:
    return application.build(req.model_dump())
