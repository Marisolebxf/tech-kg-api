from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from service.expert_direct_relation import (
    ExpertDirectRelationService,
    _matchable_names,
    clear_caches,
)


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
    client.get_node.return_value = {"properties": {}}  # 姓名素材为空即可
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
    client.get_node.return_value = {"properties": {}}
    rows = [{"expert_a_id": "person_a1", "expert_b_id": "person_b2", "relation_key": "a:b"}]
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    assert rows[0]["representative_achievements"] == []


class _FakeResult:
    def __init__(self, rows_):
        self._rows = rows_

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _RecordingSession:
    """按 SQL/参数标记分发结果，并记录每次执行的语句（供断言各层回退是否触发）。"""

    def __init__(self, level1_rows, level2_rows, level2_params=None, pool_rows=None):
        self.level1_rows = level1_rows
        self.level2_rows = level2_rows
        self.level2_params = level2_params or {}
        self.pool_rows = pool_rows or []
        self.pool_params: dict | None = None
        self.executed: list[str] = []

    def execute(self, sql, params):
        sql_text = str(sql)
        self.executed.append(sql_text)
        if "n0" in params:  # 锚点论文池（:n0/:n1 + :pool_limit）
            self.pool_params = params
            return _FakeResult(self.pool_rows)
        if "authors LIKE" in sql_text:  # 单对双方姓名联查
            assert params == self.level2_params
            return _FakeResult(self.level2_rows)
        assert set(params) == {"a", "b"}  # 关系表自连接
        return _FakeResult(self.level1_rows)


@pytest.mark.asyncio
async def test_representative_achievements_fall_back_to_author_names(monkeypatch):
    """关系表自连接无标题且为单对查询时，按双方姓名反查 authors 取真实标题。"""
    client = AsyncMock()
    client.get_node_edges.return_value = []
    client.get_node.side_effect = [
        {"properties": {"name_zh": "沈定刚", "name_en": "Dinggang Shen"}},
        {"properties": {"name_zh": "杨健", "name_en": "Jian Yang"}},
    ]
    rows = [{"expert_a_id": "person_a1", "expert_b_id": "person_b2", "relation_key": "a:b"}]

    session = _RecordingSession(
        level1_rows=[],
        level2_rows=[
            {"doi": "10.1/x", "title": "Deep feature descriptor"},
            {"doi": None, "title": None},  # 查不到标题的行必须被丢弃
        ],
        level2_params={
            "a0": "%沈定刚%",
            "a1": "%Dinggang Shen%",
            "b0": "%杨健%",
            "b1": "%Jian Yang%",
        },
    )

    class FakeSessionScope:
        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("service.expert_direct_relation.session_scope", lambda: FakeSessionScope())
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    item = service._build_item(rows[0])
    assert item["representativeAchievements"] == [
        {"id": "10.1/x", "title": "Deep feature descriptor"}
    ]
    assert any("authors LIKE" in sql for sql in session.executed)


@pytest.mark.asyncio
async def test_representative_achievements_name_guard_skips_author_scan(monkeypatch):
    """节点缺姓名素材时只走关系表自连接，不触发 authors 全表扫描。"""
    client = AsyncMock()
    client.get_node_edges.return_value = []
    client.get_node.return_value = {"properties": {}}
    rows = [{"expert_a_id": "person_a1", "expert_b_id": "person_b2", "relation_key": "a:b"}]

    session = _RecordingSession(level1_rows=[], level2_rows=[])

    class FakeSessionScope:
        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("service.expert_direct_relation.session_scope", lambda: FakeSessionScope())
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows)
    assert rows[0]["representative_achievements"] == []
    assert len(session.executed) == 1  # 只有自连接，没有姓名反查


def test_shared_paper_titles_from_mysql_skips_name_match_in_listing_mode(monkeypatch):
    """列表模式（allow_name_match=False）即使有姓名素材也不做姓名反查。"""
    session = _RecordingSession(level1_rows=[], level2_rows=[])

    class FakeSessionScope:
        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("service.expert_direct_relation.session_scope", lambda: FakeSessionScope())
    result = ExpertDirectRelationService._shared_paper_titles_from_mysql(
        "person_a1",
        "person_b2",
        ("沈定刚", "Dinggang Shen"),
        ("杨健", "Jian Yang"),
        allow_name_match=False,
    )
    assert result == []
    assert len(session.executed) == 1


def test_matchable_names_filters_unusable_forms():
    """过短、空、VID 兜底串都不可作为姓名匹配素材。"""
    assert _matchable_names(("杨", "person_a1", "沈定刚", "")) == ["沈定刚"]


@pytest.mark.asyncio
async def test_representative_achievements_listing_uses_anchor_pool(monkeypatch):
    """列表模式（仅A）用锚点论文池：一次扫描建池，内存按对端姓名逐行过滤。"""
    clear_caches()
    client = AsyncMock()
    client.get_node_edges.return_value = []
    # 对端节点姓名（每行一个对端；锚点姓名直接来自 anchor_node，不查图）
    client.get_node.side_effect = [
        {"properties": {"name_zh": "王翊", "name_en": "Wang Yi"}},
        {"properties": {"name_zh": "雷凯", "name_en": "Lei Kai"}},
    ]
    anchor_node = {
        "id": "person_anchor1",
        "properties": {"name_zh": "王祎", "name_en": "Yi Wang"},
    }
    rows: list[dict[str, object]] = [
        {"expert_a_id": "person_anchor1", "expert_b_id": "person_p1", "relation_key": "k1"},
        {"expert_a_id": "person_anchor1", "expert_b_id": "person_p2", "relation_key": "k2"},
    ]

    session = _RecordingSession(
        level1_rows=[],
        level2_rows=[],
        pool_rows=[
            {"doi": "10.9/1", "title": "共同论文一", "authors": "王祎, 王翊, 其他作者"},
            {"doi": "10.9/2", "title": "Joint Paper Two", "authors": "Yi Wang; Wang Yi; C. X"},
            {"doi": "10.9/3", "title": "锚点独著", "authors": "王祎"},
            {"doi": "10.9/4", "title": "与雷凯合著", "authors": "王祎, 雷凯"},
        ],
    )

    class FakeSessionScope:
        def __enter__(self):
            return session

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("service.expert_direct_relation.session_scope", lambda: FakeSessionScope())
    service = ExpertDirectRelationService()
    await service._attach_representative_achievements(client, rows, anchor_node=anchor_node)
    clear_caches()
    assert [a["title"] for a in rows[0]["representative_achievements"]] == [
        "共同论文一",
        "Joint Paper Two",
    ]
    assert [a["title"] for a in rows[1]["representative_achievements"]] == ["与雷凯合著"]
    # 池只建一次（懒加载），参数带锚点双姓名形态；总共 2 次自连接 + 1 次建池
    assert session.pool_params == {"n0": "%王祎%", "n1": "%Yi Wang%", "pool_limit": 2000}
    assert len(session.executed) == 3


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
