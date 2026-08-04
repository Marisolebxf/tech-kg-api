from fastapi import APIRouter, HTTPException

from application.industry_chain_topn_event import IndustryChainTopNEventApplication
from biz.schemas.common import ApiResponse
from biz.schemas.industry_chain_topn_event import IndustryChainTopNEventRequest

router = APIRouter(prefix="/kg-construction/industry-chain-topn-event-relations")
application = IndustryChainTopNEventApplication()


@router.get("")
def describe_industry_chain_topn_event() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ApiResponse)
def query_industry_chain_topn_event(request: IndustryChainTopNEventRequest) -> ApiResponse:
    try:
        return ApiResponse(data=application.query(**request.model_dump()))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
