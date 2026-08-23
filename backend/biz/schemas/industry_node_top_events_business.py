"""科技产业链点 TOP-N 事件关系业务（九大业务之一）请求/响应模型。

对齐前端 service-modules.ts 的 industry-chain-event 契约：
端点 POST /api/v1/kg-service/industry-node-top-events，请求 {chain_node_id, top_n, event_type,
time_range}，响应 data={events, experts, enterprises, risk_level, top_events, relations}。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IndustryNodeTopEventsRequest(BaseModel):
    chain_node_id: str = Field(..., description="产业链节点标识，如 IC0007007（集成电路设计）")
    top_n: int = Field(10, ge=1, le=50, description="返回事件数量")
    event_type: str = Field("", description="事件类型筛选（financing/bankruptcy/bid/...）")
    time_range: str = Field("", description="事件时间范围筛选，如 2025-2026")
    max_orgs: int = Field(
        20, ge=1, le=50, description="链节点下最多扫描企业数（按 chain_score 排序）"
    )


class TopEventItem(BaseModel):
    event_id: str
    event_type: str | None = None
    occur_date: str | None = None
    amount: str | None = None
    title: str | None = None
    impact_score: float = 0.0
    rank: int = 0
    org_id: str | None = None
    org_name: str | None = None
    confidence: float = 0.0  # 事件置信度（按事件类型规则赋值）


class EventExpertRelation(BaseModel):
    event_id: str
    event_title: str | None = None
    expert_id: str
    expert_name: str | None = None
    role: str | None = None
    org_id: str
    org_name: str | None = None


class IndustryNodeTopEventsResponse(BaseModel):
    chain_node_id: str
    chain_node_name: str | None = None
    chain_name: str | None = None
    node_imp_level: str | None = None
    events: int = 0  # TOP-N 事件数
    experts: int = 0  # 关联专家数
    enterprises: int = 0  # 关联企业数
    risk_level: str = ""  # 高/中/低
    top_events: list[TopEventItem] = Field(default_factory=list)
    relations: list[EventExpertRelation] = Field(default_factory=list)
    # 标书分析维度：节点影响 / 发展趋势 / 机遇挖掘（从 TOP 事件池规则派生）
    node_impact: str = ""
    trend: str = ""
    opportunity: str = ""
    confidence: float = 0.0  # 综合置信度（按风险等级赋值）
    evidence: list[str] = Field(default_factory=list)
