# backend/tests/unit/test_expert_enterprise_service.py
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


def _node(props):
    return MagicMock(properties=props)


def _edge(eid, target, rt):
    return MagicMock(id=eid, target_id=target, properties={"relation_type": rt})


def _svc(graph):
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    return svc


def test_build_creates_edge_with_english_codes_and_returns_chinese_label():
    scholar = _node({"name_zh": "张三"})
    enterprise = _node({"name_cn": "某企业"})
    org1 = _node({"org_id": "ENT001", "name_cn": "华智科技"})
    org2 = _node({"org_id": "ENT002", "name_cn": "启航智造"})
    nodes = {"S001": scholar, "E001": enterprise, "ENT001": org1, "ENT002": org2}
    edge1 = _edge("S001->ENT001@0", "ENT001", "employment")
    edge2 = _edge("S001->ENT002@0", "ENT002", "tech_cooperation")

    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.get_node_edges = MagicMock(return_value=[edge1, edge2])
    graph.create_edge = MagicMock()
    graph.delete_edge = MagicMock()

    resp = _svc(graph).build(
        {"scholarId": "S001", "enterpriseId": "E001", "relationTypes": ["employment"]}
    )

    assert resp["status"] == "success"
    assert resp["scholarName"] == "张三"
    assert resp["builtRelationId"] == "S001->E001@0"
    assert resp["relationType"] == "任职"
    assert resp["effective"] is True
    graph.create_edge.assert_called_once()
    args = graph.create_edge.call_args.args
    assert args[0] == "S001" and args[1] == "E001" and args[2] == "EMPLOYED_BY"
    assert args[3]["relation_type"] == "employment"
    assert len(resp["relations"]) == 2
    assert resp["relations"][0]["enterpriseName"] == "华智科技"
    assert resp["relations"][0]["relationType"] == "任职"
    assert resp["relations"][1]["relationType"] == "技术合作"


def test_build_merges_existing_codes_with_slash():
    scholar = _node({"name_zh": "张三"})
    enterprise = _node({"name_cn": "某企业"})
    edge = _edge("S001->E001@0", "E001", "employment")
    nodes = {"S001": scholar, "E001": enterprise}

    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.get_node_edges = MagicMock(return_value=[edge])
    graph.create_edge = MagicMock()
    graph.delete_edge = MagicMock()

    resp = _svc(graph).build(
        {"scholarId": "S001", "enterpriseId": "E001", "relationTypes": ["advisor"]}
    )
    assert resp["relationType"] == "任职/顾问"
    props = graph.create_edge.call_args.args[3]
    assert props["relation_type"] == "employment/advisor"


def test_build_does_not_duplicate_codes():
    scholar = _node({"name_zh": "张三"})
    enterprise = _node({"name_cn": "某企业"})
    edge = _edge("S001->E001@0", "E001", "employment/advisor")
    nodes = {"S001": scholar, "E001": enterprise}
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.get_node_edges = MagicMock(return_value=[edge])
    graph.create_edge = MagicMock()
    graph.delete_edge = MagicMock()
    _svc(graph).build(
        {"scholarId": "S001", "enterpriseId": "E001", "relationTypes": ["employment"]}
    )
    assert graph.create_edge.call_args.args[3]["relation_type"] == "employment/advisor"


def test_build_deletes_extra_rank_edges():
    scholar = _node({"name_zh": "张三"})
    enterprise = _node({"name_cn": "某企业"})
    e0 = _edge("S001->E001@0", "E001", "employment")
    e2 = _edge("S001->E001@2", "E001", "rd_cooperation")
    nodes = {"S001": scholar, "E001": enterprise}
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.get_node_edges = MagicMock(return_value=[e0, e2])
    graph.create_edge = MagicMock()
    graph.delete_edge = MagicMock()
    _svc(graph).build(
        {"scholarId": "S001", "enterpriseId": "E001", "relationTypes": ["employment"]}
    )
    deleted_ids = [c.args[0] for c in graph.delete_edge.call_args_list]
    assert "S001->E001@2" in deleted_ids
    assert "S001->E001@0" not in deleted_ids


def test_build_scholar_missing_raises():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=None)
    graph.create_edge = MagicMock()
    with pytest.raises(KeyError):
        _svc(graph).build(
            {"scholarId": "NO", "enterpriseId": "E001", "relationTypes": ["employment"]}
        )
    graph.create_edge.assert_not_called()


def test_build_enterprise_missing_raises():
    scholar = _node({"name_zh": "张三"})
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: scholar if nid == "S001" else None)
    graph.create_edge = MagicMock()
    with pytest.raises(KeyError):
        _svc(graph).build(
            {"scholarId": "S001", "enterpriseId": "NO", "relationTypes": ["employment"]}
        )
    graph.create_edge.assert_not_called()


def test_build_dedupes_relations_by_enterprise():
    scholar = _node({"name_zh": "张三"})
    org1 = _node({"org_id": "ENT001", "name_cn": "华智科技"})
    edge_a = _edge("S001->ENT001@0", "ENT001", "employment")
    edge_b = _edge("S001->ENT001@2", "ENT001", "rd_cooperation")
    nodes = {"S001": scholar, "ENT001": org1, "E001": _node({"name_cn": "某企业"})}
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.get_node_edges = MagicMock(return_value=[edge_a, edge_b])
    graph.create_edge = MagicMock()
    graph.delete_edge = MagicMock()
    resp = _svc(graph).build(
        {"scholarId": "S001", "enterpriseId": "E001", "relationTypes": ["employment"]}
    )
    assert len(resp["relations"]) == 1
    assert resp["relations"][0]["enterpriseId"] == "ENT001"
    assert resp["relations"][0]["relationType"] == "任职/研发合作"
