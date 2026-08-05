"""科技产业链点 TOP-N 事件关系业务的单元测试。

mock MySQL（_load_chain_node）+ httpx（subgraph + node edges），验证事件影响力排序、
风险等级、事件↔专家关联。
"""

from __future__ import annotations

import pytest

from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest
from service.industry_node_top_events_business import IndustryNodeTopEventsService

ORG_A = "org_aaa"
ORG_B = "org_bbb"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, routes: list[tuple[str, dict]]) -> None:
        self._routes = routes

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc) -> None:
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
    # orgA: 1 个高风险事件(bankruptcy) + 1 个财务事件(stock_finance 高金额)
    sub_a = {
        "data": {
            "nodes": [
                {
                    "id": ORG_A,
                    "labels": ["Organization"],
                    "properties": {"name_cn": "甲公司", "listing_status": "已上市"},
                },
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
                {
                    "id": "ev_fin",
                    "labels": ["Event"],
                    "properties": {
                        "event_type": "stock_finance",
                        "occur_date": "202512",
                        "amount": "1000000000",
                        "title": "上市企业财务信息",
                    },
                },
            ],
            "edges": [
                {"type": "INVOLVED_IN", "source": ORG_A, "target": "ev_bk", "properties": {}},
                {"type": "INVOLVED_IN", "source": ORG_A, "target": "ev_fin", "properties": {}},
            ],
        }
    }
    sub_b = {
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
    # 专家边（orgA 有一个高管）
    edges_a = {
        "data": {
            "edges": [{"source": "person_x", "target": ORG_A, "properties": {"position": "董事长"}}]
        }
    }
    return [
        (f"/graph-search/subgraph/{ORG_A}", sub_a),
        (f"/graph-search/subgraph/{ORG_B}", sub_b),
        (f"/graph-search/node/{ORG_A}", edges_a),
    ]


@pytest.mark.asyncio
async def test_topn_ranks_by_impact_and_links_experts(monkeypatch):
    svc = IndustryNodeTopEventsService(base_url="http://x")
    # mock MySQL：链节点信息 + 2 个企业
    svc._load_chain_node = lambda chain_node_id, max_orgs: (
        {"node_name": "集成电路设计", "chain_name": "集成电路", "node_imp_level": "1"},
        [("aaa", 80.0), ("bbb", 60.0)],
    )
    monkeypatch.setattr(_httpx(), "AsyncClient", lambda: _FakeAsyncClient(_routes()))

    resp = await svc.run(
        IndustryNodeTopEventsRequest(chain_node_id="IC0007007", top_n=3, max_orgs=10)
    )

    assert resp.chain_node_name == "集成电路设计"
    assert resp.chain_name == "集成电路"
    assert resp.enterprises == 2
    assert resp.events == 3  # 3 个事件全进 TOP-3
    # bankruptcy(stock_finance) 排在 recruit 前（风险权重高）
    types = [e.event_type for e in resp.top_events]
    assert types.index("bankruptcy") < types.index("recruit")
    # 含风险事件 → 风险等级高
    assert resp.risk_level == "高"
    # orgA 有专家 → relations 非空
    assert resp.experts == 1
    assert len(resp.relations) == 2  # orgA 的 2 个 TOP 事件都关联到该专家
    assert resp.relations[0].expert_id == "person_x"
