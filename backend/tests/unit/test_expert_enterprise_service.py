from __future__ import annotations

from unittest.mock import MagicMock

from service.expert_enterprise_relation import ExpertEnterpriseRelationService


def _graph_with_expert_and_org():
    graph = MagicMock()
    scholar_node = MagicMock(
        id="S1",
        labels=["Scholar"],
        properties={"scholar_id": "S1", "name_zh": "张伟", "scholar_org_name_zh": "清华大学"},
    )
    org_node = MagicMock(
        id="O1",
        labels=["Organization"],
        properties={
            "org_id": "O1",
            "name_cn": "清华大学",
            "province": "北京市",
            "org_type": "高校",
        },
    )
    edge = MagicMock(
        id="S1->O1@0",
        type="EMPLOYED_BY",
        source_id="S1",
        target_id="O1",
        properties={"relation_type": "任职", "role": "", "start_date": "", "end_date": ""},
    )
    graph.find_nodes = MagicMock(
        side_effect=lambda labels, props, **k: (
            MagicMock(items=[scholar_node]) if "Scholar" in labels else MagicMock(items=[org_node])
        )
    )
    graph.get_node_edges = MagicMock(return_value=[edge])
    graph.get_node = MagicMock(return_value=org_node)
    return graph


def test_build_returns_expert_and_enterprises():
    svc = ExpertEnterpriseRelationService()
    svc._graph = _graph_with_expert_and_org()  # noqa: SLF001
    resp = svc.build(
        {"expertAId": "S1", "relationType": "all", "dataSource": "all", "timeRange": None}
    )
    assert resp["status"] == "success"
    assert resp["expert"] == "张伟"
    assert resp["expert_id"] == "S1"
    assert resp["enterprises"][0]["name"] == "清华大学"
    assert resp["enterprises"][0]["relation"] == "任职"


def test_build_expert_not_found():
    graph = MagicMock()
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[]))
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build(
        {"expertAId": "ZZZ", "relationType": "all", "dataSource": "all", "timeRange": None}
    )
    assert resp["status"] == "success"
    assert resp["expert"] is None
    assert resp["enterprises"] == []


def test_build_filters_by_relation_type():
    graph = MagicMock()
    scholar_node = MagicMock(
        id="S1", labels=["Scholar"], properties={"scholar_id": "S1", "name_zh": "张伟"}
    )
    org_node = MagicMock(
        id="O1", labels=["Organization"], properties={"org_id": "O1", "name_cn": "清华大学"}
    )
    edge_match = MagicMock(
        id="S1->O1@0",
        type="EMPLOYED_BY",
        source_id="S1",
        target_id="O1",
        properties={"relation_type": "任职", "start_date": "", "end_date": ""},
    )
    edge_other = MagicMock(
        id="S1->O2@0",
        type="EMPLOYED_BY",
        source_id="S1",
        target_id="O2",
        properties={"relation_type": "合作", "start_date": "", "end_date": ""},
    )
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[scholar_node]))
    graph.get_node_edges = MagicMock(return_value=[edge_match, edge_other])
    graph.get_node = MagicMock(return_value=org_node)
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build(
        {"expertAId": "S1", "relationType": "任职", "dataSource": "all", "timeRange": None}
    )
    assert len(resp["enterprises"]) == 1
    assert resp["enterprises"][0]["relation"] == "任职"


def test_build_filters_by_time_range():
    graph = MagicMock()
    scholar_node = MagicMock(
        id="S1", labels=["Scholar"], properties={"scholar_id": "S1", "name_zh": "张伟"}
    )
    org_node = MagicMock(
        id="O1", labels=["Organization"], properties={"org_id": "O1", "name_cn": "清华大学"}
    )
    # 边的 end_date 早于 timeRange.start → 被滤掉
    edge_old = MagicMock(
        id="S1->O1@0",
        type="EMPLOYED_BY",
        source_id="S1",
        target_id="O1",
        properties={"relation_type": "任职", "start_date": "2010.01", "end_date": "2012.12"},
    )
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[scholar_node]))
    graph.get_node_edges = MagicMock(return_value=[edge_old])
    graph.get_node = MagicMock(return_value=org_node)
    svc = ExpertEnterpriseRelationService()
    svc._graph = graph  # noqa: SLF001
    resp = svc.build(
        {
            "expertAId": "S1",
            "relationType": "all",
            "dataSource": "all",
            "timeRange": {"start": "2018.01", "end": "2022.12"},
        }
    )
    assert resp["enterprises"] == []
