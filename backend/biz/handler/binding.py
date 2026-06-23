from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from application.expert_direct_relation import ExpertDirectRelationApplication

router = APIRouter(prefix="/binding")
application = ExpertDirectRelationApplication()


def _build_relation_response(
    relation_type: str,
    data_source: str = "all",
    expert_a_id: Optional[str] = None,
    expert_b_id: Optional[str] = None,
    institution: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> dict[str, object]:
    return application.get_relation_response(
        data_source=data_source,
        expert_a_id=expert_a_id,
        expert_b_id=expert_b_id,
        institution=institution,
        relation_type=relation_type,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/expert-direct-relation")
async def expert_direct_relation(
    dataSource: str = "all",
    expertAId: Optional[str] = None,
    expertBId: Optional[str] = None,
    institution: Optional[str] = None,
    relationType: str = "direct",
    startTime: Optional[str] = None,
    endTime: Optional[str] = None,
) -> dict[str, object]:
    return _build_relation_response(
        relation_type=relationType,
        data_source=dataSource,
        expert_a_id=expertAId,
        expert_b_id=expertBId,
        institution=institution,
        start_time=startTime,
        end_time=endTime,
    )


@router.get("/expert-direct-two-hop")
async def expert_direct_two_hop(
    dataSource: str = "all",
    expertAId: Optional[str] = None,
    expertBId: Optional[str] = None,
    institution: Optional[str] = None,
    startTime: Optional[str] = None,
    endTime: Optional[str] = None,
) -> dict[str, object]:
    return _build_relation_response(
        relation_type="two_hop",
        data_source=dataSource,
        expert_a_id=expertAId,
        expert_b_id=expertBId,
        institution=institution,
        start_time=startTime,
        end_time=endTime,
    )


@router.get("/expert-direct-three-hop")
async def expert_direct_three_hop(
    dataSource: str = "all",
    expertAId: Optional[str] = None,
    expertBId: Optional[str] = None,
    institution: Optional[str] = None,
    startTime: Optional[str] = None,
    endTime: Optional[str] = None,
) -> dict[str, object]:
    return _build_relation_response(
        relation_type="three_hop",
        data_source=dataSource,
        expert_a_id=expertAId,
        expert_b_id=expertBId,
        institution=institution,
        start_time=startTime,
        end_time=endTime,
    )
