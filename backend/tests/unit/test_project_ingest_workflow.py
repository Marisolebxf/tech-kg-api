"""项目抽取工作流封装脚本单测。"""

from __future__ import annotations

from unittest.mock import patch

from script.workflows.project_ingest_workflow import workflow


def test_workflow_passes_payload_and_returns_report():
    """workflow(payload) 应把 payload 透传给 load_project_graph 并原样返回 report。"""
    fake_report = {"ingest_batch": "BATCH_X", "projects_merged": 3, "dry_run": True}
    with patch(
        "script.load_project_graph.load_project_graph", return_value=fake_report
    ) as mock_load:
        result = workflow({"limit": 5, "dry_run": True, "id_prefix": "P"})

    assert result == fake_report
    mock_load.assert_called_once_with(
        id_prefix="P", limit=5, nodes_only=False, relations_only=False, dry_run=True
    )


def test_workflow_defaults_limit_when_missing():
    """payload 不给 limit 时默认 50。"""
    with patch(
        "script.load_project_graph.load_project_graph", return_value={"ok": True}
    ) as mock_load:
        workflow({})
    mock_load.assert_called_once_with(
        id_prefix=None, limit=50, nodes_only=False, relations_only=False, dry_run=False
    )


def test_workflow_respects_nodes_and_relations_flags():
    with patch(
        "script.load_project_graph.load_project_graph", return_value={"ok": True}
    ) as mock_load:
        workflow({"nodes_only": True, "limit": 1})
    mock_load.assert_called_once_with(
        id_prefix=None, limit=1, nodes_only=True, relations_only=False, dry_run=False
    )
