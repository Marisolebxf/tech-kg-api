"""角色与合作详情标注 路由。"""

from fastapi import APIRouter, HTTPException

from application.relation_detail_annotation import RelationDetailAnnotationApplication
from biz.schemas.relation_detail_annotation import (
    RelationDetailAnnotationRequest,
    RelationDetailAnnotationResponse,
)

router = APIRouter(prefix="/kg-construction/relation-detail-annotations")
application = RelationDetailAnnotationApplication()


@router.get("")
async def describe_relation_detail_annotation() -> dict[str, object]:
    return application.describe()


@router.post("/annotate", response_model=RelationDetailAnnotationResponse)
async def annotate_relation_detail(
    req: RelationDetailAnnotationRequest,
) -> RelationDetailAnnotationResponse:
    try:
        return application.annotate(req.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
