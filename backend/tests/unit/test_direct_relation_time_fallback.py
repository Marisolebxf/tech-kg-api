from unittest.mock import AsyncMock

import pytest
from infra.graph_api_client import GraphAPIError
from service import expert_direct_relation as module
from service.direct_relation_time import paper_time, parse_time, select_time
from service.expert_direct_relation import ExpertDirectRelationService


def path(vid, **props):
    return {
        "nodes": [
            {"id": "person_a"},
            {"id": vid, "properties": props},
            {"id": "person_b"},
        ]
    }


def row(value=None):
    return {
        "relation_key": "a:b",
        "expert_a_id": "person_a",
        "expert_b_id": "person_b",
        "relation_time": value,
    }


@pytest.mark.parametrize(
    "value,display,precision",
    [
        (2020, "2020", "year"),
        ("2020-2", "2020-02", "month"),
        ("2020-02-29", "2020-02-29", "day"),
        ("2020-02-29T10:20:30+08:00", "2020-02-29", "day"),
        ("2020年2月29日", "2020-02-29", "day"),
    ],
)
def test_precision_is_preserved(value, display, precision):
    evidence = parse_time(value, source="test")
    assert evidence["display"] == display
    assert evidence["precision"] == precision


@pytest.mark.parametrize(
    "value", [None, True, {}, "", "unknown", "2021-02-29", "2020-13", "2020-00-10"]
)
def test_invalid_dates_are_unknown(value):
    assert parse_time(value, source="test") is None


def test_publication_date_priority_and_invalid_field_fallback():
    assert (
        paper_time(
            {"properties": {"publish_date": "2020-06-12", "publication_year": "2021"}}
        )["display"]
        == "2020-06-12"
    )
    assert (
        paper_time(
            {"properties": {"publish_date": "invalid", "publication_year": "2021"}}
        )["display"]
        == "2021"
    )


def test_month_boundaries_do_not_invent_dates():
    evidence = [parse_time("2020", source="test")]
    assert select_time(evidence, "2020-02", "2020-12") is None
    assert select_time(evidence, "2020-01", "2020-11") is None
    assert select_time(evidence, "2020-01", "2020-12")["display"] == "2020"
    month = [parse_time("2020-02", source="test")]
    assert select_time(month, "2020-02-02", "2020-02-29") is None
    assert select_time(month, "2020-02-01", "2020-02-29") is not None


@pytest.mark.asyncio
async def test_edge_time_precedes_paper_fallback():
    client = AsyncMock()
    rows = [row("2020-05-06")]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    client.search_paths.assert_not_awaited()
    assert rows[0]["relation_time_source"] == "COAUTHOR_WITH.relation_time"


@pytest.mark.asyncio
async def test_invalid_edge_time_falls_back_and_reuses_titles():
    client = AsyncMock()
    client.search_paths.return_value = {
        "items": [path("paper_1", publication_year="2020", title="共同论文")]
    }
    rows = [row("bad date")]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    await service._attach_representative_achievements(client, rows)
    assert client.search_paths.await_count == 1
    assert rows[0]["relation_time"] == "2020"
    assert rows[0]["relation_time_paper_ids"] == ["paper_1"]
    assert rows[0]["representative_achievements"][0]["title"] == "共同论文"


@pytest.mark.asyncio
async def test_filter_selects_latest_in_range_not_latest_overall():
    client = AsyncMock()
    client.search_paths.return_value = {
        "items": [
            path("paper_1", publication_year="2020"),
            path("paper_2", publication_year="2024"),
        ]
    }
    rows = [row()]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    assert rows[0]["relation_time"] == "2024"
    result = service._filter_rows_by_time(rows, "2020-01", "2020-12")
    assert result[0]["relation_time"] == "2020"
    assert result[0]["relation_time_paper_ids"] == ["paper_1"]
    assert service._build_item(result[0])["lastUpdatedAt"] == "2020"


