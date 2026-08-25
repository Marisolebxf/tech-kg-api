# backend/tests/unit/test_expert_alumni_relation.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infra.graph_db import GraphConnectionError
from infra.graph_db.models import GraphPagedResult
from service.expert_alumni_relation import ExpertAlumniRelationService, clear_caches


@pytest.fixture(autouse=True)
def _isolate_caches():
    """每条用例前后清空进程内 TTL 缓存，避免用例间串味。"""
    clear_caches()
    yield
    clear_caches()


def _node(nid: str, props: dict | None = None):
    return SimpleNamespace(id=nid, properties=props or {}, labels=["Person"])


def _edge(etype: str, source: str, target: str):
    return SimpleNamespace(
        id=f"{source}->{target}@0",
        type=etype,
        source_id=source,
        target_id=target,
        properties={},
    )


def _svc(graph) -> ExpertAlumniRelationService:
    svc = ExpertAlumniRelationService()
    svc._client = MagicMock(return_value=graph)  # type: ignore[method-assign]
    return svc


def test_pair_same_school_and_degree():
    a = _node(
        "S1",
        {
            "name_zh": "甲",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "博士",
            "education_background_date": "2008-2013",
        },
    )
    b = _node(
        "S2",
        {
            "name_zh": "乙",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "博士",
            "education_background_date": "2010-2015",
        },
    )
    nodes = {"S1": a, "S2": b}
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(return_value=[_edge("COAUTHOR_WITH", "S1", "S2")])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(expert_id="S1", target_expert_id="S2")

    assert resp["mode"] == "pair"
    assert resp["total"] == 1
    item = resp["items"][0]
    assert item["alumniId"] == "S2"
    assert "同校" in item["dimensions"]
    assert "同学历" in item["dimensions"]
    assert "同期" in item["dimensions"]
    assert "同院系" not in item["dimensions"]
    assert "同导师" not in item["dimensions"]
    assert item["interactions"]["coauthorEdge"] is True
    assert resp["summaryRows"]
    assert resp["resultRows"][0]["label"] == "校友数量"
    assert resp["graph"]["nodes"]
    assert resp["graph"]["edges"]
    assert resp["entities"][0]["id"] == "S1"
    assert resp["relations"][0]["to"] == "S2"
    assert resp["provenance"]["evidences"]
    assert resp["rules"][0]["name"] == "教育经历匹配规则"
    assert "同校" in resp["dimensionsCatalog"]


def test_pair_not_alumni():
    a = _node("S1", {"name_zh": "甲", "education_background_institution_zh": "北京大学"})
    b = _node("S2", {"name_zh": "乙", "education_background_institution_zh": "清华大学"})
    nodes = {"S1": a, "S2": b}
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(expert_id="S1", target_expert_id="S2")
    assert resp["total"] == 0
    assert resp["items"] == []


def test_pair_education_stage_accepts_multiple_values():
    a = _node(
        "S1",
        {
            "name_zh": "甲",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "博士",
        },
    )
    b = _node(
        "S2",
        {
            "name_zh": "乙",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "硕士",
        },
    )
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: {"S1": a, "S2": b}.get(str(nid)))
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(
        expert_id="S1",
        target_expert_id="S2",
        education_stage="学士,硕士",
    )

    assert resp["total"] == 1


def test_list_finds_alumni_and_truncation_meta():
    source = _node(
        "S1",
        {"name_zh": "甲", "education_background_institution_zh": "复旦大学"},
    )
    alum = _node(
        "S2",
        {"name_zh": "乙", "education_background_institution_zh": "复旦大学"},
    )
    other = _node(
        "S3",
        {"name_zh": "丙", "education_background_institution_zh": "浙大"},
    )
    nodes = {"S1": source, "S2": alum, "S3": other}
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_nodes_by_label = MagicMock(
        return_value=GraphPagedResult(items=[alum, other], total=2, limit=50, offset=0)
    )
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(expert_id="S1", limit=10)

    assert resp["mode"] == "list"
    assert resp["total"] == 1
    assert resp["items"][0]["alumniId"] == "S2"
    assert "同校" in resp["dimensionsCatalog"]


def test_list_scans_beyond_original_500_candidate_limit():
    source = _node("S1", {"education_background_institution_zh": "测试大学"})
    first_page = [
        _node(f"P{i}", {"education_background_institution_zh": "其他大学"}) for i in range(500)
    ]
    pages = [
        GraphPagedResult(items=first_page, total=551, limit=500, offset=0),
        GraphPagedResult(
            items=[
                *[
                    _node(f"P{i}", {"education_background_institution_zh": "其他大学"})
                    for i in range(500, 550)
                ],
                _node("TARGET", {"education_background_institution_zh": "测试大学"}),
            ],
            total=551,
            limit=500,
            offset=500,
        ),
    ]
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=source)
    graph.get_nodes_by_label = MagicMock(side_effect=pages)
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")
    resp = _svc(graph).query(expert_id="S1", limit=20)
    assert resp["total"] == 1
    assert resp["items"][0]["alumniId"] == "TARGET"
    assert graph.get_nodes_by_label.call_count == 2
    assert resp["sourceMeta"]["truncated"] is False


def test_no_education_returns_zero():
    a = _node("S1", {"name_zh": "甲"})
    b = _node("S2", {"name_zh": "乙", "education_background_institution_zh": "北大"})
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: a if nid == "S1" else b)
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(expert_id="S1", target_expert_id="S2")
    assert resp["total"] == 0


def test_missing_expert_raises():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=None)
    with pytest.raises(KeyError, match="未找到专家"):
        _svc(graph).query(expert_id="NO")


def test_list_propagates_graph_connection_error():
    source = _node("S1", {"education_background_institution_zh": "测试大学"})
    graph = MagicMock()
    graph.get_node.return_value = source
    graph.get_nodes_by_label.side_effect = GraphConnectionError("not connected")
    graph._settings = SimpleNamespace(space="dev")

    with pytest.raises(GraphConnectionError, match="not connected"):
        _svc(graph).query(expert_id="S1")


def test_service_does_not_cache_replaced_process_client():
    first = MagicMock()
    second = MagicMock()
    service = ExpertAlumniRelationService()

    with patch(
        "service.expert_alumni_relation.get_trs_graph_client",
        side_effect=[first, second],
    ):
        assert service._client() is first  # noqa: SLF001
        assert service._client() is second  # noqa: SLF001


def test_same_id_raises():
    graph = MagicMock()
    with pytest.raises(ValueError, match="不能相同"):
        _svc(graph).query(expert_id="S1", target_expert_id="S1")
