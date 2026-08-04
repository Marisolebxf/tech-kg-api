"""角色与合作详情标注 路由。"""

from fastapi import APIRouter, HTTPException

from application.relation_detail_annotation import RelationDetailAnnotationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.relation_detail_annotation import RelationDetailAnnotationRequest

router = APIRouter(prefix="/kg-construction/relation-detail-annotations")
application = RelationDetailAnnotationApplication()


@router.get("")
def describe_relation_detail_annotation() -> dict[str, object]:
    return application.describe()


@router.post("/annotate", response_model=ApiResponse)
def annotate_relation_detail(req: RelationDetailAnnotationRequest) -> ApiResponse:
    try:
        result = application.annotate(req.model_dump())
        return ApiResponse(data=result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
