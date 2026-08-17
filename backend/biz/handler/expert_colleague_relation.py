from fastapi import APIRouter, Request
from httpx import ASGITransport, AsyncClient

from application.expert_colleague_relation import ExpertColleagueRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_colleague_relation import (
    ExpertColleagueRelationData,
    ExpertColleagueRelationRequest,
)

router = APIRouter(prefix="/kg-construction/expert-colleague-relations", tags=["expert-colleague"])
service_router = APIRouter(
    prefix="/kg-service/expert-colleague-relation", tags=["expert-colleague"]
)
application = ExpertColleagueRelationApplication()


@router.get("")
async def describe_expert_colleague_relation() -> dict[str, object]:
    return application.describe()


@service_router.post("", response_model=ApiResponse)
async def query_expert_colleague_relation(
    body: ExpertColleagueRelationRequest,
    request: Request,
) -> ApiResponse:
    """组合公开查图 API 推理专家同事关系。"""
    try:
        async with AsyncClient(
            transport=ASGITransport(app=request.app),
            base_url="http://fastapi-internal",
        ) as client:
            data = await application.query(
                client,
                expert_id=body.expertId,
                organization=body.organization,
                department=body.department,
                overlap_period=body.overlapPeriod,
                limit=body.limit,
                space=body.space,
            )
        validated = ExpertColleagueRelationData.model_validate(data)
        return ApiResponse(data=validated.model_dump())
    except LookupError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))
    except Exception as exc:
        return ApiResponse(code=500, success=False, msg=f"专家同事关系查询失败: {exc}")
