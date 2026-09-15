from __future__ import annotations

import pytest

from service import industry_chain_panorama as panorama_module
from service.industry_chain_panorama import IndustryChainPanoramaService


class _FakeGraphClient:
    def __init__(self) -> None:
        self.resolve_calls: list[str] = []
        self.search_calls: list[tuple[str, str, str, int]] = []
        self.search_payloads: dict[tuple[str, str, str], dict[str, object]] = {}

    async def search_nodes(self, *, label, properties=None, limit=20, space=None):
        [(prop, value)] = list((properties or {}).items())
        self.search_calls.append((str(label), str(prop), str(value), int(limit)))
        return self.search_payloads.get((str(label), str(prop), str(value)), {"items": []})

    async def list_nodes(self, *, label, limit=20, offset=0, space=None):
        return {"items": [], "total": 0}

    async def resolve_addressable_node(self, node, *, vid_candidates=(), space=None):
        self.resolve_calls.append(str(node.get("id") or ""))
        return {"id": str(node.get("id") or "")}


@pytest.mark.asyncio
async def test_resolve_seed_vids_stops_after_enough_resolved_ids() -> None:
    service = IndustryChainPanoramaService()
    client = _FakeGraphClient()
    candidates = {
        "leading_expert": [{"id": f"person_{i}", "properties": {}} for i in range(4)],
        "leading_enterprise": [{"id": f"org_{i}", "properties": {}} for i in range(4)],
        "core_technology": [{"id": f"kw_{i}", "properties": {}} for i in range(2)],
        "flagship_achievement": [{"id": "paper_1", "properties": {}}],
    }

    resolved = await service._resolve_seed_vids(client, candidates)

    assert resolved == [
        "person_0",
        "person_1",
        "person_2",
        "person_3",
        "org_0",
        "org_1",
    ]
    assert client.resolve_calls == resolved


@pytest.mark.asyncio
async def test_search_by_keyword_falls_back_to_small_scan(monkeypatch) -> None:
    service = IndustryChainPanoramaService()

    async def _fake_list_by_label_throttled(client, label, limit, offset):
        assert label == "Keyword"
        assert limit == 50
        assert offset == 0
        return [
            {"id": "kw_1", "properties": {"keyword": "人工智能芯片"}},
            {"id": "kw_2", "properties": {"keyword": "量子计算"}},
        ]

    monkeypatch.setattr(service, "_list_by_label_throttled", _fake_list_by_label_throttled)

    result = await service._search_by_keyword(
        client=_FakeGraphClient(),
        label="Keyword",
        definition={"keyword_props": ("keyword",)},
        industry="人工智能",
        top_k=2,
    )

    assert [node["id"] for node in result] == ["kw_1"]


def test_build_summary_counts_only_returned_layer_items_and_graph_edges() -> None:
    service = IndustryChainPanoramaService()

    summary = service._build_summary(
        "人工智能",
        [
            {
                "key": "core_technology",
                "title": "核心技术",
                "items": [{"id": "kw_1"}, {"id": "kw_2"}],
            },
            {"key": "leading_enterprise", "title": "领军企业", "items": [{"id": "org_1"}]},
            {"key": "leading_expert", "title": "领军专家", "items": []},
        ],
        {
            "nodes": [{"id": "kw_1"}, {"id": "org_1"}],
            "edges": [
                {"label": "HAS_KEYWORD"},
                {"label": "HAS_KEYWORD"},
                {"label": "RELATED_TO"},
            ],
        },
        ["集成电路", "低空经济"],
    )

    assert summary == {
        "industry": "人工智能",
        "industryChains": ["集成电路", "低空经济"],
        "totalNodes": 3,
        "totalEdges": 3,
        "nodesByLabel": {"核心技术": 2, "领军企业": 1, "领军专家": 0},
        "edgesByType": {"HAS_KEYWORD": 2, "RELATED_TO": 1},
    }


