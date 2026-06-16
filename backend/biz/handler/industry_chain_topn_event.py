from fastapi import APIRouter

from application.industry_chain_topn_event import IndustryChainTopNEventApplication

router = APIRouter(prefix="/kg-construction/industry-chain-topn-event-relations")
application = IndustryChainTopNEventApplication()


@router.get("")
async def describe_industry_chain_topn_event() -> dict[str, object]:
    return application.describe()
