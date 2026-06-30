from typing import Annotated

from fastapi import APIRouter, Query

from application.expert_direct_relation import ExpertDirectRelationApplication
from biz.schema.expert_direct_relation import (
    DataSource,
    ExpertDirectRelationQueryRequest,
    ExpertDirectRelationQueryResponse,
    MAX_QUERY_LIMIT,
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
    return application.query(
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
    return application.query(
        data_source=dataSource,
        expert_a_id=expertAId,
        expert_b_id=expertBId,
        institution=institution,
        start_time=startTime,
        end_time=endTime,
        limit=min(limit, MAX_QUERY_LIMIT),
    )