@pytest.mark.asyncio
async def test_fetch_industry_chain_labels_lists_and_dedupes_chain_names() -> None:
    service = IndustryChainPanoramaService()

    class _ChainClient:
        async def list_nodes(self, *, label, limit=20, offset=0, space=None):
            assert label == "IndustryChain"
            return {
                "items": [
                    {"id": "chain_1", "properties": {"name": "集成电路"}},
                    {"id": "chain_2", "properties": {"chain_name": "低空经济"}},
                    {"id": "chain_3", "properties": {"name": "集成电路"}},
                    {"id": "chain_4", "properties": {}},
                ],
                "total": 4,
            }

    labels = await service._fetch_industry_chain_labels(_ChainClient())

    assert labels == ["集成电路", "低空经济"]


def test_normalize_industry_keyword_uses_presets() -> None:
    assert IndustryChainPanoramaService._normalize_industry_keyword("人工智能产业链") == "人工智能"
    assert IndustryChainPanoramaService._normalize_industry_keyword("芯片") == "集成电路"
    assert IndustryChainPanoramaService._normalize_industry_keyword("产业全景") is None


@pytest.mark.asyncio
async def test_resolve_anchor_from_keyword_prefers_preset_search_plan() -> None:
    service = IndustryChainPanoramaService()
    client = _FakeGraphClient()
    client.search_payloads[("IndustryNode", "node_name", "集成电路")] = {
        "items": [{"id": "node_ic_1", "properties": {"node_name": "集成电路"}}]
    }

    resolved = await service._resolve_anchor_from_keyword(client, "集成电路", None)

    assert resolved == "node_ic_1"
    assert client.resolve_calls == ["node_ic_1"]
    assert client.search_calls == [
        ("IndustryNode", "node_name", "集成电路", 2),
        ("IndustryNode", "name", "集成电路", 2),
    ]


@pytest.mark.asyncio
async def test_resolve_anchor_from_keyword_uses_unique_search_hit() -> None:
    service = IndustryChainPanoramaService()
    client = _FakeGraphClient()
    client.search_payloads[("IndustryNode", "node_name", "人工智能")] = {
        "items": [{"id": "node_ai_1", "properties": {"node_name": "人工智能"}}]
    }

    resolved = await service._resolve_anchor_from_keyword(client, "人工智能", None)

    assert resolved == "node_ai_1"
    assert client.resolve_calls == ["node_ai_1"]


@pytest.mark.asyncio
async def test_resolve_unique_anchor_candidate_rejects_ambiguous_hits() -> None:
    service = IndustryChainPanoramaService()
    client = _FakeGraphClient()
    client.search_payloads[("IndustryNode", "node_name", "人工智能")] = {
        "items": [
            {"id": "node_ai_1", "properties": {"node_name": "人工智能"}},
            {"id": "node_ai_2", "properties": {"node_name": "人工智能"}},
        ]
    }

    resolved = await service._resolve_unique_anchor_candidate(
        client,
        "IndustryNode",
        ("node_name",),
        "人工智能",
    )

    assert resolved is None
    assert client.resolve_calls == []


@pytest.mark.asyncio
async def test_fetch_layers_collects_all_four_layers_without_keyword() -> None:
    """重置参数后执行（无关键词、无锚点）时四层都要返回，核心专家/产业动态事件不能缺层。"""
    service = IndustryChainPanoramaService()

    layers, seed_vids = await service._fetch_layers(_FakeGraphClient(), None, 5)

    assert [layer["key"] for layer in layers] == [
        "core_technology",
        "leading_enterprise",
        "leading_expert",
        "flagship_achievement",
    ]
    assert seed_vids == []


@pytest.mark.asyncio
async def test_query_returns_keyword_no_match_when_keyword_misses(monkeypatch) -> None:
    """关键词未命中不再回退全库紧凑全景：结果保持空并标记 keyword_no_match。"""

    service = IndustryChainPanoramaService()

    async def _fake_fetch_layers(client, industry, top_k):
        assert industry == "人工智能"
        return (
            [
                {"key": "core_technology", "title": "核心技术", "total": 0, "items": []},
                {"key": "leading_enterprise", "title": "领军企业", "total": 0, "items": []},
            ],
            [],
        )

    async def _fake_fetch_graph(client, seed_vids, anchor_id, depth):
        return {"nodes": [], "edges": []}

    class _GraphCtx:
        async def __aenter__(self):
            return _FakeGraphClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service, "_fetch_layers", _fake_fetch_layers)
    monkeypatch.setattr(service, "_fetch_graph", _fake_fetch_graph)
    monkeypatch.setattr(
        service,
        "_resolve_anchor_from_keyword",
        lambda *args, **kwargs: __import__("asyncio").sleep(0, result=None),
    )
    monkeypatch.setattr("service.industry_chain_panorama.graph_api", lambda **kwargs: _GraphCtx())

    result = await service.query(industry="人工智能", depth=1, top_k=3)

    assert result["source"]["reason"] == "keyword_no_match"
    assert [not layer["items"] for layer in result["layers"]]
    assert result["graph"]["nodes"] == []
    assert result["summary"]["totalNodes"] == 0


