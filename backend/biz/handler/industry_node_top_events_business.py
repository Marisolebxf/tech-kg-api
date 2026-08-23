"""科技产业链点 TOP-N 事件关系业务（九大业务之一）HTTP 端点。

对齐前端 service-modules.ts 的 industry-chain-event 契约：
POST /api/v1/kg-service/industry-node-top-events，请求 {chain_node_id, top_n, event_type,
time_range}。围绕产业链节点，收集关联企业的事件，按影响力排序取 TOP-N，构建事件↔专家关联，
给出风险等级与影响分析。全部数据经 graph-search 查图 API 获取，不直连图、不直连 MySQL。

命中缓存时直接返回预序列化 JSON（Response），跳过 FastAPI jsonable_encoder，
消除 500 并发下响应序列化阻塞事件循环的瓶颈。
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import Response

from biz.schemas.common import ApiResponse
from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest
from infra.result_cache import get_cached_json, set_cached_json
from service.industry_node_top_events_business import IndustryNodeTopEventsService

router = APIRouter(prefix="/kg-service", tags=["kg-service"])
service = IndustryNodeTopEventsService()


def _json_response(payload: ApiResponse) -> Response:
    return Response(
        content=json.dumps(payload.model_dump(), ensure_ascii=False), media_type="application/json"
    )


def _cache_key(req: IndustryNodeTopEventsRequest) -> str:
    return f"{req.chain_node_id}|{req.top_n}|{req.event_type}|{req.time_range}|{req.max_orgs}"


@router.get("/industry-node-top-events")
async def describe_industry_node_top_events() -> dict[str, object]:
    return {
        "business": "科技产业链点TOP-N事件关系",
        "endpoint": "POST /api/v1/kg-service/industry-node-top-events",
        "request": ["chain_node_id(必)", "top_n", "event_type", "time_range"],
        "data_sources": [
            "graph: IndustryNode(BELONGS_TO_NODE)→Organization(INVOLVED_IN)→Event",
            "graph: Organization←EXECUTIVE_OF/LEGAL_REP_OF←Person(专家)",
            "graph: IndustryNode←HAS_NODE←IndustryChain(产业链名)",
        ],
        "impact_factors": ["event_type 风险权重", "事件金额", "时间新鲜度", "企业 chain_score"],
        "data_gaps": [
            "事件类型多为财务/风险/招投标，无独立的'技术突破'事件类型",
            "链节点关联企业的 governance 边未全覆盖（部分上市企业高管没入图），experts 可能为 0",
        ],
    }


@router.post("/industry-node-top-events")
async def run_industry_node_top_events(req: IndustryNodeTopEventsRequest) -> Response:
    key = _cache_key(req)
    cached = get_cached_json(key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")
    try:
        data = await service.run(req)
        body = json.dumps(ApiResponse(data=data.model_dump()).model_dump(), ensure_ascii=False)
        set_cached_json(key, body)
        return Response(content=body, media_type="application/json")
    except KeyError as exc:  # noqa: BLE001
        return _json_response(ApiResponse(code=404, success=False, msg=str(exc)))
    except Exception as exc:  # noqa: BLE001
        return _json_response(
            ApiResponse(code=500, success=False, msg=f"产业链点TOP-N事件业务执行失败: {exc}")
        )
