# backend/tests/unit/test_expert_alumni_relation.py
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infra.graph_db import GraphConnectionError
from service.expert_alumni_relation import ExpertAlumniRelationService, clear_caches


@pytest.fixture(autouse=True)
def _isolate_caches():
    """每条用例前后清空进程内 TTL 缓存，避免用例间串味。"""
    clear_caches()
    yield
    clear_caches()


def _node(nid: str, props: dict | None = None, labels: list[str] | None = None):
    return SimpleNamespace(id=nid, properties=props or {}, labels=labels or ["Person"])


def _edge(etype: str, source: str, target: str, props: dict | None = None):
    return SimpleNamespace(
        id=f"{source}->{target}@0",
        type=etype,
        source_id=source,
        target_id=target,
        properties=props or {},
    )


def _svc(graph) -> ExpertAlumniRelationService:
    svc = ExpertAlumniRelationService()
    svc._client = MagicMock(return_value=graph)  # type: ignore[method-assign]
    return svc


def _graph_with_studied_at(
    source: Any,
    alumni: list[Any],
    *,
    org_vid: str = "org_pku",
    institution: str = "北京大学",
) -> MagicMock:
    """源专家 --STUDIED_AT--> org <--STUDIED_AT-- 校友。"""
    nodes = {
        str(source.id): source,
        org_vid: _node(org_vid, {"name_cn": institution}, ["Organization"]),
    }
    for a in alumni:
        nodes[str(a.id)] = a

    def edges(nid, **kwargs):
        et = kwargs.get("edge_type")
        direction = kwargs.get("direction", "both")
        nid = str(nid)
        if nid == str(source.id) and direction == "out" and et == "STUDIED_AT":
            return [
                _edge(
                    "STUDIED_AT",
                    str(source.id),
                    org_vid,
                    {"institution_zh": institution},
                )
            ]
        if nid == org_vid and direction == "in" and et == "STUDIED_AT":
            return [
                _edge("STUDIED_AT", str(source.id), org_vid, {"institution_zh": institution}),
                *[
                    _edge("STUDIED_AT", str(a.id), org_vid, {"institution_zh": institution})
                    for a in alumni
                ],
            ]
        if direction == "both" and et is None:
            return []
        return []

    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=edges)
    graph.get_nodes_by_label = MagicMock(
        side_effect=AssertionError("list 模式不得调用 get_nodes_by_label")
    )
    graph.execute_read = MagicMock(return_value=SimpleNamespace(records=[]))
    graph._settings = SimpleNamespace(space="dev")
    return graph


