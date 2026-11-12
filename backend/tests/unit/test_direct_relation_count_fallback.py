from unittest.mock import AsyncMock

import pytest
from biz.schema.expert_direct_relation import DirectRelationItem
from infra.graph_api_client import GraphAPIError
from service import expert_direct_relation as module
from service.expert_direct_relation import ExpertDirectRelationService


def path(vid, **props):
    return {
        "nodes": [
            {"id": "person_a"},
            {"id": vid, "properties": props},
            {"id": "person_b"},
        ]
    }


def row(**props):
    return ExpertDirectRelationService()._build_row(
        {"id": "person_a"}, {"id": "person_b"}, {"properties": props}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [18, 15, 11])
async def test_verified_examples_count_undated_papers_and_reuse_titles(count):
    client = AsyncMock()
    client.search_paths.return_value = {
        "items": [path(f"paper_{i}", title=f"论文 {i}") for i in range(count)]
    }
    rows = [row()]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    await service._attach_representative_achievements(client, rows)
    item = DirectRelationItem.model_validate(service._build_item(rows[0])).model_dump()
    assert item["coPaperCount"] == count
    assert item["coPaperCountSource"] == "shared_paper.vid"
    assert item["coPaperCountStatus"] == "verified"
    assert item["lastUpdatedAt"] is None
    assert len(item["representativeAchievements"]) == 3
    assert ["证据数量", count] in item["detailRows"]
    assert client.search_paths.await_count == 1
    provenance = service._build_provenance(rows, {})
    evidence = next(e for e in provenance["evidences"] if e["title"].startswith("直接关系"))
    assert f"共同论文 {count} 篇" in evidence["summary"]
    assert "shared_paper.vid" in evidence["summary"]
    assert evidence["sourceField"] == "VID (distinct)"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, "0", 7, " 18 "])
async def test_valid_edge_count_including_zero_is_retained(value):
    client = AsyncMock()
    client.search_paths.return_value = {"items": [path("paper_1")]}
    rows = [row(co_paper_count=value, count=999)]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["co_paper_count"] == int(value)
    assert rows[0]["co_paper_count_source"] == "COAUTHOR_WITH.co_paper_count"
    assert rows[0]["evidence_count"] == int(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "", "bad", -1, "-1", 1.9, "1.5", True, {}, []])
async def test_missing_or_invalid_count_uses_complete_paper_query(value):
    client = AsyncMock()
    client.search_paths.return_value = {"items": [path("paper_1")]}
    rows = [row(co_paper_count=value, relation_time="2020")]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["co_paper_count"] == 1
    assert rows[0]["relation_time_source"] == "COAUTHOR_WITH.relation_time"
    assert rows[0]["relation_time"] == "2020"


def test_legacy_count_and_explicit_zero_precedence():
    assert row(count="12")["co_paper_count_source"] == "COAUTHOR_WITH.count"
    assert row(count="12")["co_paper_count"] == 12
    assert row(co_paper_count=0, count=12)["co_paper_count"] == 0


@pytest.mark.asyncio
async def test_valid_edge_time_and_count_skip_full_scan():
    client = AsyncMock()
    rows = [row(co_paper_count=0, relation_time="2020")]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    client.search_paths.assert_not_awaited()
    assert rows[0]["co_paper_count"] == 0


@pytest.mark.asyncio
async def test_full_pagination_deduplicates_raw_and_prefixed_vids(monkeypatch):
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 2)
    client = AsyncMock()
    client.search_paths.side_effect = [
        {"items": [path("paper_1", publication_year="2020"), path("paper_2")]},
        {"items": [path("1"), path("paper_3", publication_year="2024")]},
        {"items": []},
    ]
    rows = [row()]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    rows = service._filter_rows_by_time(rows, "2020-01", "2020-12")
    assert rows[0]["relation_time"] == "2020"
    assert service._build_item(rows[0])["coPaperCount"] == 3
    assert [c.args[0]["offset"] for c in client.search_paths.await_args_list] == [0, 2, 4]
    assert all(not c.args[0]["steps"][0]["targetFilters"] for c in client.search_paths.await_args_list)


@pytest.mark.asyncio
async def test_successful_empty_scan_is_verified_zero():
    client = AsyncMock()
    client.search_paths.return_value = {"items": []}
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["co_paper_count"] == 0
    assert rows[0]["co_paper_count_status"] == "verified"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [GraphAPIError("failed"), TimeoutError("budget")])
async def test_count_failure_keeps_edge_time_but_never_publishes_partial_count(monkeypatch, failure):
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 1)
    client = AsyncMock()
    client.search_paths.side_effect = [{"items": [path("paper_1")]}, failure]
    rows = [row(relation_time="2020")]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    item = DirectRelationItem.model_validate(service._build_item(rows[0])).model_dump()
    assert item["coPaperCount"] is None
    assert item["coPaperCountStatus"] == "unavailable"
    assert item["lastUpdatedAt"] == "2020"
    assert item["relationTimeStatus"] == "verified"
    assert ["证据数量", "暂不可用"] in item["detailRows"]


@pytest.mark.asyncio
async def test_failed_time_fallback_keeps_valid_edge_count():
    client = AsyncMock()
    client.search_paths.side_effect = GraphAPIError("failed")
    rows = [row(co_paper_count=7)]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    item = service._build_item(rows[0])
    assert item["coPaperCount"] == 7
    assert item["coPaperCountStatus"] == "verified"
    assert item["relationTimeStatus"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{}, {"items": None}, {"items": {}}, {"items": [None]}, {"items": [{"nodes": []}]}])
async def test_malformed_path_response_does_not_become_zero(response):
    client = AsyncMock()
    client.search_paths.return_value = response
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["co_paper_count"] is None
    assert rows[0]["co_paper_count_status"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("overflow", [False, True])
async def test_budget_lookahead_distinguishes_complete_and_truncated_count(monkeypatch, overflow):
    monkeypatch.setattr(module, "_MAX_TIME_PATHS", 2)
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 2)
    client = AsyncMock()
    client.search_paths.side_effect = [
        {"items": [path("paper_1"), path("paper_2")]},
        {"items": [path("paper_3")] if overflow else []},
    ]
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["co_paper_count"] == (None if overflow else 2)
    assert rows[0]["co_paper_count_status"] == ("unavailable" if overflow else "verified")


@pytest.mark.asyncio
async def test_query_returns_18_and_does_not_cache_count_failure(monkeypatch):
    module.clear_caches()
    client = AsyncMock()
    client.get_node.side_effect = lambda vid: {"id": vid, "properties": {}}
    client.get_node_edges.return_value = [{
        "source": "person_a", "target": "person_b", "properties": {"relation_time": "2020"}
    }]
    client.search_paths.side_effect = GraphAPIError("count scan failed")

    class Context:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(module, "graph_api", lambda **kwargs: Context())
    service = ExpertDirectRelationService()
    result = await service.query(expert_a_id="person_a", expert_b_id="person_b")
    assert result["items"][0]["coPaperCount"] is None
    assert result["source"]["coPaperCountStatus"] == "unavailable"
    assert not module._result_cache
    client.search_paths.side_effect = None
    client.search_paths.return_value = {"items": [path(f"paper_{i}") for i in range(18)]}
    result = await service.query(expert_a_id="person_a", expert_b_id="person_b")
    assert result["items"][0]["coPaperCount"] == 18
    assert result["items"][0]["coPaperCountSource"] == "shared_paper.vid"
    assert result["items"][0]["lastUpdatedAt"] == "2020"
    assert module._result_cache
    module.clear_caches()
