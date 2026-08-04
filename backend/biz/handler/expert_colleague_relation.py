from fastapi import APIRouter, HTTPException

from application.expert_colleague_relation import ExpertColleagueRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_colleague_relation import ExpertColleagueRelationRequest

router = APIRouter(prefix="/kg-construction/expert-colleague-relations")
application = ExpertColleagueRelationApplication()


@router.get("")
def describe_expert_colleague_relation() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
def query_expert_colleague_relation(request: ExpertColleagueRelationRequest) -> ApiResponse:
    try:
        return ApiResponse(data=application.query(**request.model_dump()))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