@pytest.mark.asyncio
async def test_resolve_anchor_scans_exact_value_when_property_index_is_missing(monkeypatch) -> None:
    service = IndustryChainPanoramaService()

    async def _fake_list(client, label, limit, offset):
        assert label == "IndustryChain"
        assert limit == 50
        assert offset == 0
        return [
            {
                "id": "chain_IC0007",
                "labels": ["IndustryChain"],
                "properties": {"chain_name": "集成电路"},
            },
            {
                "id": "chain_OTHER",
                "labels": ["IndustryChain"],
                "properties": {"chain_name": "其他产业"},
            },
        ]

    monkeypatch.setattr(service, "_list_by_label_throttled", _fake_list)

    resolved = await service._resolve_unique_anchor_candidate(
        _FakeGraphClient(),
        "IndustryChain",
        ("name", "chain_name"),
        "集成电路",
    )

    assert resolved == "chain_IC0007"


def test_backfill_empty_layers_uses_real_anchor_subgraph() -> None:
    service = IndustryChainPanoramaService()
    layers = [
        {"key": "core_technology", "title": "核心技术", "total": 0, "items": []},
        {"key": "leading_enterprise", "title": "领军企业", "total": 0, "items": []},
        {"key": "leading_expert", "title": "领军专家", "total": 0, "items": []},
    ]
    graph = {
        "nodes": [
            {
                "id": "chain_IC0007",
                "type": "IndustryChain",
                "label": "集成电路",
                "subtitle": None,
            },
            {
                "id": "node_IC0007001",
                "type": "IndustryNode",
                "label": "集成电路设计",
                "subtitle": "上游",
            },
            {
                "id": "org_1",
                "type": "Organization",
                "label": "集成电路企业",
                "subtitle": None,
            },
        ],
        "edges": [],
    }

    result = service._backfill_empty_layers_from_graph(layers, graph, top_k=5)

    assert result[0]["items"] == [
        {
            "id": "node_IC0007001",
            "label": "集成电路设计",
            "type": "technology",
            "subtitle": "上游",
            "metric": None,
            "metricValue": None,
            "sourceTable": None,
            "sourceField": None,
            "sourceRecordId": None,
            "ingestBatch": None,
            "ingestTime": None,
        }
    ]
    assert result[1]["items"][0]["id"] == "org_1"
    assert result[2]["items"] == []
    assert result[0]["total"] == 1


def test_backfill_empty_layers_carries_subgraph_provenance() -> None:
    """回填分层的实体要带上子图节点已记录的溯源字段（查到即记），否则
    前端点击分层连线时源数据表/英文字段名只能显示「—」。"""
    service = IndustryChainPanoramaService()
    layers = [
        {"key": "leading_enterprise", "title": "领军企业", "total": 0, "items": []},
    ]
    graph = {
        "nodes": [
            {
                "id": "org_1",
                "type": "Organization",
                "label": "集成电路企业",
                "subtitle": None,
                "sourceTable": "dwd_org_stock_base",
                "sourceField": "org_id",
                "sourceRecordId": "org_1",
                "ingestBatch": "batch_20260901",
                "ingestTime": "2026-09-01 00:00:00",
            },
        ],
        "edges": [],
    }

    result = service._backfill_empty_layers_from_graph(layers, graph, top_k=5)

    assert result[0]["items"][0] == {
        "id": "org_1",
        "label": "集成电路企业",
        "type": "organization",
        "subtitle": None,
        "metric": None,
        "metricValue": None,
        "sourceTable": "dwd_org_stock_base",
        "sourceField": "org_id",
        "sourceRecordId": "org_1",
        "ingestBatch": "batch_20260901",
        "ingestTime": "2026-09-01 00:00:00",
    }


