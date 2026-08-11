"""科技产业链点 TOP-N 事件关系业务编排服务的单元测试。

mock graph-search API（不碰 MySQL/图），验证链节点查询 → 企业关联 → 事件影响力排序 →
风险等级 → 事件↔专家关联。
"""

from __future__ import annotations

import pytest

from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest
from service.industry_node_top_events_business import IndustryNodeTopEventsService

NODE_VID = "node_IC_test"
ORG_A = "org_aaa"
ORG_B = "org_bbb"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """按 url 子串路由到预设响应。"""

    def __init__(self, routes: list[tuple[str, dict]]) -> None:
        self._routes = routes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get(self, url: str, params: dict | None = None, timeout: float = 0) -> _FakeResponse:
        for key, payload in self._routes:
            if key in url:
                return _FakeResponse(payload)
        return _FakeResponse({"data": {"nodes": [], "edges": []}})


def _httpx():
    import service.industry_node_top_events_business as mod

    return mod.httpx


def _routes() -> list[tuple[str, dict]]:
    # 1) 链节点子图：IndustryNode + IndustryChain + 2 个 org(BELONGS_TO_NODE)
    node_subgraph = {
        "data": {
            "nodes": [
                {
                    "id": NODE_VID,
                    "labels": ["IndustryNode"],
                    "properties": {"node_name": "测试节点", "node_imp_level": "1"},
                },
                {
                    "id": "chain_IC",
                    "labels": ["IndustryChain"],
                    "properties": {"chain_name": "测试产业链"},
                },
                {"id": ORG_A, "labels": ["Organization"], "properties": {"name_cn": "甲公司"}},
                {"id": ORG_B, "labels": ["Organization"], "properties": {"name_cn": "乙公司"}},
            ],
            "edges": [
                {"type": "HAS_NODE", "source": "chain_IC", "target": NODE_VID, "properties": {}},
                {
                    "type": "BELONGS_TO_NODE",
                    "source": ORG_A,
                    "target": NODE_VID,
                    "properties": {"chain_score": 90},
                },
                {
                    "type": "BELONGS_TO_NODE",
                    "source": ORG_B,
                    "target": NODE_VID,
                    "properties": {"chain_score": 60},
                },
            ],
        }
    }
    # 2) orgA 子图：1 破产事件(高风险) + 1 财务事件
    org_a_sub = {
        "data": {
            "nodes": [
                {"id": ORG_A, "labels": ["Organization"], "properties": {"name_cn": "甲公司"}},
                {
                    "id": "ev_bk",
                    "labels": ["Event"],
                    "properties": {
                        "event_type": "bankruptcy",
                        "occur_date": "2025-03-01",
                        "amount": "50000000",
                        "title": "破产清算",
                    },
                },
            ],
            "edges": [
                {"type": "INVOLVED_IN", "source": ORG_A, "target": "ev_bk", "properties": {}}
            ],
        }
    }
    # 3) orgB 子图：1 招聘事件(低风险)
    org_b_sub = {
        "data": {
            "nodes": [
                {"id": ORG_B, "labels": ["Organization"], "properties": {"name_cn": "乙公司"}},
                {
                    "id": "ev_rc",
                    "labels": ["Event"],
                    "properties": {
                        "event_type": "recruit",
                        "occur_date": "2024-01-01",
                        "amount": "0",
                        "title": "招聘",
                    },
                },
            ],
            "edges": [
                {"type": "INVOLVED_IN", "source": ORG_B, "target": "ev_rc", "properties": {}}
            ],
        }
    }
    # 4) orgA 专家边
    org_a_edges = {
        "data": {
            "edges": [{"source": "person_x", "target": ORG_A, "properties": {"position": "董事长"}}]
        }
    }
    return [
        (f"/graph-search/filtered-subgraph/{NODE_VID}", node_subgraph),
        (f"/graph-search/filtered-subgraph/{ORG_A}", org_a_sub),
        (f"/graph-search/filtered-subgraph/{ORG_B}", org_b_sub),
        (f"/graph-search/node/{ORG_A}", org_a_edges),
    ]


@pytest.mark.asyncio
async def test_topn_via_graph_search_only(monkeypatch):
    """纯 graph-search API（不碰 MySQL），验证 TOP-N 排序 + 风险 + 专家关联。"""
    svc = IndustryNodeTopEventsService(base_url="http://x")
    monkeypatch.setattr(_httpx(), "AsyncClient", lambda: _FakeAsyncClient(_routes()))

    resp = await svc.run(
        IndustryNodeTopEventsRequest(chain_node_id="IC_test", top_n=3, max_orgs=10)
    )

    assert resp.chain_node_name == "测试节点"
    assert resp.chain_name == "测试产业链"
    assert resp.node_imp_level == "1"
    assert resp.enterprises == 2  # 2 个 org
    assert resp.events == 2  # 2 个事件（破产 + 招聘）
    # bankruptcy 权重高，排在 recruit 前
    types = [e.event_type for e in resp.top_events]
    assert types.index("bankruptcy") < types.index("recruit")
    assert resp.risk_level == "高"  # 含破产 → 高
    # orgA 有专家
    assert resp.experts == 1
    assert resp.relations[0].expert_id == "person_x"
    # 标书分析维度：后端真实派生（非空）
    assert resp.node_impact and "bankruptcy" in resp.node_impact
    assert resp.trend and "分布平稳" in resp.trend
    assert resp.opportunity  # 非空（即便 0 条也有兜底文案）


def test_derive_analysis_dimensions():
    """_derive_analysis 从混合事件池派生 节点影响/发展趋势/机遇挖掘 文案。"""
    top = [
        {
            "event_type": "bankruptcy",
            "occur_date": "2025-05-01",
            "org_id": "org_a",
        },
        {
            "event_type": "financing",
            "occur_date": "2026-01-10",
            "org_id": "org_a",
        },
        {
            "event_type": "news",
            "occur_date": "2026-03-02",
            "org_id": "org_b",
        },
    ]
    top_org_ids = {"org_a", "org_b"}
    node_impact, trend, opportunity = IndustryNodeTopEventsService._derive_analysis(
        top, top_org_ids, "高"
    )
    # 节点影响：含风险/财务/资讯计数
    assert "1 条风险事件" in node_impact
    assert "1 条财务事件" in node_impact
    assert "1 条资讯" in node_impact
    assert "波及 2 家链上企业" in node_impact
    # 发展趋势：2025+2026 占 2/3 > 50% → 短期热度上升
    assert "短期热度上升" in trend
    assert "2025" in trend and "2026" in trend
    # 机遇挖掘：financing + news 命中机遇类
    assert "2 条" in opportunity
    assert "financing" in opportunity
    assert "涉及 2 家企业" in opportunity


def test_derive_analysis_empty():
    assert IndustryNodeTopEventsService._derive_analysis([], set(), "低") == ("", "", "")
