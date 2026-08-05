"""科技专家校友关系 路由。"""

from fastapi import APIRouter

from application.expert_alumni_relation import ExpertAlumniRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_alumni_relation import AlumniRelationQueryRequest

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
# 兼容前端/文档遗留路径，避免页面或 curl 打到 404
legacy_router = APIRouter(prefix="/kg-service/expert-alumni-relation")
application = ExpertAlumniRelationApplication()


async def _describe() -> dict[str, object]:
    return application.describe()


async def _query(body: AlumniRelationQueryRequest) -> ApiResponse:
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


@router.get("")
async def describe_expert_alumni_relation() -> dict[str, object]:
    return await _describe()


@router.post("/query", response_model=ApiResponse)
async def query_expert_alumni_relation(body: AlumniRelationQueryRequest) -> ApiResponse:
    return await _query(body)


@legacy_router.get("")
async def legacy_describe_expert_alumni_relation() -> dict[str, object]:
    return await _describe()


@legacy_router.post("", response_model=ApiResponse)
async def legacy_query_expert_alumni_relation(body: AlumniRelationQueryRequest) -> ApiResponse:
    return await _query(body)