@pytest.mark.asyncio
async def test_all_missing_times_keep_unrestricted_relation_only():
    client = AsyncMock()
    client.search_paths.return_value = {"items": [path("paper_1", title="undated")]}
    rows = [row()]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    assert service._filter_rows_by_time(rows, None, None) == rows
    assert rows[0]["relation_time"] is None
    assert rows[0]["relation_time_status"] == "missing"
    assert service._filter_rows_by_time(rows, "2015-01", "2026-08") == []


@pytest.mark.asyncio
async def test_pagination_dedup_and_alias_hydrated_properties(monkeypatch):
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 2)
    client = AsyncMock()
    client.search_paths.side_effect = [
        {"items": [path("paper_1"), path("paper_2", publication_year="2020")]},
        {"items": [path("1", publication_year="2024")]},
    ]
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert len(rows[0]["relation_time_evidence"]) == 2
    assert rows[0]["relation_time"] == "2024"
    requests = [call.args[0] for call in client.search_paths.await_args_list]
    assert [request["offset"] for request in requests] == [0, 2]
    assert all(request["countTotal"] is False for request in requests)
    assert requests[0]["steps"][0]["edgeType"] == "AUTHORED_BY"
    assert requests[0]["steps"][0]["direction"] == "in"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [GraphAPIError("unavailable"), TimeoutError("budget")]
)
async def test_failed_query_does_not_publish_partial_time(failure):
    client = AsyncMock()
    client.search_paths.side_effect = failure
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["relation_time"] is None
    assert rows[0]["relation_time_status"] == "unavailable"


@pytest.mark.asyncio
async def test_overflow_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(module, "_MAX_TIME_PATHS", 2)
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 2)
    client = AsyncMock()
    client.search_paths.side_effect = [
        {
            "items": [
                path("paper_1", publication_year="2020"),
                path("paper_2", publication_year="2021"),
            ]
        },
        {"items": [path("paper_3", publication_year="2024")]},
    ]
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["relation_time_status"] == "unavailable"
    assert rows[0]["relation_time"] is None


@pytest.mark.asyncio
async def test_exact_budget_finishes_with_empty_lookahead(monkeypatch):
    monkeypatch.setattr(module, "_MAX_TIME_PATHS", 2)
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 2)
    client = AsyncMock()
    client.search_paths.side_effect = [
        {
            "items": [
                path("paper_1", publication_year="2020"),
                path("paper_2", publication_year="2021"),
            ]
        },
        {"items": []},
    ]
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["relation_time_status"] == "verified"
    assert rows[0]["relation_time"] == "2021"


@pytest.mark.asyncio
async def test_techkg_keeps_authored_direction(monkeypatch):
    monkeypatch.setattr(module, "effective_graph_space", lambda: "techkg")
    client = AsyncMock()
    client.search_paths.return_value = {"items": []}
    await ExpertDirectRelationService()._resolve_relation_times(client, [row()])
    request = client.search_paths.await_args.args[0]
    assert [step["edgeType"] for step in request["steps"]] == ["AUTHORED", "AUTHORED"]
    assert [step["direction"] for step in request["steps"]] == ["out", "in"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "years,expected",
    [
        (
            [
                2015,
                2016,
                2018,
                2019,
                2016,
                2015,
                2018,
                2015,
                2018,
                2016,
                2018,
                2015,
                2016,
                2018,
                2017,
                2020,
                2016,
                2017,
            ],
            "2020",
        ),
        (
            [
                2022,
                2022,
                2022,
                2021,
                2022,
                2023,
                2023,
                2021,
                2022,
                None,
                2022,
                None,
                2020,
                2021,
                2023,
            ],
            "2023",
        ),
        ([None] * 11, None),
    ],
)
async def test_three_verified_space_snapshots(years, expected):
    """Sanitized publication-year evidence read from kgcfg_1808ec65d on 2026-11-12."""
    client = AsyncMock()
    client.search_paths.return_value = {
        "items": [
            path(f"paper_{i}", publication_year=str(year) if year else None)
            for i, year in enumerate(years)
        ]
    }
    rows = [row()]
    service = ExpertDirectRelationService()
    await service._resolve_relation_times(client, rows)
    result = service._filter_rows_by_time(rows, "2015-01", "2026-08")
    assert bool(result) == bool(expected)
    if result:
        item = service._build_item(result[0])
        assert item["lastUpdatedAt"] == expected
        assert item["relationTimePrecision"] == "year"
        assert item["relationTimeSource"] == "shared_paper.publication_year"


