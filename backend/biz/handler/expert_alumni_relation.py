"""科技专家校友关系 路由。"""

from fastapi import APIRouter

from application.expert_alumni_relation import ExpertAlumniRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_alumni_relation import AlumniRelationQueryRequest

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
application = ExpertAlumniRelationApplication()


@router.get("")
async def describe_expert_alumni_relation() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
async def query_expert_alumni_relation(body: AlumniRelationQueryRequest) -> ApiResponse:
    try:
        result = application.query(
            expert_id=body.expertId,
            target_expert_id=body.targetExpertId,
            school=body.school,
            education_stage=body.educationStage,
            limit=body.limit,
        )
        return ApiResponse(data=result)
    except ValueError as exc:
        return ApiResponse(code=400, success=False, msg=str(exc))
    except KeyError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))
