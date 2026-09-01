from __future__ import annotations

import pytest

from service.industry_chain_panorama import IndustryChainPanoramaService


class _FakeGraphClient:
    def __init__(self) -> None:
        self.resolve_calls: list[str] = []

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
async def test_search_by_keyword_scans_pages_in_batches_and_stops_on_first_hit_batch(monkeypatch) -> None:
    service = IndustryChainPanoramaService()
    requested_offsets: list[int] = []

    async def _fake_safe_search_nodes(client, label, prop, industry, top_k):
        return {"items": []}

    async def _fake_list_by_label_throttled(client, label, limit, offset):
        requested_offsets.append(offset)
        if offset == 0:
            return [
                {"id": "kw_1", "properties": {"keyword": "人工智能芯片"}},
                {"id": "kw_2", "properties": {"keyword": "人工智能平台"}},
            ]
        return [{"id": f"kw_{offset}", "properties": {"keyword": "无关字段"}}]

    monkeypatch.setattr(
        IndustryChainPanoramaService,
        "_safe_search_nodes",
        staticmethod(_fake_safe_search_nodes),
    )
    monkeypatch.setattr(
        service,
        "_list_by_label_throttled",
        _fake_list_by_label_throttled,
    )

    result = await service._search_by_keyword(
        client=object(),
        label="Keyword",
        definition={"keyword_props": ("keyword",)},
        industry="人工智能",
        top_k=2,
    )

    assert [node["id"] for node in result] == ["kw_1", "kw_2"]
    assert requested_offsets == [0, 500]


def test_build_summary_counts_only_returned_layer_items_and_graph_edges() -> None:
    service = IndustryChainPanoramaService()

    summary = service._build_summary(
        '人工智能',
        [
            {'key': 'core_technology', 'title': '核心技术', 'items': [{'id': 'kw_1'}, {'id': 'kw_2'}]},
            {'key': 'leading_enterprise', 'title': '领军企业', 'items': [{'id': 'org_1'}]},
            {'key': 'leading_expert', 'title': '领军专家', 'items': []},
        ],
        {
            'nodes': [{'id': 'kw_1'}, {'id': 'org_1'}],
            'edges': [
                {'label': 'HAS_KEYWORD'},
                {'label': 'HAS_KEYWORD'},
                {'label': 'RELATED_TO'},
            ],
        },
    )

    assert summary == {
        'industry': '人工智能',
        'totalNodes': 3,
        'totalEdges': 3,
        'nodesByLabel': {'核心技术': 2, '领军企业': 1, '领军专家': 0},
        'edgesByType': {'HAS_KEYWORD': 2, 'RELATED_TO': 1},
    }