@pytest.mark.asyncio
async def test_query_integration_filters_and_keeps_missing_time_status(monkeypatch):
    module.clear_caches()
    client = AsyncMock()
    client.get_node.side_effect = lambda vid: {
        "id": vid,
        "labels": ["Person"],
        "properties": {"name_zh": vid, "source_table": "test"},
    }
    client.get_node_edges.return_value = [
        {"source": "person_a", "target": "person_b", "properties": {}}
    ]
    client.search_paths.return_value = {
        "items": [path("paper_1", publication_year="2020")]
    }

    class Context:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(module, "graph_api", lambda **kwargs: Context())
    result = await ExpertDirectRelationService().query(
        expert_a_id="person_a",
        expert_b_id="person_b",
        start_time="2015-01",
        end_time="2026-08",
    )
    assert result["total"] == 1
    assert result["items"][0]["lastUpdatedAt"] == "2020"
    module.clear_caches()
    client.search_paths.side_effect = GraphAPIError("unavailable")
    result = await ExpertDirectRelationService().query(
        expert_a_id="person_a",
        expert_b_id="person_b",
        start_time="2015-01",
        end_time="2026-08",
    )
    assert result["total"] == 0
    assert result["source"]["relationTimeStatus"] == "unavailable"
    assert result["source"]["reason"] == "graph_api_error"
    assert not module._result_cache


@pytest.mark.asyncio
async def test_paper_path_never_creates_direct_relationship_without_edge(monkeypatch):
    module.clear_caches()
    client = AsyncMock()
    client.get_node.side_effect = lambda vid: {
        "id": vid,
        "properties": {"source_table": "test"},
    }
    client.get_node_edges.return_value = []

    class Context:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(module, "graph_api", lambda **kwargs: Context())
    result = await ExpertDirectRelationService().query(
        expert_a_id="person_a", expert_b_id="person_b"
    )
    assert result["total"] == 0
    client.search_paths.assert_not_awaited()


def test_response_model_preserves_time_provenance():
    from biz.schema.expert_direct_relation import DirectRelationItem

    service = ExpertDirectRelationService()
    value = row()
    value["relation_time_evidence"] = [
        parse_time("2020", source="shared_paper.publication_year", paper_id="paper_1")
    ]
    value["relation_time_status"] = "verified"
    service._filter_rows_by_time([value], None, None)
    item = DirectRelationItem.model_validate(service._build_item(value)).model_dump()
    assert item["lastUpdatedAt"] == "2020"
    assert item["relationTimeSource"] == "shared_paper.publication_year"
    assert item["relationTimePrecision"] == "year"
    assert item["relationTimePaperIds"] == ["paper_1"]


@pytest.mark.asyncio
async def test_later_page_failure_discards_partial_evidence(monkeypatch):
    monkeypatch.setattr(module, "_TIME_PATH_PAGE_SIZE", 1)
    client = AsyncMock()
    client.search_paths.side_effect = [
        {"items": [path("paper_1", publication_year="2020")]},
        GraphAPIError("page 2 failed"),
    ]
    rows = [row()]
    await ExpertDirectRelationService()._resolve_relation_times(client, rows)
    assert rows[0]["relation_time"] is None
    assert rows[0]["relation_time_evidence"] == []
    assert rows[0]["relation_time_status"] == "unavailable"
