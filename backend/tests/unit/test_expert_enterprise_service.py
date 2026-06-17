from __future__ import annotations

from unittest.mock import MagicMock

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


def _node(props):
    return MagicMock(properties=props)


def test_build_constructs_and_returns_all_relations():
    scholar = _node({"name_zh": "张三"})
    enterprise = _node({"name_cn": "某企业"})
    org1 = _node({"org_id": "ENT001", "name_cn": "华智科技"})
    org2 = _node({"org_id": "ENT002", "name_cn": "启航智造"})
    edge1 = MagicMock(id="S001->ENT001@0", target_id="ENT001", properties={"relation_type": "任职"})
    edge2 = MagicMock(id="S001->ENT002@1", target_id="ENT002", properties={"relation_type": "合作"})
    nodes = {"S001": scholar, "E001": enterprise, "ENT001": org1, "ENT002": org2}

    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.execute_write = MagicMock()
    graph.get_node_edges = MagicMock(return_value=[edge1, edge2])

    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build({"scholarId": "S001", "enterpriseId": "E001", "relationType": "任职"})

    assert resp["status"] == "success"
    assert resp["scholarId"] == "S001"
    assert resp["scholarName"] == "张三"
    assert resp["builtRelationId"] == "S001->E001@0"  # 任职 → rank 0
    assert resp["relationType"] == "任职"
    assert resp["effective"] is True
    # 返回该专家全部企业关系
    assert len(resp["relations"]) == 2
    assert resp["relations"][0] == {
        "relationId": "S001->ENT001@0",
        "enterpriseId": "ENT001",
        "enterpriseName": "华智科技",
        "relationType": "任职",
    }
    assert resp["relations"][1]["enterpriseName"] == "启航智造"
    assert resp["relations"][1]["relationType"] == "合作"
    graph.execute_write.assert_called_once()
    assert "INSERT EDGE EMPLOYED_BY" in graph.execute_write.call_args.args[0]
    assert "任职" in graph.execute_write.call_args.args[0]


def test_build_scholar_missing():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=None)
    graph.execute_write = MagicMock()
    graph.get_node_edges = MagicMock(return_value=[])
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build({"scholarId": "NO", "enterpriseId": "E001", "relationType": "任职"})
    assert resp["scholarName"] is None
    assert resp["effective"] is False
    assert resp["builtRelationId"] is None
    assert resp["relations"] == []
    graph.execute_write.assert_not_called()
    graph.get_node_edges.assert_not_called()


def test_build_enterprise_missing_returns_existing_relations():
    scholar = _node({"name_zh": "张三"})
    org1 = _node({"org_id": "ENT001", "name_cn": "华智科技"})
    edge1 = MagicMock(id="S001->ENT001@0", target_id="ENT001", properties={"relation_type": "任职"})
    nodes = {"S001": scholar, "ENT001": org1}  # E001 不存在

    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(nid))
    graph.execute_write = MagicMock()
    graph.get_node_edges = MagicMock(return_value=[edge1])

    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build({"scholarId": "S001", "enterpriseId": "E001", "relationType": "合作"})
    # 企业不存在 → 不构建
    assert resp["effective"] is False
    assert resp["builtRelationId"] is None
    graph.execute_write.assert_not_called()
    # 但仍返回该专家现有关系
    assert len(resp["relations"]) == 1
    assert resp["relations"][0]["enterpriseName"] == "华智科技"
