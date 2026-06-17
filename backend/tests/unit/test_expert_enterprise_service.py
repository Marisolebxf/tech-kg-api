from __future__ import annotations

from unittest.mock import MagicMock

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


def _graph_with_nodes():
    graph = MagicMock()
    # 两端节点都存在，带名称属性
    scholar = MagicMock(properties={"name_zh": "张三"})
    enterprise = MagicMock(properties={"name_cn": "某企业"})
    graph.get_node = MagicMock(side_effect=lambda nid: scholar if nid == "S001" else enterprise)
    graph.execute_write = MagicMock()
    return graph


def test_build_writes_edge_per_relation_type():
    graph = _graph_with_nodes()
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build(
        {
            "scholarId": "S001",
            "enterpriseId": "E001",
            "relationTypes": ["employment", "advisor", "rd_cooperation"],
        }
    )
    assert resp["status"] == "success"
    assert resp["scholarId"] == "S001"
    assert resp["enterpriseId"] == "E001"
    assert resp["scholarName"] == "张三"
    assert resp["enterpriseName"] == "某企业"
    assert len(resp["relations"]) == 3
    assert [r["relationType"] for r in resp["relations"]] == [
        "employment",
        "advisor",
        "rd_cooperation",
    ]
    assert [r["relationId"] for r in resp["relations"]] == [
        "S001->E001@0",
        "S001->E001@1",
        "S001->E001@2",
    ]
    assert all(r["effective"] for r in resp["relations"])
    # 每个类型写一条边
    assert graph.execute_write.call_count == 3
    stmts = " ".join(str(c.args[0]) for c in graph.execute_write.call_args_list)
    assert "employment" in stmts and "advisor" in stmts and "rd_cooperation" in stmts
    assert "INSERT EDGE EMPLOYED_BY" in stmts


def test_build_missing_node_returns_ineffective():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=None)  # 节点不存在
    graph.execute_write = MagicMock()
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build(
        {
            "scholarId": "S001",
            "enterpriseId": "E001",
            "relationTypes": ["employment"],
        }
    )
    assert resp["relations"] == [
        {"relationId": "S001->E001@0", "relationType": "employment", "effective": False},
    ]
    graph.execute_write.assert_not_called()


def test_build_write_failure_marks_ineffective():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=MagicMock())
    graph.execute_write = MagicMock(side_effect=RuntimeError("boom"))
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build(
        {
            "scholarId": "S001",
            "enterpriseId": "E001",
            "relationTypes": ["employment", "advisor"],
        }
    )
    assert len(resp["relations"]) == 2
    assert all(r["effective"] is False for r in resp["relations"])
