"""角色与合作详情标注 路由。"""

from fastapi import APIRouter

from application.relation_detail_annotation import RelationDetailAnnotationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.relation_detail_annotation import RelationDetailAnnotationRequest

router = APIRouter(prefix="/kg-construction/relation-detail-annotations")
application = RelationDetailAnnotationApplication()


@router.get("")
async def describe_relation_detail_annotation() -> dict[str, object]:
    return application.describe()


@router.post("/annotate", response_model=ApiResponse)
async def annotate_relation_detail(req: RelationDetailAnnotationRequest) -> ApiResponse:
    try:
        result = application.annotate(req.model_dump())
        return ApiResponse(data=result)
    except KeyError as exc:
        return ApiResponse(code=404, success=False, msg=str(exc))
