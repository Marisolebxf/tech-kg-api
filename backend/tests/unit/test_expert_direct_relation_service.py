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
async def test_representative_achievements_graph_only_no_mysql_fallback():
    """仅查图数据库：图上无 AUTHORED_BY 共同论文时代表成果为空，模块不绑定 MySQL 会话。"""
    from service import expert_direct_relation

    assert not hasattr(expert_direct_relation, "session_scope")
    client = AsyncMock()
    client.get_node_edges.return_value = []
    client.get_node.return_value = {"properties": {}}
    rows = [{"expert_a_id": "person_a1", "expert_b_id": "person_b2", "relation_key": "a:b"}]
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    assert rows[0]["representative_achievements"] == []
    client.get_node.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_query_reports_graph_api_error_on_timeout(monkeypatch) -> None:
    """graph_api 总预算耗尽（TimeoutError）须如实报 graph_api_error，不落 unexpected_error。"""

    class _TimeoutCtx:
        async def __aenter__(self):
            raise TimeoutError("budget exhausted")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("service.expert_direct_relation.graph_api", lambda **kw: _TimeoutCtx())

    result = await ExpertDirectRelationService().query(expert_a_id="专家甲")

    assert result["source"]["reason"] == "graph_api_error"


async def test_peer_fetch_semaphore_is_shared_across_requests(monkeypatch):
    """对端详情并发上限按事件循环共享：并发请求叠加后峰值仍 ≤ 上限。

    旧实现在每个请求里各建 Semaphore(5)，N 个并发冷请求会叠加 5N 个在飞
    get_node；修复后两个并发请求一起受同一上限约束。
    """
    import asyncio

    from service import expert_direct_relation

    monkeypatch.setattr(expert_direct_relation, "_PEER_FETCH_CONCURRENCY", 2)
    service = ExpertDirectRelationService()
    monkeypatch.setattr(
        ExpertDirectRelationService,
        "_build_row",
        lambda self, node_a, node_b, edge: {"peer": node_b["id"]},
    )

    class _PeerFakeClient:
        def __init__(self):
            self.in_flight = 0
            self.peak = 0

        async def get_node_edges(self, node_id, *, edge_type, limit):
            return [
                {
                    "source": "person_A",
                    "target": f"person_P{i}",
                    "properties": {"co_paper_count": i},
                }
                for i in range(6)
            ]

        async def get_node(self, peer_id):
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            await asyncio.sleep(0.01)
            self.in_flight -= 1
            return {"id": peer_id, "properties": {"name_zh": peer_id}}

    shared = _PeerFakeClient()
    node_a = {"id": "person_A", "labels": ["Person"], "properties": {}}
    await asyncio.gather(
        service._collect_relations(shared, node_a, limit=6),
        service._collect_relations(shared, node_a, limit=6),
    )

    assert shared.peak == 2  # 进程级上限对两个并发请求一起生效（旧实现会到 4）
