from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from application.industry_chain_panorama import IndustryChainPanoramaApplication
from biz.schema.industry_chain_panorama import (
    MAX_KEY_ENTITIES,
    IndustryChainPanoramaQueryRequest,
    IndustryChainPanoramaQueryResponse,
)

router = APIRouter(prefix="/kg-construction/industry-chain-panorama")
application = IndustryChainPanoramaApplication()


@router.get("")
async def describe_industry_chain_panorama() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=IndustryChainPanoramaQueryResponse)
async def query_industry_chain_panorama(
    body: IndustryChainPanoramaQueryRequest,
) -> dict[str, object]:
    return await application.query(
        industry=body.industry,
        anchor_id=body.anchorId,
        depth=body.depth,
        top_k=min(body.topK, MAX_KEY_ENTITIES),
        relation_types=body.relationTypes,
        refresh=body.refresh,
    )


@router.get("/query", response_model=IndustryChainPanoramaQueryResponse)
async def query_industry_chain_panorama_get(
    industry: Annotated[str | None, Query()] = None,
    anchor_id: Annotated[str | None, Query(alias="anchorId")] = None,
    depth: Annotated[int, Query(ge=1, le=3)] = 2,
    top_k: Annotated[int, Query(ge=1, alias="topK")] = 5,
    relation_types: Annotated[list[str] | None, Query(alias="relationTypes")] = None,
    refresh: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    # GET 与 POST 共用同一套入参校验，避免绕过长度/异常字符限制
    try:
        body = IndustryChainPanoramaQueryRequest(
            industry=industry,
            anchorId=anchor_id,
            depth=depth,
            topK=top_k,
            relationTypes=relation_types,
            refresh=refresh,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return await application.query(
        industry=body.industry,
        anchor_id=body.anchorId,
        depth=body.depth,
        top_k=min(body.topK, MAX_KEY_ENTITIES),
        relation_types=body.relationTypes,
        refresh=body.refresh,
    )
