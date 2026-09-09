"""科技专家校友关系 路由。"""

from fastapi import APIRouter

from application.expert_alumni_relation import ExpertAlumniRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_alumni_relation import AlumniRelationQueryRequest

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
# 兼容前端/文档遗留路径，避免页面或 curl 打到 404
legacy_router = APIRouter(prefix="/kg-service/expert-alumni-relation")
application = ExpertAlumniRelationApplication()


def _describe() -> dict[str, object]:
    return application.describe()


def _query(body: AlumniRelationQueryRequest) -> ApiResponse:
    # service.query 是同步实现（直连 infra graph client）；用 def 让 FastAPI 放进线程池，
    # 每个 worker 可并发处理 ~40 个请求，而不是 async 阻塞事件循环只跑 1 个。
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
        return ApiResponse(
            code=400,
            success=False,
            data=None,
            msg=str(exc.args[0]) if exc.args else str(exc),
        )
    except KeyError as exc:
        return ApiResponse(
            code=404,
            success=False,
            data=None,
            msg=str(exc.args[0]) if exc.args else str(exc),
        )


@router.get("")
def describe_expert_alumni_relation() -> dict[str, object]:
    return _describe()


@router.post("/query")
def query_expert_alumni_relation(body: AlumniRelationQueryRequest) -> ApiResponse:
    return _query(body)


@legacy_router.get("")
def legacy_describe_expert_alumni_relation() -> dict[str, object]:
    return _describe()


@legacy_router.post("")
def legacy_query_expert_alumni_relation(body: AlumniRelationQueryRequest) -> ApiResponse:
    return _query(body)
