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
                "properties": {
                    "node_name": "测试节点",
                    "node_imp_level": "1",
                    "confidence": 0.88,
                },
            },
            {
                "id": "chain_IC",
                "labels": ["IndustryChain"],
                "properties": {"chain_name": "测试产业链"},
            },
            {
                "id": ORG_A,
                "labels": ["Organization"],
                "properties": {"name_cn": "甲公司", "confidence": 0.81},
            },
            {
                "id": ORG_B,
                "labels": ["Organization"],
                "properties": {"name_cn": "乙公司", "confidence": 0.76},
            },
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
    """org_id -> [(expert_id, position, expert_props), ...]。"""
    return {
        ORG_A: [
            (
                "person_x",
                "董事长",
                {"name_cn": "张三", "source_record_id": "sch-001", "source_table": "dwd_scholar"},
            )
        ],
        ORG_B: [],
    }


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
    # 专家姓名来自 Person 节点属性；溯源为真实字段（不再缺省让前端回退静态映射）
    assert resp.relations[0].expert_name == "张三"
    assert resp.entity_provenance["person_x"].sourceField == "scholar_id"
    assert resp.entity_provenance["person_x"].sourceValue == "sch-001"
    assert resp.entity_provenance["IC_test"].confidence == 0.88
    assert resp.entity_provenance[ORG_A].confidence == 0.81
    # 专家节点 mock 未带 confidence：dwd_scholar + 稳定 ID + 姓名 → 0.80
    assert resp.entity_provenance["person_x"].confidence == 0.8
    # 标书分析维度：后端真实派生（非空）
    assert resp.node_impact
    # 分析文案使用中文事件类型（EVENT_TYPE_LABEL）
    assert "破产" in resp.node_impact
    assert resp.trend
    assert "分布平稳" in resp.trend
    assert resp.opportunity  # 非空（即便 0 条也有兜底文案）
    # 置信度：风险等级 高 → 0.9；bankruptcy 事件 → 0.9
    assert resp.confidence == 0.9
    assert resp.top_events[0].confidence == 0.9


def test_industry_node_confidence_falls_back_to_entity_completeness():
    """图节点未携带 confidence 时，按 DWD 来源和核心字段完整度回退。"""
    provenance = mod._entity_provenance(
        {
            "node_id": "IC0007007",
            "node_name": "集成电路设计",
            "node_type": "2",
            "level": "3",
            "node_imp_level": "1",
            "node_stage": "2",
            "node_path": "设计、制造、封测>IC设计>集成电路设计",
            "source_table": "dwd_industry_chain_info",
        },
        {"IndustryNode"},
    )

    assert provenance.confidence == 0.9


def test_industry_node_confidence_prefers_graph_value():
    """图中已有置信度时保留原值，不被完整度回退覆盖。"""
    provenance = mod._entity_provenance(
        {
            "node_id": "IC0007007",
            "node_name": "集成电路设计",
            "source_table": "dwd_industry_chain_info",
            "confidence": 0.88,
        },
        {"IndustryNode"},
    )

    assert provenance.confidence == 0.88


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
async def test_topn_fills_missing_entity_confidence(monkeypatch):
    """链节点/企业/事件缺图上 confidence 时按规则计算，实体 tab 仍拿到数字。"""
    subs = _subgraphs()
    for node in subs[NODE_VID]["nodes"]:
        props = node.get("properties") or {}
        props.pop("confidence", None)
        if node.get("id") == NODE_VID:
            props["source_record_id"] = "IC_test"
            node["properties"] = props
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
    monkeypatch.setattr(mod, "_get_dev_client", lambda: None)
    monkeypatch.setattr(mod, "_result_cache", {})

    resp = await IndustryNodeTopEventsService().run(
        IndustryNodeTopEventsRequest(chain_node_id="IC_test", top_n=3, max_orgs=10)
    )

    # IndustryNode: 非 DWD + 稳定 ID + 名称 + node_imp_level → 0.80（规则分，不是空属性兜底）
    assert resp.entity_provenance["IC_test"].confidence == 0.8
    # Organization: 仅 name_cn → 0.30 + 0.20
    assert resp.entity_provenance[ORG_A].confidence == 0.5
    assert resp.entity_provenance["person_x"].confidence == 0.8
    # Event: 有 title → 0.30 + 0.20，不再是 None/暂无
    assert resp.entity_provenance["ev_bk"].confidence == 0.5


