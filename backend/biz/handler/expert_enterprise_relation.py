"""专家-企业关系构建 路由。"""

from fastapi import APIRouter, HTTPException

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
    try:
        return application.build(req.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