def test_backfill_enterprise_matches_secondary_organization_label() -> None:
    """organization_base 是入图打到几乎所有节点的基础标签，真企业靠叠加的
    Organization 标签识别，论文/专家不应混入领军企业层。"""
    service = IndustryChainPanoramaService()
    layers = [
        {"key": "leading_enterprise", "title": "领军企业", "total": 0, "items": []},
    ]
    graph = {
        "nodes": [
            {
                "id": "org_1",
                "type": "organization_base",
                "label": "深圳市劲拓自动化设备股份有限公司",
                "subtitle": None,
                "data": {"labels": ["organization_base", "Organization"]},
            },
            {
                "id": "paper_1",
                "type": "organization_base",
                "label": "人工智能产业分析论文",
                "subtitle": None,
                "data": {"labels": ["organization_base", "Paper"]},
            },
            {
                "id": "person_1",
                "type": "organization_base",
                "label": "某专家",
                "subtitle": None,
                "data": {"labels": ["organization_base", "Person"]},
            },
        ],
        "edges": [],
    }

    result = service._backfill_empty_layers_from_graph(layers, graph, top_k=5)

    assert [item["id"] for item in result[0]["items"]] == ["org_1"]
    assert result[0]["items"][0]["type"] == "organization"
    assert result[0]["total"] == 1


def test_backfill_dynamic_events_keeps_three_unique_real_events() -> None:
    service = IndustryChainPanoramaService()
    layers = [
        {
            "key": "flagship_achievement",
            "title": "产业动态事件",
            "total": 0,
            "items": [],
        }
    ]
    graph = {
        "nodes": [
            {"id": "event_1", "type": "Event", "label": "年报财务信息"},
            {"id": "event_2", "type": "Event", "label": "年报财务信息"},
            {"id": "event_3", "type": "Event", "label": "上市企业财务信息"},
            {"id": "event_4", "type": "Event", "label": "企业融资事件"},
            {"id": "event_5", "type": "Event", "label": "企业中标事件"},
        ],
        "edges": [],
    }

    result = service._backfill_empty_layers_from_graph(layers, graph, top_k=5)

    assert [item["label"] for item in result[0]["items"]] == [
        "年报财务信息",
        "上市企业财务信息",
        "企业融资事件",
    ]
    assert all(item["type"] == "event" for item in result[0]["items"])
    assert result[0]["total"] == 3


def test_filter_graph_keeps_chain_and_anchor_skeleton() -> None:
    """关系筛选裁边不能把链节点/锚点裁掉：链只经 HAS_NODE 连环节，筛选不含
    HAS_NODE（如只选产业链归属）时链会变成孤立点被丢弃，前端中心退化为
    虚拟节点、丢失链的溯源信息。骨架节点始终保留。"""
    service = IndustryChainPanoramaService()
    graph = {
        "nodes": [
            {
                "id": "chain_IC0007",
                "type": "IndustryChain",
                "label": "集成电路",
                "sourceTable": "dwd_industry_chain_info",
                "sourceField": "source_record_id",
            },
            {"id": "node_IC0007007", "type": "IndustryNode", "label": "芯片设计"},
            {"id": "org_1", "type": "Organization", "label": "某企业"},
            {"id": "paper_1", "type": "Paper", "label": "无关论文"},
        ],
        "edges": [
            {"source": "chain_IC0007", "target": "node_IC0007007", "label": "HAS_NODE"},
            {
                "source": "org_1",
                "target": "node_IC0007007",
                "label": "BELONGS_TO_NODE",
            },
            {"source": "paper_1", "target": "org_1", "label": "COVERS_CHAIN"},
        ],
    }

    # 页面「产业链归属」筛选：只保留 BELONGS_TO_NODE 边。
    result = service._filter_graph_by_relation_types(
        graph, ["BELONGS_TO_NODE", "COAUTHOR_WITH"], anchor_id="node_IC0007007"
    )

    # 链节点（经被裁掉的 HAS_NODE 连图）与锚点节点保留；无关论文被裁掉。
    assert [node["id"] for node in result["nodes"]] == [
        "chain_IC0007",
        "node_IC0007007",
        "org_1",
    ]
    assert [edge["label"] for edge in result["edges"]] == ["BELONGS_TO_NODE"]
    # 链节点的溯源字段随骨架保留，前端中心可展示真实溯源信息。
    chain = result["nodes"][0]
    assert chain["sourceTable"] == "dwd_industry_chain_info"