@pytest.mark.asyncio
async def test_event_type_expands_scan_beyond_max_orgs(monkeypatch):
    """指定 event_type 时扫描全链企业：目标事件在 chain_score 靠后企业也不被 max_orgs 截成空。

    orgA(score=90) 只有 bankruptcy；orgB(score=60) 有 recruit。
    max_orgs=1 时未过滤只会扫 orgA → 空；event_type=recruit 应扩窗扫到 orgB 命中。
    """
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
        IndustryNodeTopEventsRequest(
            chain_node_id="IC_test", top_n=10, max_orgs=1, event_type="recruit"
        )
    )

    assert resp.events == 1
    assert resp.top_events[0].event_type == "recruit"
    assert resp.top_events[0].org_id == ORG_B


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
    assert "2025" in trend
    assert "2026" in trend
    # 机遇挖掘：financing + news 命中机遇类
    assert "2 条" in opportunity
    # 机遇挖掘文案的事件类型为中文（EVENT_TYPE_LABEL）
    assert "融资" in opportunity
    assert "涉及 2 家企业" in opportunity


def test_derive_analysis_empty():
    assert IndustryNodeTopEventsService._derive_analysis([], set(), "低") == ("", "", "")


class _FakeEdge:
    def __init__(self, source_id, target_id, edge_type, properties=None):
        self.source_id = source_id
        self.target_id = target_id
        self.type = edge_type
        self.properties = properties or {}


class _FakeNode:
    def __init__(self, node_id, labels, properties=None):
        self.id = node_id
        self.labels = labels
        self.properties = properties or {}


class _FakeClient:
    def __init__(self, edges_by_type, nodes):
        self.edges_by_type = edges_by_type
        self.nodes = nodes

    def get_node_edges(self, org_id, direction="in", edge_type=None, limit=20):
        return list(self.edges_by_type.get(edge_type, []))[:limit]

    def get_node(self, vid):
        return self.nodes.get(vid)


def test_fetch_org_governance_keeps_person_affiliation_drops_org_shareholder():
    """任职学者要进关联专家；股东边对端若是机构则丢弃。"""
    client = _FakeClient(
        {
            "AFFILIATED_WITH": [
                _FakeEdge(
                    "person_s1",
                    ORG_A,
                    "AFFILIATED_WITH",
                    {"work_experience_position_zh": "研究员"},
                )
            ],
            "SHAREHOLDER_OF": [_FakeEdge("org_hold", ORG_A, "SHAREHOLDER_OF")],
            "EXECUTIVE_OF": [],
        },
        {
            "person_s1": _FakeNode(
                "person_s1",
                ["Person"],
                {"name_zh": "李四", "source_record_id": "s1", "source_table": "dwd_scholar"},
            ),
            "org_hold": _FakeNode("org_hold", ["Organization"], {"name_cn": "控股公司"}),
        },
    )
    experts = mod._fetch_org_governance_sync(client, ORG_A)
    assert len(experts) == 1
    pid, role, props = experts[0]
    assert pid == "person_s1"
    assert role == "研究员"
    assert props["name_zh"] == "李四"


def test_select_top_covering_experts_replaces_last_when_window_has_none():
    ranked = [
        {"event_id": "e1", "org_id": ORG_A, "_score": 9},
        {"event_id": "e2", "org_id": ORG_B, "_score": 3},
        {"event_id": "e3", "org_id": "org_ccc", "_score": 2},
    ]
    picked = mod._select_top_covering_experts(
        ranked, 2, {ORG_A: [], ORG_B: [], "org_ccc": [("person_x", "董事", {})]}
    )
    assert [ev["event_id"] for ev in picked] == ["e1", "e3"]


