# backend/tests/unit/test_expert_cooperation_achievement.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from service.expert_cooperation_achievement import ExpertCooperationAchievementService


def _node(nid: str, props: dict | None = None, labels: list[str] | None = None):
    return SimpleNamespace(id=nid, properties=props or {}, labels=labels or ["Person"])


def _edge(etype: str, source: str, target: str):
    return SimpleNamespace(
        id=f"{source}->{target}@0",
        type=etype,
        source_id=source,
        target_id=target,
        properties={},
    )


def _svc(graph) -> ExpertCooperationAchievementService:
    svc = ExpertCooperationAchievementService()
    svc._graph = graph  # noqa: SLF001
    return svc


def test_query_shared_papers_and_patent_with_awards():
    p1 = _node("P1", {"title": "论文A", "year": "2020", "keywords": "图谱,AI", "award": "优秀论文"})
    p2 = _node("P2", {"title": "论文B", "year": "2021"})
    pt1 = _node(
        "PT1",
        {
            "title": "专利X",
            "year": "2022",
            "awards": [{"name": "中国专利奖", "level": "国家级", "year": 2022}],
        },
    )
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": p1,
        "P2": p2,
        "PT1": pt1,
    }
    edges = {
        "S1": [
            _edge("AUTHORED_BY", "P1", "S1"),
            _edge("AUTHORED_BY", "P2", "S1"),
            _edge("INVENTED_BY", "PT1", "S1"),
        ],
        "S2": [
            _edge("AUTHORED_BY", "P1", "S2"),
            _edge("INVENTED_BY", "PT1", "S2"),
        ],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")

    assert resp["summary"]["papers"] == 1
    assert resp["summary"]["patents"] == 1
    assert resp["summary"]["projects"] == 0
    assert resp["summary"]["awards"] >= 1
    types = {i["type"] for i in resp["items"]}
    assert types == {"paper", "patent"}
    paper = next(i for i in resp["items"] if i["type"] == "paper")
    assert paper["title"] == "论文A"
    assert "图谱" in paper["fields"]
    assert resp["coreContribution"]  # has patent + paper
    assert "共同专利产出" in resp["coreContribution"]
    assert resp["cooperationMode"] in {
        "多类型合作",
        "长期稳定型科研合作",
        "单类型合作（论文）",
        "单类型合作（专利）",
        "单类型合作（项目）",
    }


def test_query_same_id_raises():
    graph = MagicMock()
    with pytest.raises(ValueError, match="不能相同"):
        _svc(graph).query(source_expert_id="S1", target_expert_id="S1")


def test_query_missing_expert_raises():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=None)
    with pytest.raises(KeyError, match="不存在"):
        _svc(graph).query(source_expert_id="NO", target_expert_id="S2")


def test_query_empty_shared_achievements():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")

    assert resp["summary"] == {"papers": 0, "patents": 0, "projects": 0, "awards": 0}
    assert resp["items"] == []
    assert resp["coreContribution"] == "暂无结构化共同成果"
    assert resp["cooperationMode"] == "暂无合作模式"


def test_cooperation_mode_long_term():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "a", "year": "2018"}),
        "P2": _node("P2", {"title": "b", "year": "2020"}),
        "P3": _node("P3", {"title": "c", "year": "2022"}),
    }
    edges = {
        "S1": [
            _edge("AUTHORED_BY", "P1", "S1"),
            _edge("AUTHORED_BY", "P2", "S1"),
            _edge("AUTHORED_BY", "P3", "S1"),
        ],
        "S2": [
            _edge("AUTHORED_BY", "P1", "S2"),
            _edge("AUTHORED_BY", "P2", "S2"),
            _edge("AUTHORED_BY", "P3", "S2"),
        ],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["cooperationMode"] == "长期稳定型科研合作"
    assert resp["coreContribution"] == "共同论文产出"


def test_does_not_treat_project_level_as_award():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "PR1": _node("PR1", {"title": "项目", "year": "2021", "project_level": "国家级"}),
    }
    edges = {
        "S1": [_edge("HAS_PARTICIPANT", "PR1", "S1")],
        "S2": [_edge("LEADS", "PR1", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["summary"]["projects"] == 1
    assert resp["summary"]["awards"] == 0
    assert resp["items"][0]["awards"] == []
