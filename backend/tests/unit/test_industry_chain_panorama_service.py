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
