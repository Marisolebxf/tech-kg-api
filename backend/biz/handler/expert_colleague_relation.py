import json

from fastapi import APIRouter, Request
from fastapi.responses import Response
from httpx import ASGITransport, AsyncClient

from application.expert_colleague_relation import ExpertColleagueRelationApplication
from biz.schemas.common import ApiResponse
from biz.schemas.expert_colleague_relation import (
    ExpertColleagueRelationData,
    ExpertColleagueRelationRequest,
)
from infra.result_cache import get_cached_json, set_cached_json

router = APIRouter(prefix="/kg-construction/expert-colleague-relations", tags=["expert-colleague"])
service_router = APIRouter(
    prefix="/kg-service/expert-colleague-relation", tags=["expert-colleague"]
)
application = ExpertColleagueRelationApplication()


def _json_response(payload: ApiResponse) -> Response:
    return Response(
        content=json.dumps(payload.model_dump(), ensure_ascii=False), media_type="application/json"
    )


def _cache_key(body: ExpertColleagueRelationRequest) -> str:
    overlap = (
        f"{body.startTime}至{body.endTime}"
        if body.startTime and body.endTime
        else body.overlapPeriod
    )
    return (
        f"{body.expertId}|{body.targetExpertId}|{body.organization}|{body.department}|"
        f"{overlap}|{body.teamOrProject}|{tuple(body.achievementTypes or [])}|"
        f"{body.minConfidence}|{body.limit}|{body.offset}"
    )


@router.get("")
async def describe_expert_colleague_relation() -> dict[str, object]:
    return application.describe()


@service_router.post("")
async def query_expert_colleague_relation(
    body: ExpertColleagueRelationRequest,
    request: Request,
) -> Response:
    """组合公开查图 API 推理专家同事关系。"""
    key = _cache_key(body)
    cached = get_cached_json(key)
    if cached is not None:
        # 命中预序列化 JSON，跳过 ASGITransport 自调用 + model_dump 序列化，避免 500 并发互锁
        return Response(content=cached, media_type="application/json")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=request.app),
            base_url="http://fastapi-internal",
        ) as client:
            data = await application.query(
                client,
                expert_id=body.expertId,
                target_expert_id=body.targetExpertId,
                organization=body.organization,
                department=body.department,
                overlap_period=(
                    f"{body.startTime} 至 {body.endTime}"
                    if body.startTime and body.endTime
                    else body.overlapPeriod
                ),
                team_or_project=body.teamOrProject,
                achievement_types=body.achievementTypes,
                min_confidence=body.minConfidence,
                limit=body.limit,
                offset=body.offset,
            )
        validated = ExpertColleagueRelationData.model_validate(data)
        resp = ApiResponse(data=validated.model_dump())
        body_json = json.dumps(resp.model_dump(), ensure_ascii=False)
        set_cached_json(key, body_json)
        return Response(content=body_json, media_type="application/json")
    except LookupError as exc:
        return _json_response(ApiResponse(code=404, success=False, msg=str(exc)))
    except Exception as exc:  # noqa: BLE001
        return _json_response(
            ApiResponse(code=500, success=False, msg=f"专家同事关系查询失败: {exc}")
        )
