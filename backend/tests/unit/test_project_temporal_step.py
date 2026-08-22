"""Unit tests for project Temporal activity step mapping."""

from __future__ import annotations

from unittest.mock import patch

from service.temporal_workflows import _run_project_step


def test_run_project_step_defers_until_persist():
    result = _run_project_step("align", {"limit": 3, "dry_run": True})
    assert result["status"] == "deferred_to_persist"
    assert result["output"]["limit"] == 3


def test_run_project_step_persist_runs_pipeline():
    fake = {"status": "completed", "stages": {"load": {}}}
    with patch(
        "script.workflows.project_ingest_workflow.workflow", return_value=fake
    ) as mock_pipeline:
        result = _run_project_step("persist", {"limit": 2, "dry_run": True})
    assert result["status"] == "completed"
    assert result["output"] == fake
    mock_pipeline.assert_called_once_with({"limit": 2, "dry_run": True})
