from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from service.expert_direct_relation import ExpertDirectRelationService


def test_time_filter_uses_relation_time_for_items_total_and_graph_source() -> None:
    rows = [
        {"relation_time": "2019-12-31", "relation_key": "old"},
        {"relation_time": "2021-06", "relation_key": "matched"},
        {"relation_time": datetime(2023, 1, 2), "relation_key": "new"},
        {"relation_time": None, "relation_key": "unknown"},
    ]

    result = ExpertDirectRelationService._filter_rows_by_time(rows, "2020-01", "2022-12")

    assert [row["relation_key"] for row in result] == ["matched"]


def test_time_filter_keeps_all_rows_without_time_constraint() -> None:
    rows = [{"relation_time": None}, {"relation_time": "2021-06"}]

    assert ExpertDirectRelationService._filter_rows_by_time(rows, None, None) == rows


@pytest.mark.parametrize(
    "value", [datetime(2026, 5, 27, 16, 39, 38), "2026-05-27 16:39:38", "2026-05-27T16:39:38+08:00"]
)
def test_display_date_has_no_time(value):
    item = ExpertDirectRelationService()._build_item({"relation_time": value})
    assert item["lastUpdatedAt"] == "2026-05-27"
    assert item["representativeAchievements"] == []


@pytest.mark.asyncio
async def test_representative_achievements_use_shared_paper_titles():
    client = AsyncMock()
    client.get_node_edges.side_effect = [
        [{"source": "paper_1", "target": "a"}, {"source": "paper_2", "target": "a"}],
        [{"source": "paper_2", "target": "b"}, {"source": "paper_3", "target": "b"}],
    ]
    client.get_node.return_value = {"properties": {"title": "A verified joint paper"}}
    rows = [{"expert_a_id": "a", "expert_b_id": "b", "relation_key": "a:b"}]
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    item = service._build_item(rows[0])
    assert item["representativeAchievements"] == [
        {"id": "paper_2", "title": "A verified joint paper"}
    ]
    client.get_node.assert_awaited_once_with("paper_2")


@pytest.mark.asyncio
async def test_representative_achievements_fall_back_to_mysql_when_graph_empty(monkeypatch):
    """图上无 AUTHORED_BY 共同论文时回退 MySQL 自连接；仅保留可核实标题。"""
    client = AsyncMock()
    client.get_node_edges.return_value = []
    rows = [{"expert_a_id": "person_a1", "expert_b_id": "person_b2", "relation_key": "a:b"}]

    class FakeResult:
        def __init__(self, rows_):
            self._rows = rows_

        def mappings(self):
            return self

        def all(self):
            return self._rows

    class FakeSession:
        def execute(self, _sql, params):
            assert params == {"a": "a1", "b": "b2"}
            return FakeResult(
                [
                    {"paper_id": 11, "title": "可信图计算"},
                    {"paper_id": 12, "title": None},  # 查不到标题的行必须被丢弃
                ]
            )

    class FakeSessionScope:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("service.expert_direct_relation.session_scope", lambda: FakeSessionScope())
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    item = service._build_item(rows[0])
    assert item["representativeAchievements"] == [{"id": "paper_11", "title": "可信图计算"}]


@pytest.mark.asyncio
async def test_representative_achievements_mysql_failure_degrades_to_empty(monkeypatch):
    """MySQL 回退异常时吞掉告警并回到空列表，不影响主结果。"""

    def _boom():
        raise RuntimeError("mysql unavailable")

    monkeypatch.setattr("service.expert_direct_relation.session_scope", _boom)
    client = AsyncMock()
    client.get_node_edges.return_value = []
    rows = [{"expert_a_id": "person_a1", "expert_b_id": "person_b2", "relation_key": "a:b"}]
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    assert rows[0]["representative_achievements"] == []


def test_build_graph_institution_edges_carry_confidence():
    """机构从属边是 organization 属性直读派生，应带边类型兜底置信度，
    前端按 data.strength/100 换算后不再显示"暂无"。"""
    row = {
        "expert_a_id": "a",
        "expert_b_id": "b",
        "expert_a_name": "甲",
        "expert_b_name": "乙",
        "expert_a_org": "大连理工大学",
        "expert_b_org": "北京大学",
        "evidence_kind": "paper",
        "evidence_count": 3,
        "relation_key": "a:b",
    }
    service = ExpertDirectRelationService()
    graph = service._build_graph([service._build_item(row)])

    institution_edges = [e for e in graph["edges"] if e["label"] == "关联机构"]
    assert len(institution_edges) == 2
    for edge in institution_edges:
        assert edge["data"]["strength"] == 75  # edge_confidence 边类型兜底 0.75
    relation_edge = next(e for e in graph["edges"] if e["label"] != "关联机构")
    assert relation_edge["data"]["strength"] > 0