def test_filter_graph_without_skeleton_keeps_only_connected_nodes() -> None:
    """非骨架节点维持原行为：筛选后无保留边相连的节点照常裁掉。"""
    service = IndustryChainPanoramaService()
    graph = {
        "nodes": [
            {"id": "person_1", "type": "Person", "label": "专家A"},
            {"id": "person_2", "type": "Person", "label": "专家B"},
            {"id": "paper_1", "type": "Paper", "label": "论文"},
        ],
        "edges": [
            {"source": "person_1", "target": "person_2", "label": "COAUTHOR_WITH"},
            {"source": "person_1", "target": "paper_1", "label": "AUTHORED_BY"},
        ],
    }

    result = service._filter_graph_by_relation_types(graph, ["COAUTHOR_WITH"])

    assert [node["id"] for node in result["nodes"]] == ["person_1", "person_2"]
    assert [edge["label"] for edge in result["edges"]] == ["COAUTHOR_WITH"]


@pytest.mark.asyncio
async def test_expert_scan_ranks_research_fields_and_returns_real_nodes(monkeypatch) -> None:
    service = IndustryChainPanoramaService()

    async def _fake_list(client, label, limit, offset):
        assert label == "Person"
        assert limit == 500
        return [
            {
                "id": "person_org_only",
                "properties": {"name_zh": "机构匹配专家", "scholar_org": "芯片研究中心"},
            },
            {
                "id": "person_vlsi",
                "properties": {
                    "name_zh": "芯片设计专家",
                    "research_fields": "VLSI Design;System-on-Chip Design",
                },
            },
            {
                "id": "person_unrelated",
                "properties": {"name_zh": "无关专家", "research_fields": "Ecology"},
            },
        ]

    monkeypatch.setattr(service, "_list_by_label_throttled", _fake_list)

    result = await service._search_by_keyword(
        _FakeGraphClient(),
        "Person",
        {"keyword_props": ("scholar_org", "research_fields", "bio_zh")},
        "集成电路",
        3,
    )

    assert [node["id"] for node in result] == ["person_vlsi", "person_org_only"]


@pytest.mark.asyncio
async def test_low_altitude_economy_scans_bounded_pages_for_three_experts(
    monkeypatch,
) -> None:
    service = IndustryChainPanoramaService()
    requested_offsets: list[int] = []

    async def _fake_list(client, label, limit, offset):
        assert label == "Person"
        assert limit == 500
        requested_offsets.append(offset)
        candidates = {
            500: [
                {
                    "id": "person_uav_network",
                    "properties": {
                        "name_zh": "无人机网络专家",
                        "research_fields": "Unmanned Aerial Vehicle Networks",
                    },
                }
            ],
            1000: [
                {
                    "id": "person_agricultural_uav",
                    "properties": {
                        "name_zh": "农业无人机专家",
                        "research_fields": "Agricultural UAV Technology",
                    },
                }
            ],
            2000: [
                {
                    "id": "person_uav_vision",
                    "properties": {
                        "name_zh": "无人机视觉专家",
                        "research_fields": "Unmanned Aerial Vehicle Vision",
                    },
                }
            ],
        }
        return candidates.get(offset, [])

    monkeypatch.setattr(service, "_list_by_label_throttled", _fake_list)

    result = await service._search_by_keyword(
        _FakeGraphClient(),
        "Person",
        {"keyword_props": ("scholar_org", "research_fields", "bio_zh")},
        "低空经济",
        5,
    )

    assert sorted(requested_offsets) == [0, 500, 1000, 1500, 2000]
    assert [node["id"] for node in result] == [
        "person_uav_network",
        "person_agricultural_uav",
        "person_uav_vision",
    ]


