"""专家企业关系挖掘 路由。"""

from fastapi import APIRouter, HTTPException

from application.expert_enterprise_mining import ExpertEnterpriseMiningApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_enterprise_mining import ExpertEnterpriseMiningRequest

router = APIRouter(prefix="/kg-construction/expert-enterprise-mining")
application = ExpertEnterpriseMiningApplication()


@router.get("")
def describe_expert_enterprise_mining() -> dict[str, object]:
    return application.describe()


@router.post("/mine", response_model=ApiResponse)
def mine_expert_enterprise_relation(req: ExpertEnterpriseMiningRequest) -> ApiResponse:
    try:
        result = application.mine(req.model_dump())
        return ApiResponse(data=result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