def test_pair_same_school_and_degree():
    a = _node(
        "S1",
        {
            "name_zh": "甲",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "博士",
            "education_background_date": "2008-2013",
            "source_table": "dwd_scholar_test",
            "source_field": "education_source_id",
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
    assert item["interactions"]["summary"] == "存在合著边"
    assert "0" not in item["interactions"]["summary"]
    assert "共同论文" not in {row["label"] for row in resp["summaryRows"]}
    assert "共同专利" not in {row["label"] for row in resp["summaryRows"]}
    assert "共同项目" not in {row["label"] for row in resp["summaryRows"]}
    assert not any(row["label"].startswith("成果 ") for row in resp["summaryRows"])
    assert resp["summaryRows"]
    assert resp["resultRows"][0]["label"] == "校友数量"
    assert resp["graph"]["nodes"]
    assert resp["graph"]["edges"]
    assert resp["entities"][0]["id"] == "S1"
    assert resp["relations"][0]["to"] == "S2"
    entities_by_id = {entity["id"]: entity for entity in resp["entities"]}
    assert (
        entities_by_id["S1"]["relations"]
        == "与乙存在校友关系（同校、同学历、同期；共同院校：北京大学）"
    )
    assert (
        entities_by_id["S2"]["relations"]
        == "与甲存在校友关系（同校、同学历、同期；共同院校：北京大学）"
    )
    assert entities_by_id["S1"]["evidence"] == ["教育经历 1 条"]
    assert entities_by_id["S2"]["evidence"][0] == "共同院校：北京大学"
    assert entities_by_id["S2"]["evidence"][1].startswith("互动证据：")
    assert all(
        not evidence.startswith("shared=")
        for entity in resp["entities"]
        for evidence in entity["evidence"]
    )
    assert resp["relations"][0]["label"] == "校友关系"
    assert resp["relations"][0]["category"] == "教育经历关联"
    assert resp["relations"][0]["dimensions"] == ["同校", "同学历", "同期"]
    assert resp["relations"][0]["sharedInstitutions"] == ["北京大学"]
    assert "关系维度：同校、同学历、同期" in resp["relations"][0]["summary"]
    assert resp["graph"]["edges"][0]["label"] == "校友关系"
    assert resp["graph"]["edges"][0]["category"] == "教育经历关联"
    assert resp["graph"]["edges"][0]["dimensions"] == ["同校", "同学历", "同期"]
    assert all(0 <= edge["confidence"] <= 1 for edge in resp["graph"]["edges"])
    assert resp["relations"][0]["confidenceSource"] == "derived"
    assert resp["relations"][0]["confidenceBasis"]["rule"] == "alumni-evidence-v1"
    assert {edge["label"] for edge in resp["graph"]["edges"]} >= {"校友关系"}
    assert resp["provenance"]["evidences"]
    source_evidence = resp["provenance"]["evidences"][0]
    assert source_evidence["technicalTable"] == "dwd_scholar_test"
    assert source_evidence["sourceField"] == "education_source_id"
    assert source_evidence["graphVid"] == "S1"
    alumni_evidence = resp["provenance"]["evidences"][1]
    assert alumni_evidence["technicalTable"] == "-"
    assert alumni_evidence["sourceField"] == "-"
    assert alumni_evidence["graphVid"] == "S2"
    assert resp["rules"][0]["name"] == "教育经历匹配算法"
    assert "同校" in resp["dimensionsCatalog"]


def test_graph_entities_use_alumni_and_shared_achievement_relation_semantics():
    expert = {"id": "S1", "name": "甲", "educations": []}
    items = [
        {
            "alumniId": "S2",
            "name": "乙",
            "dimensions": ["同校", "同期"],
            "sharedInstitutions": ["北京大学"],
            "interactions": {
                "summary": "共同论文 1 篇、专利 1、项目 1",
                "sharedAchievements": [
                    {"id": "P1", "label": "论文A", "kind": "paper", "entityType": "论文成果"},
                    {"id": "PT1", "label": "专利A", "kind": "patent", "entityType": "专利成果"},
                    {"id": "PR1", "label": "项目A", "kind": "project", "entityType": "项目成果"},
                ],
            },
        }
    ]

    entities, relations, graph = ExpertAlumniRelationService._build_graph_entities(
        expert, items, mode="pair", include_shared_achievements=True
    )

    entities_by_id = {entity["id"]: entity for entity in entities}
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    assert entities_by_id["S1"]["relations"] == "与乙存在校友关系（同校、同期；共同院校：北京大学）"
    assert entities_by_id["S2"]["relations"] == "与甲存在校友关系（同校、同期；共同院校：北京大学）"
    assert nodes_by_id["P1"]["relations"] == "由甲、乙共同发表"
    assert nodes_by_id["PT1"]["relations"] == "由甲、乙共同发明"
    assert nodes_by_id["PR1"]["relations"] == "由甲、乙共同参与"
    assert relations[0]["label"] == "校友关系"
    assert {edge["label"] for edge in graph["edges"]} == {
        "校友关系",
        "发表",
        "发明",
        "参与",
    }
    assert all(edge.get("confidence") is not None for edge in graph["edges"])


def test_pair_mode_pages_all_interaction_edges():
    edges = [_edge("AUTHORED_BY", f"P{index}", "S1") for index in range(501)]
    graph = MagicMock()

    def get_edges(_nid, **kwargs):
        if kwargs.get("edge_type") != "AUTHORED_BY":
            return []
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 500)
        return edges[offset : offset + limit]

    graph.get_node_edges = MagicMock(side_effect=get_edges)
    result = _svc(graph)._all_interaction_edges(graph, "S1")

    assert len(result) == 501
    assert graph.get_node_edges.call_count >= 2


def test_pair_summary_lists_each_shared_achievement_name_once():
    source = _node("S1", {"name_zh": "甲", "education_background_institution_zh": "北京大学"})
    target = _node("S2", {"name_zh": "乙", "education_background_institution_zh": "北京大学"})
    achievements = {
        "P1": _node("P1", {"title": "共同论文一"}, ["Paper"]),
        "P2": _node("P2", {"title": "共同论文二"}, ["Paper"]),
        "PT1": _node("PT1", {"title": "共同专利"}, ["Patent"]),
        "PR1": _node("PR1", {"title": "共同项目"}, ["Project"]),
    }
    nodes = {"S1": source, "S2": target, **achievements}
    edges = [
        _edge("AUTHORED_BY", paper_id, person_id)
        for paper_id in ("P1", "P2")
        for person_id in ("S1", "S2")
    ] + [
        _edge(edge_type, achievement_id, person_id)
        for edge_type, achievement_id in (("INVENTED_BY", "PT1"), ("HAS_PARTICIPANT", "PR1"))
        for person_id in ("S1", "S2")
    ]
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(
        side_effect=lambda nid, **kwargs: [
            edge
            for edge in edges
            if str(nid) in (edge.source_id, edge.target_id) and edge.type == kwargs.get("edge_type")
        ]
    )
    graph._settings = SimpleNamespace(space="dev")

    response = _svc(graph).query(expert_id="S1", target_expert_id="S2")

    assert response["mode"] == "pair"
    assert response["total"] == 1
    assert response["items"][0]["interactions"]["sharedAchievements"]
    assert [
        (row["label"], row["value"])
        for row in response["summaryRows"]
        if row["label"].startswith("成果 ")
    ] == [
        ("成果 1", "共同论文一"),
        ("成果 2", "共同论文二"),
        ("成果 3", "共同专利"),
        ("成果 4", "共同项目"),
    ]
    assert (
        next(row["value"] for row in response["summaryRows"] if row["label"] == "共同成果总数")
        == "4 项"
    )


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
    assert not any(row["label"].startswith("成果 ") for row in resp["summaryRows"])
    entities_by_id = {entity["id"]: entity for entity in resp["entities"]}
    assert entities_by_id["S1"]["relations"] == "与乙未形成校友关系（未命中共同院校）"
    assert entities_by_id["S2"]["relations"] == "与甲未形成校友关系（未命中共同院校）"
    assert resp["graph"]["edges"] == []


def test_pair_education_stage_accepts_multiple_values():
    a = _node(
        "S1",
        {
            "name_zh": "甲",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "硕士",
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


def test_pair_education_stage_requires_both_experts_to_match():
    source = _node(
        "S1",
        {
            "name_zh": "甲",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "硕士",
        },
    )
    target = _node(
        "S2",
        {
            "name_zh": "乙",
            "education_background_institution_zh": "北京大学",
            "education_background_degree_zh": "博士",
        },
    )
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: {"S1": source, "S2": target}.get(str(nid)))
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    response = _svc(graph).query(expert_id="S1", target_expert_id="S2", education_stage="博士")

    assert response["total"] == 0
    assert response["relations"] == []
    assert response["graph"]["edges"] == []


def test_parse_educations_preserves_multiple_stages_at_same_school():
    service = ExpertAlumniRelationService()
    educations = service._parse_educations(
        {
            "education_background": [
                {"institution": "清华大学", "degree": "硕士", "date": "2012-2015"},
                {"institution": "清华大学", "degree": "博士", "date": "2015-2019"},
                {"institution": "清华大学", "degree": "博士", "date": "2015-2019"},
            ]
        }
    )

    text_educations = service._parse_educations(
        {"education_background_zh": "清华大学（硕士，2012-2015）；清华大学（博士，2015-2019）"}
    )
    assert text_educations == [
        {"institution": "清华大学", "degree": "硕士", "date": "2012-2015"},
        {"institution": "清华大学", "degree": "博士", "date": "2015-2019"},
    ]

    assert educations == [
        {"institution": "清华大学", "degree": "硕士", "date": "2012-2015"},
        {"institution": "清华大学", "degree": "博士", "date": "2015-2019"},
    ]


def test_list_via_studied_at_neighborhood():
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
    graph = _graph_with_studied_at(
        source, [alum, other], org_vid="org_fudan", institution="复旦大学"
    )

    resp = _svc(graph).query(expert_id="S1", limit=10)

    assert resp["mode"] == "list"
    assert not any(row["label"].startswith("成果 ") for row in resp["summaryRows"])
    assert resp["total"] == 1
    assert resp["items"][0]["alumniId"] == "S2"
    assert "同校" in resp["dimensionsCatalog"]
    entities_by_id = {entity["id"]: entity for entity in resp["entities"]}
    assert entities_by_id["S1"]["relations"] == "与乙存在校友关系"
    assert entities_by_id["S2"]["relations"] == "与甲存在校友关系（同校；共同院校：复旦大学）"
    graph.get_nodes_by_label.assert_not_called()


def test_list_does_not_call_get_nodes_by_label():
    source = _node("S1", {"education_background_institution_zh": "测试大学"})
    target = _node("TARGET", {"education_background_institution_zh": "测试大学"})
    graph = _graph_with_studied_at(source, [target], org_vid="org_test", institution="测试大学")
    _svc(graph).query(expert_id="S1", limit=20)
    assert graph.get_nodes_by_label.call_count == 0


def test_no_education_returns_zero():
    a = _node("S1", {"name_zh": "甲"})
    b = _node("S2", {"name_zh": "乙", "education_background_institution_zh": "北大"})
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: a if nid == "S1" else b)
    graph.get_node_edges = MagicMock(return_value=[])
    graph.execute_read = MagicMock(return_value=SimpleNamespace(records=[]))
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
    graph.get_node_edges.side_effect = GraphConnectionError("not connected")
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