def test_graph_node_uses_chain_name_as_display_label() -> None:
    service = IndustryChainPanoramaService()

    result = service._node_to_graph_node(
        {
            "id": "chain_IC0007",
            "labels": ["IndustryChain"],
            "properties": {"chain_name": "集成电路"},
        }
    )

    assert result["label"] == "集成电路"


def test_graph_edge_exposes_numeric_confidence_from_chain_score() -> None:
    service = IndustryChainPanoramaService()

    result = service._edge_to_graph_edge(
        {
            "source": "org_1",
            "target": "node_IC9901036",
            "type": "BELONGS_TO_NODE",
            "properties": {
                "chain_score": 97.78,
                "source_table": "dwd_org_industry_chain_dtl",
            },
        }
    )

    assert result["confidence"] == pytest.approx(0.9778)
    assert result["data"]["chain_score"] == 97.78


@pytest.mark.asyncio
async def test_fetch_graph_expands_chain_structure_when_anchor_present() -> None:
    """锚点子图被 News 刷满 limit 时，HAS_NODE 环节和叶子环节的 BELONGS_TO_NODE
    企业边（chain_score 置信度来源）仍要进图。"""
    service = IndustryChainPanoramaService()

    class _ChainGraphClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def get_subgraph(self, vid, *, depth=1, limit=50, edge_type=None, space=None):
            self.calls.append({"vid": vid, "depth": depth, "edge_type": edge_type})
            if vid == "chain_IC0007" and edge_type is None:
                return {
                    "nodes": [
                        {"id": "chain_IC0007", "labels": ["IndustryChain"]},
                        *[{"id": f"news_{i}", "labels": ["News"]} for i in range(60)],
                    ],
                    "edges": [
                        {
                            "source": f"news_{i}",
                            "target": "chain_IC0007",
                            "type": "COVERS_CHAIN",
                            "properties": {},
                        }
                        for i in range(60)
                    ],
                }
            if vid == "chain_IC0007" and edge_type == "HAS_NODE":
                return {
                    "nodes": [
                        {"id": "chain_IC0007", "labels": ["IndustryChain"]},
                        {
                            "id": "node_IC0007001",
                            "labels": ["IndustryNode"],
                            "properties": {"node_type": "1", "node_name": "集成电路设计"},
                        },
                        {
                            "id": "node_IC0007005",
                            "labels": ["IndustryNode"],
                            "properties": {
                                "node_type": "2",
                                "node_imp_level": "1",
                                "node_name": "集成电路制造设备",
                            },
                        },
                        {
                            "id": "node_IC0007004",
                            "labels": ["IndustryNode"],
                            "properties": {"node_type": "2", "node_name": "集成电路制造"},
                        },
                    ],
                    "edges": [
                        {
                            "source": "chain_IC0007",
                            "target": "node_IC0007001",
                            "type": "HAS_NODE",
                            "properties": {},
                        },
                        {
                            "source": "chain_IC0007",
                            "target": "node_IC0007005",
                            "type": "HAS_NODE",
                            "properties": {},
                        },
                        {
                            "source": "chain_IC0007",
                            "target": "node_IC0007004",
                            "type": "HAS_NODE",
                            "properties": {},
                        },
                    ],
                }
            if vid in {"node_IC0007004", "node_IC0007005"} and edge_type == "BELONGS_TO_NODE":
                return {
                    "nodes": [
                        {"id": vid, "labels": ["IndustryNode"]},
                        {
                            "id": "org_1",
                            "labels": ["organization_base", "Organization"],
                            "properties": {"name_cn": "某半导体股份有限公司"},
                        },
                    ],
                    "edges": [
                        {
                            "source": "org_1",
                            "target": vid,
                            "type": "BELONGS_TO_NODE",
                            "properties": {"chain_score": 97.78},
                        }
                    ],
                }
            return {"nodes": [], "edges": []}

    client = _ChainGraphClient()
    graph = await service._fetch_graph(client, [], "chain_IC0007", 2)

    node_ids = {n["id"] for n in graph["nodes"]}
    assert "node_IC0007004" in node_ids
    assert "org_1" in node_ids
    belongs_edges = [e for e in graph["edges"] if e["label"] == "BELONGS_TO_NODE"]
    assert belongs_edges and belongs_edges[0]["confidence"] == pytest.approx(0.9778)
    # 只探叶子环节（node_type=2）且重点环节（node_imp_level=1）优先，分类环节
    # 不打企业边请求。
    probed = [c for c in client.calls if c["edge_type"] == "BELONGS_TO_NODE"]
    assert [c["vid"] for c in probed] == ["node_IC0007005", "node_IC0007004"]


