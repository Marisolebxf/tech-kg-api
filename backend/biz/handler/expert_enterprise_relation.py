"""专家-企业关系构建 路由。"""

from fastapi import APIRouter, HTTPException

from application.expert_enterprise_relation import ExpertEnterpriseRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_enterprise_relation import ExpertEnterpriseBuildRequest

router = APIRouter(prefix="/kg-construction/expert-enterprise-relations")
application = ExpertEnterpriseRelationApplication()


@router.get("")
def describe_expert_enterprise_relation() -> dict[str, object]:
    return application.describe()


@router.post("/build", response_model=ApiResponse)
def build_expert_enterprise_relation(req: ExpertEnterpriseBuildRequest) -> ApiResponse:
    try:
        result = application.build(req.model_dump())
        return ApiResponse(data=result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
