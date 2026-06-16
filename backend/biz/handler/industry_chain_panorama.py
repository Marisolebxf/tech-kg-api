from fastapi import APIRouter

from application.industry_chain_panorama import IndustryChainPanoramaApplication

router = APIRouter(prefix="/kg-construction/industry-chain-panorama")
application = IndustryChainPanoramaApplication()


@router.get("")
async def describe_industry_chain_panorama() -> dict[str, object]:
    return application.describe()
