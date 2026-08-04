from fastapi import APIRouter, HTTPException

from application.expert_alumni_relation import ExpertAlumniRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_alumni_relation import ExpertAlumniRelationRequest

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
application = ExpertAlumniRelationApplication()


@router.get("")
def describe_expert_alumni_relation() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
def query_expert_alumni_relation(request: ExpertAlumniRelationRequest) -> ApiResponse:
    try:
        return ApiResponse(data=application.query(**request.model_dump()))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
