from __future__ import annotations

import pytest

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
    )

    assert summary == {
        "industry": "人工智能",
        "totalNodes": 3,
        "totalEdges": 3,
        "nodesByLabel": {"核心技术": 2, "领军企业": 1, "领军专家": 0},
        "edgesByType": {"HAS_KEYWORD": 2, "RELATED_TO": 1},
    }


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


def test_select_layer_definitions_compacts_when_no_anchor() -> None:
    service = IndustryChainPanoramaService()

    compact = service._select_layer_definitions(True)
    full = service._select_layer_definitions(False)

    assert [item["key"] for item in compact] == ["core_technology", "leading_enterprise"]
    assert len(full) == 4


@pytest.mark.asyncio
async def test_query_falls_back_to_compact_overview_when_keyword_misses(monkeypatch) -> None:
    service = IndustryChainPanoramaService()

    async def _fake_fetch_layers(client, industry, top_k, compact_without_anchor):
        if industry == "人工智能":
            return (
                [
                    {"key": "core_technology", "title": "核心技术", "total": 0, "items": []},
                    {"key": "leading_enterprise", "title": "领军企业", "total": 0, "items": []},
                ],
                [],
            )
        assert industry is None
        assert compact_without_anchor is True
        return (
            [
                {
                    "key": "core_technology",
                    "title": "核心技术",
                    "total": 1,
                    "items": [{"id": "kw_1"}],
                },
                {
                    "key": "leading_enterprise",
                    "title": "领军企业",
                    "total": 1,
                    "items": [{"id": "org_1"}],
                },
            ],
            ["kw_1"],
        )

    async def _fake_fetch_graph(client, seed_vids, anchor_id, depth):
        return {
            "nodes": [{"id": seed_vids[0], "label": seed_vids[0]}] if seed_vids else [],
            "edges": [],
        }

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

    assert result["source"]["reason"] == "keyword_fallback_overview"
    assert [layer["key"] for layer in result["layers"]] == ["core_technology", "leading_enterprise"]
    assert result["summary"]["totalNodes"] == 2


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
        }
    ]
    assert result[1]["items"][0]["id"] == "org_1"
    assert result[2]["items"] == []
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
