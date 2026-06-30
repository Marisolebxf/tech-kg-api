from fastapi import APIRouter, Query

from biz.schema.expert_direct_relation import (
    DataSource,
    ExpertDirectRelationQueryRequest,
    ExpertDirectRelationQueryResponse,
    MAX_QUERY_LIMIT,
)

from application.expert_direct_relation import ExpertDirectRelationApplication

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
    dataSource: DataSource = Query(default="all"),
    expertAId: str | None = Query(default=None),
    expertBId: str | None = Query(default=None),
    institution: str | None = Query(default=None),
    startTime: str | None = Query(default=None),
    endTime: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1),
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
