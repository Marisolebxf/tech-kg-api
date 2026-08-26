"""科技产业链点 TOP-N 事件关系业务编排服务的单元测试。

mock graph 查询 helper（_subgraph_sync / _fetch_org_governance_sync），不碰 MySQL/图/HTTP，
验证链节点查询 → 企业关联 → 事件影响力排序 → 风险等级 → 事件↔专家关联。
"""

from __future__ import annotations

import pytest

import service.industry_node_top_events_business as mod
from biz.schemas.industry_node_top_events_business import IndustryNodeTopEventsRequest
from service.industry_node_top_events_business import IndustryNodeTopEventsService

NODE_VID = "node_IC_test"
ORG_A = "org_aaa"
ORG_B = "org_bbb"


def _subgraphs() -> dict[str, dict]:
    """vid -> 子图（与 graph-search /filtered-subgraph 的 data 结构一致）。"""
    # 1) 链节点子图：IndustryNode + IndustryChain + 2 个 org(BELONGS_TO_NODE)
    node_subgraph = {
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
    # 2) orgA 子图：1 破产事件(高风险) + 1 财务事件
    org_a_sub = {
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
        "edges": [{"type": "INVOLVED_IN", "source": ORG_A, "target": "ev_bk", "properties": {}}],
    }
    # 3) orgB 子图：1 招聘事件(低风险)
    org_b_sub = {
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
        "edges": [{"type": "INVOLVED_IN", "source": ORG_B, "target": "ev_rc", "properties": {}}],
    }
    return {NODE_VID: node_subgraph, ORG_A: org_a_sub, ORG_B: org_b_sub}


def _governance() -> dict[str, list]:
    """org_id -> [(expert_id, position), ...]。"""
    return {ORG_A: [("person_x", "董事长")], ORG_B: []}


@pytest.mark.asyncio
async def test_topn_via_graph_helpers(monkeypatch):
    """直调 infra graph client 的 helper 已 mock，验证 TOP-N 排序 + 风险 + 专家关联。"""
    subs = _subgraphs()
    govs = _governance()
    monkeypatch.setattr(
        mod,
        "_subgraph_sync",
        lambda client, vid, edge_types, limit: subs.get(vid, {"nodes": [], "edges": []}),
    )
    monkeypatch.setattr(
        mod,
        "_fetch_org_governance_sync",
        lambda client, org_id: govs.get(org_id, []),
    )
    monkeypatch.setattr(mod, "_get_dev_client", lambda: None)  # 不连真实图
    monkeypatch.setattr(mod, "_result_cache", {})  # 清缓存，避免用例间串

    svc = IndustryNodeTopEventsService(base_url="http://x")
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
    # 置信度：风险等级 高 → 0.9；bankruptcy 事件 → 0.9
    assert resp.confidence == 0.9
    assert resp.top_events[0].confidence == 0.9


@pytest.mark.asyncio
async def test_enterprises_and_provenance_only_cover_topn_result(monkeypatch):
    subs = _subgraphs()
    monkeypatch.setattr(
        mod,
        "_subgraph_sync",
        lambda client, vid, edge_types, limit: subs.get(vid, {"nodes": [], "edges": []}),
    )
    monkeypatch.setattr(mod, "_fetch_org_governance_sync", lambda client, org_id: [])
    monkeypatch.setattr(mod, "_get_dev_client", lambda: None)
    monkeypatch.setattr(mod, "_result_cache", {})

    resp = await IndustryNodeTopEventsService().run(
        IndustryNodeTopEventsRequest(chain_node_id="IC_test", top_n=1, max_orgs=10)
    )

    assert resp.events == 1
    assert resp.enterprises == 1
    assert {item.org_id for item in resp.top_events} == {ORG_A}
    assert ORG_A in resp.entity_provenance
    assert ORG_B not in resp.entity_provenance


@pytest.mark.asyncio
async def test_topn_result_cache_hit(monkeypatch):
    """同参数二次请求命中 60s 缓存，_subgraph_sync 只被调用一次。"""
    subs = _subgraphs()
    govs = _governance()
    call_count = {"n": 0}

    def _counted_subgraph(client, vid, edge_types, limit):
        call_count["n"] += 1
        return subs.get(vid, {"nodes": [], "edges": []})

    monkeypatch.setattr(mod, "_subgraph_sync", _counted_subgraph)
    monkeypatch.setattr(
        mod, "_fetch_org_governance_sync", lambda client, org_id: govs.get(org_id, [])
    )
    monkeypatch.setattr(mod, "_get_dev_client", lambda: None)
    monkeypatch.setattr(mod, "_result_cache", {})

    svc = IndustryNodeTopEventsService()
    req = IndustryNodeTopEventsRequest(chain_node_id="IC_test", top_n=3, max_orgs=10)
    r1 = await svc.run(req)
    r2 = await svc.run(req)
    assert r1.chain_node_name == r2.chain_node_name == "测试节点"
    # 第二次命中缓存，_subgraph_sync 不再被调用（第一次会调 1 次链节点 + 2 次企业 = 3 次）
    assert call_count["n"] == 3


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