def test_backfill_dynamic_events_uses_chain_news() -> None:
    """链上 News 是产业动态的载体，事件层为空时用新闻标题回填。"""
    service = IndustryChainPanoramaService()
    layers = [{"key": "flagship_achievement", "title": "产业动态事件", "total": 0, "items": []}]
    graph = {
        "nodes": [
            {"id": "news_1", "type": "News", "label": "低空经济产业政策发布"},
            {"id": "news_2", "type": "News", "label": "无人机新品发布"},
        ],
        "edges": [],
    }

    result = service._backfill_empty_layers_from_graph(layers, graph, top_k=5)

    assert [item["label"] for item in result[0]["items"]] == [
        "低空经济产业政策发布",
        "无人机新品发布",
    ]
    assert all(item["type"] == "event" for item in result[0]["items"])
    assert result[0]["total"] == 2


def test_merge_graphs_dedupes_nodes_and_edges_base_first() -> None:
    service = IndustryChainPanoramaService()
    base = {
        "nodes": [
            {"id": "chain_1", "label": "人工智能"},
            {"id": "org_1", "label": "锚点侧企业"},
        ],
        "edges": [
            {"source": "news_1", "target": "chain_1", "label": "COVERS_CHAIN"},
        ],
    }
    extra = {
        "nodes": [
            {"id": "org_1", "label": "种子侧企业（重复）"},
            {"id": "person_1", "label": "专家"},
        ],
        "edges": [
            {"source": "news_1", "target": "chain_1", "label": "COVERS_CHAIN"},
            {"source": "person_1", "target": "org_1", "label": "AFFILIATED_WITH"},
        ],
    }

    merged = service._merge_graphs(base, extra)

    assert [node["id"] for node in merged["nodes"]] == ["chain_1", "org_1", "person_1"]
    # 重复节点保留 base 版本。
    assert merged["nodes"][1]["label"] == "锚点侧企业"
    assert [edge["label"] for edge in merged["edges"]] == ["COVERS_CHAIN", "AFFILIATED_WITH"]


