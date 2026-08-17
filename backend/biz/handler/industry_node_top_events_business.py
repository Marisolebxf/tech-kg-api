"""科技产业链点 TOP-N 事件关系业务（九大业务之一）HTTP 端点。

对齐前端 service-modules.ts 的 industry-chain-event 契约：
POST /api/v1/kg-service/industry-node-top-events，请求 {chain_node_id, top_n, event_type,
time_range}。围绕产业链节点，收集关联企业的事件，按影响力排序取 TOP-N，构建事件↔专家关联，
给出风险等级与影响分析。全部数据经 graph-search 查图 API 获取，不直连图、不直连 MySQL。
"""

from __future__ import annotations

from fastapi import APIRouter

from biz.schemas.common import ApiResponse
from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest
from service.industry_node_top_events_business import IndustryNodeTopEventsService

router = APIRouter(prefix="/kg-service", tags=["kg-service"])
service = IndustryNodeTopEventsService()


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


@router.post("/industry-node-top-events", response_model=ApiResponse)
async def run_industry_node_top_events(req: IndustryNodeTopEventsRequest) -> ApiResponse:
    try:
        data = await service.run(req)
        return ApiResponse(data=data.model_dump())
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(code=500, success=False, msg=f"产业链点TOP-N事件业务执行失败: {exc}")
