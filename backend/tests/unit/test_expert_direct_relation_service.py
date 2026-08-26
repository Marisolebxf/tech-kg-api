from datetime import datetime

from service.expert_direct_relation import ExpertDirectRelationService


def test_time_filter_uses_relation_time_for_items_total_and_graph_source() -> None:
    rows = [
        {"relation_time": "2019-12-31", "relation_key": "old"},
        {"relation_time": "2021-06", "relation_key": "matched"},
        {"relation_time": datetime(2023, 1, 2), "relation_key": "new"},
        {"relation_time": None, "relation_key": "unknown"},
    ]

    result = ExpertDirectRelationService._filter_rows_by_time(
        rows, "2020-01", "2022-12"
    )

    assert [row["relation_key"] for row in result] == ["matched"]


def test_time_filter_keeps_all_rows_without_time_constraint() -> None:
    rows = [{"relation_time": None}, {"relation_time": "2021-06"}]

    assert ExpertDirectRelationService._filter_rows_by_time(rows, None, None) == rows
