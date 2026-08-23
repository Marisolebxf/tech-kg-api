"""Unit tests for project stub cleanup helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from script.cleanup_project_stubs import (
    cleanup_project_stubs,
    is_project_stub,
)


def test_is_project_stub_by_source_and_kind() -> None:
    assert is_project_stub({"source": "project_stub"})
    assert is_project_stub({"org_kind": "project_stub"})
    assert is_project_stub({"person_kind": "project_stub"})
    assert is_project_stub({}, vid="org_project_stub_abc")
    assert not is_project_stub({"source": "zh_org"}, vid="org_123")


def test_cleanup_dry_run_counts_without_deletes() -> None:
    stub = SimpleNamespace(
        id="org_project_stub_1",
        properties={"source": "project_stub", "name_cn": "假机构"},
    )
    real = SimpleNamespace(id="org_real", properties={"source": "dwd_org_base_info"})
    edge = SimpleNamespace(id="e1", type="FUNDED_BY")

    graph = MagicMock()
    page = SimpleNamespace(items=[stub, real])
    graph.get_nodes_by_label.side_effect = lambda label, limit=500, offset=0: (
        page if offset == 0 and label == "Organization" else SimpleNamespace(items=[])
    )
    graph.get_node_edges.return_value = SimpleNamespace(items=[edge])

    report = cleanup_project_stubs(
        dry_run=True,
        labels=("Organization",),
        graph=graph,
    )
    assert report["stubs_found"] == 1
    assert report["edges_deleted"] == 1
    assert report["nodes_deleted"] == 1
    graph.delete_edge.assert_not_called()
    graph.delete_node.assert_not_called()


def test_cleanup_deletes_edges_then_nodes() -> None:
    stub = SimpleNamespace(
        id="person_project_stub_x",
        properties={"person_kind": "project_stub"},
    )
    edge = SimpleNamespace(id="e2", type="LEADS")
    graph = MagicMock()
    graph.get_nodes_by_label.side_effect = lambda label, limit=500, offset=0: (
        SimpleNamespace(items=[stub])
        if offset == 0 and label == "Person"
        else SimpleNamespace(items=[])
    )
    graph.get_node_edges.return_value = [edge]
    graph.delete_node.return_value = True

    report = cleanup_project_stubs(dry_run=False, labels=("Person",), graph=graph)
    assert report["stubs_found"] == 1
    assert report["edges_deleted"] == 1
    assert report["nodes_deleted"] == 1
    graph.delete_edge.assert_called_once_with("e2", edge_type="LEADS")
    graph.delete_node.assert_called_once_with("person_project_stub_x", detach=True)
