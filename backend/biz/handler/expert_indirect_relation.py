from fastapi import APIRouter, HTTPException

from application.expert_indirect_relation import ExpertIndirectRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_indirect_relation import ExpertIndirectRelationRequest

router = APIRouter(prefix="/kg-construction/expert-indirect-relations")
application = ExpertIndirectRelationApplication()


@router.get("")
def describe_expert_indirect_relation() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
def query_expert_indirect_relation(request: ExpertIndirectRelationRequest) -> ApiResponse:
    try:
        return ApiResponse(data=application.query(**request.model_dump()))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