@pytest.mark.asyncio
async def test_query_refills_still_empty_layers_from_seed_expansion(monkeypatch) -> None:
    panorama_module._panorama_cache.clear()
    """锚点子图过薄（如新链只挂了新闻）时空层回填仍拿不到实体：要用分层
    种子再扩一轮子图合并回填，领军企业/领军专家不能因为锚点解析到薄链
    而从有数据变成 0。"""
    service = IndustryChainPanoramaService()
    fetch_graph_anchors: list[str | None] = []

    async def _fake_fetch_layers(client, industry, top_k):
        return (
            [
                {
                    "key": "core_technology",
                    "title": "核心技术",
                    "total": 1,
                    "items": [{"id": "kw_1", "label": "人工智能"}],
                },
                {"key": "leading_enterprise", "title": "领军企业", "total": 0, "items": []},
                {"key": "leading_expert", "title": "领军专家", "total": 0, "items": []},
                {"key": "flagship_achievement", "title": "产业动态事件", "total": 0, "items": []},
            ],
            ["person_1"],
        )

    async def _fake_fetch_graph(client, seed_vids, anchor_id, depth, relation_types=None):
        fetch_graph_anchors.append(anchor_id)
        if anchor_id:
            # 锚点（薄链）子图：只有链节点和挂链新闻，没有任何企业/专家。
            return {
                "nodes": [
                    {"id": "chain_1", "type": "IndustryChain", "label": "人工智能"},
                    {"id": "news_1", "type": "News", "label": "人工智能产业政策发布"},
                ],
                "edges": [{"source": "news_1", "target": "chain_1", "label": "COVERS_CHAIN"}],
            }
        # 种子扩展子图：专家及其任职企业（AFFILIATED_WITH）。
        return {
            "nodes": [
                {"id": "person_1", "type": "Person", "label": "人工智能专家"},
                {"id": "org_1", "type": "Organization", "label": "人工智能企业"},
            ],
            "edges": [{"source": "person_1", "target": "org_1", "label": "AFFILIATED_WITH"}],
        }

    async def _fake_resolve_anchor(client, industry, anchor_id):
        return "chain_1"

    class _GraphCtx:
        async def __aenter__(self):
            return _FakeGraphClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service, "_fetch_layers", _fake_fetch_layers)
    monkeypatch.setattr(service, "_fetch_graph", _fake_fetch_graph)
    monkeypatch.setattr(service, "_resolve_anchor_from_keyword", _fake_resolve_anchor)
    monkeypatch.setattr("service.industry_chain_panorama.graph_api", lambda **kwargs: _GraphCtx())

    result = await service.query(industry="人工智能", depth=2, top_k=5)

    # 第二轮用分层种子扩展（anchor=None），两轮子图合并。
    assert fetch_graph_anchors == ["chain_1", None]
    layer_by_key = {layer["key"]: layer for layer in result["layers"]}
    assert layer_by_key["flagship_achievement"]["items"][0]["id"] == "news_1"
    assert layer_by_key["leading_expert"]["items"][0]["id"] == "person_1"
    assert layer_by_key["leading_enterprise"]["items"][0]["id"] == "org_1"
    graph_ids = {node["id"] for node in result["graph"]["nodes"]}
    assert graph_ids == {"chain_1", "news_1", "person_1", "org_1"}


@pytest.mark.asyncio
async def test_query_skips_seed_expansion_when_layers_already_filled(monkeypatch) -> None:
    panorama_module._panorama_cache.clear()
    """分层全部非空时不做种子二次扩展，锚点子图行为与既有验证结果保持一致。"""
    service = IndustryChainPanoramaService()
    fetch_graph_anchors: list[str | None] = []

    async def _fake_fetch_layers(client, industry, top_k):
        return (
            [
                {
                    "key": "core_technology",
                    "title": "核心技术",
                    "total": 1,
                    "items": [{"id": "kw_1", "label": "人工智能"}],
                },
                {
                    "key": "leading_enterprise",
                    "title": "领军企业",
                    "total": 1,
                    "items": [{"id": "org_1", "label": "人工智能企业"}],
                },
                {
                    "key": "leading_expert",
                    "title": "领军专家",
                    "total": 1,
                    "items": [{"id": "person_1", "label": "人工智能专家"}],
                },
                {
                    "key": "flagship_achievement",
                    "title": "产业动态事件",
                    "total": 1,
                    "items": [{"id": "news_1", "label": "人工智能产业政策发布"}],
                },
            ],
            ["person_1"],
        )

    async def _fake_fetch_graph(client, seed_vids, anchor_id, depth, relation_types=None):
        fetch_graph_anchors.append(anchor_id)
        return {
            "nodes": [
                {"id": "chain_1", "type": "IndustryChain", "label": "人工智能"},
                {"id": "news_1", "type": "News", "label": "人工智能产业政策发布"},
            ],
            "edges": [{"source": "news_1", "target": "chain_1", "label": "COVERS_CHAIN"}],
        }

    async def _fake_resolve_anchor(client, industry, anchor_id):
        return "chain_1"

    class _GraphCtx:
        async def __aenter__(self):
            return _FakeGraphClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service, "_fetch_layers", _fake_fetch_layers)
    monkeypatch.setattr(service, "_fetch_graph", _fake_fetch_graph)
    monkeypatch.setattr(service, "_resolve_anchor_from_keyword", _fake_resolve_anchor)
    monkeypatch.setattr("service.industry_chain_panorama.graph_api", lambda **kwargs: _GraphCtx())

    result = await service.query(industry="人工智能", depth=2, top_k=5)

    assert fetch_graph_anchors == ["chain_1"]
    assert {node["id"] for node in result["graph"]["nodes"]} == {"chain_1", "news_1"}
