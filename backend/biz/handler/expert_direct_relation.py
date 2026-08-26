from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from application.expert_direct_relation import ExpertDirectRelationApplication
from biz.schema.expert_direct_relation import (
    MAX_QUERY_LIMIT,
    DataSource,
    ExpertDirectRelationQueryRequest,
    ExpertDirectRelationQueryResponse,
)

router = APIRouter(prefix="/kg-construction/expert-direct-relations")
application = ExpertDirectRelationApplication()


@router.get("")
async def describe_expert_direct_relation() -> dict[str, object]:
    return application.describe()


@router.post("/query", response_model=ExpertDirectRelationQueryResponse)
async def query_expert_direct_relation(
    body: ExpertDirectRelationQueryRequest,
) -> dict[str, object]:
    return await application.query(
        data_source=body.dataSource,
        expert_a_id=body.expertAId,
        expert_b_id=body.expertBId,
        institution=body.institution,
        start_time=body.startTime,
        end_time=body.endTime,
        limit=body.limit,
    )


@router.get("/query", response_model=ExpertDirectRelationQueryResponse)
async def query_expert_direct_relation_get(
    dataSource: Annotated[DataSource, Query()] = "all",
    expertAId: Annotated[str | None, Query()] = None,
    expertBId: Annotated[str | None, Query()] = None,
    institution: Annotated[str | None, Query()] = None,
    startTime: Annotated[str | None, Query()] = None,
    endTime: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 10,
) -> dict[str, object]:
    # GET 与 POST 共用同一套入参校验，避免绕过长度/异常字符/未来时间限制
    try:
        body = ExpertDirectRelationQueryRequest(
            dataSource=dataSource,
            expertAId=expertAId,
            expertBId=expertBId,
            institution=institution,
            startTime=startTime,
            endTime=endTime,
            limit=limit,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return await application.query(
        data_source=body.dataSource,
        expert_a_id=body.expertAId,
        expert_b_id=body.expertBId,
        institution=body.institution,
        start_time=body.startTime,
        end_time=body.endTime,
        limit=min(body.limit, MAX_QUERY_LIMIT),
    )
