"""专家企业关系挖掘 路由。"""

from fastapi import APIRouter, Depends

from application.expert_enterprise_mining import ExpertEnterpriseMiningApplication
from biz.dependencies.auth import require_platform_admin
from biz.schemas.common import ApiResponse
from biz.schemas.expert_enterprise_mining import (
    ExpertEnterpriseMiningRequest,
    ExpertEnterpriseQueryRequest,
)

router = APIRouter(prefix="/kg-construction/expert-enterprise-mining")
application = ExpertEnterpriseMiningApplication()


@router.get("")
async def describe_expert_enterprise_mining() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
async def query_expert_enterprise_relation(req: ExpertEnterpriseQueryRequest) -> ApiResponse:
    try:
        return ApiResponse(data=application.query_existing(req.model_dump()))
    except KeyError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))


@router.post(
    "/mine",
    response_model=ApiResponse,
    dependencies=[Depends(require_platform_admin)],
)
async def mine_expert_enterprise_relation(req: ExpertEnterpriseMiningRequest) -> ApiResponse:
    try:
        result = application.mine(req.model_dump())
        return ApiResponse(data=result)
    except KeyError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))