@pytest.mark.asyncio
async def test_topn_backfills_expert_org_outside_max_orgs(monkeypatch):
    """max_orgs 截断窗外的有高管企业，首轮无专家时应补扫并写入 relations。"""
    org_c = "org_ccc"
    subs = _subgraphs()
    subs[NODE_VID]["nodes"].append(
        {"id": org_c, "labels": ["Organization"], "properties": {"name_cn": "丙公司"}}
    )
    subs[NODE_VID]["edges"].append(
        {
            "type": "BELONGS_TO_NODE",
            "source": org_c,
            "target": NODE_VID,
            "properties": {"chain_score": 50},
        }
    )
    subs[org_c] = {
        "nodes": [
            {"id": org_c, "labels": ["Organization"], "properties": {"name_cn": "丙公司"}},
            {
                "id": "ev_sf",
                "labels": ["Event"],
                "properties": {
                    "event_type": "stock_finance",
                    "occur_date": "2025-06-01",
                    "amount": "1000",
                    "title": "年报",
                },
            },
        ],
        "edges": [{"type": "INVOLVED_IN", "source": org_c, "target": "ev_sf", "properties": {}}],
    }
    govs = {
        ORG_A: [],
        ORG_B: [],
        org_c: [("person_y", "董事长", {"name_cn": "王五", "source_record_id": "sch-y"})],
    }
    monkeypatch.setattr(
        mod,
        "_subgraph_sync",
        lambda client, vid, edge_types, limit: subs.get(vid, {"nodes": [], "edges": []}),
    )
    monkeypatch.setattr(
        mod, "_fetch_org_governance_sync", lambda client, org_id: govs.get(org_id, [])
    )
    monkeypatch.setattr(mod, "_get_dev_client", lambda: None)
    monkeypatch.setattr(mod, "_result_cache", {})
    monkeypatch.setattr(mod, "EXPERT_SCAN_EXTRA_ORGS", 30)
    monkeypatch.setattr(mod, "EXPERT_PROBE_LIMIT", 10)

    resp = await IndustryNodeTopEventsService().run(
        IndustryNodeTopEventsRequest(chain_node_id="IC_test", top_n=1, max_orgs=1)
    )

    assert resp.experts == 1
    assert resp.relations[0].expert_id == "person_y"
    assert resp.relations[0].expert_name == "王五"
    assert resp.top_events[0].org_id == org_c


@pytest.mark.asyncio
async def test_topn_covers_expert_org_inside_max_orgs_but_not_in_impact_top(monkeypatch):
    """有高管企业已在 max_orgs 窗内、但 impact 排不进 TOP 时，仍应替换末位展示专家。"""
    org_c = "org_ccc"
    subs = _subgraphs()
    subs[NODE_VID]["nodes"].append(
        {"id": org_c, "labels": ["Organization"], "properties": {"name_cn": "丙公司"}}
    )
    subs[NODE_VID]["edges"].append(
        {
            "type": "BELONGS_TO_NODE",
            "source": org_c,
            "target": NODE_VID,
            "properties": {"chain_score": 50},
        }
    )
    subs[org_c] = {
        "nodes": [
            {"id": org_c, "labels": ["Organization"], "properties": {"name_cn": "丙公司"}},
            {
                "id": "ev_sf",
                "labels": ["Event"],
                "properties": {
                    "event_type": "stock_finance",
                    "occur_date": "2025-06-01",
                    "amount": "1000",
                    "title": "年报",
                },
            },
        ],
        "edges": [{"type": "INVOLVED_IN", "source": org_c, "target": "ev_sf", "properties": {}}],
    }
    govs = {
        ORG_A: [],
        ORG_B: [],
        org_c: [("person_y", "董事长", {"name_cn": "王五", "source_record_id": "sch-y"})],
    }
    monkeypatch.setattr(
        mod,
        "_subgraph_sync",
        lambda client, vid, edge_types, limit: subs.get(vid, {"nodes": [], "edges": []}),
    )
    monkeypatch.setattr(
        mod, "_fetch_org_governance_sync", lambda client, org_id: govs.get(org_id, [])
    )
    monkeypatch.setattr(mod, "_get_dev_client", lambda: None)
    monkeypatch.setattr(mod, "_result_cache", {})

    resp = await IndustryNodeTopEventsService().run(
        IndustryNodeTopEventsRequest(chain_node_id="IC_test", top_n=1, max_orgs=10)
    )

    assert resp.experts == 1
    assert resp.relations[0].expert_id == "person_y"
    assert resp.top_events[0].org_id == org_c
