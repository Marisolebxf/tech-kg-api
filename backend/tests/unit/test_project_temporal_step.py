"""Project uses the standard placeholder Activity and never invokes its ETL."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from service.temporal_workflows import execute_kg_step


@pytest.mark.asyncio
async def test_project_persist_does_not_run_project_pipeline():
    request = {
        "step": "persist",
        "kind": "entity",
        "domain": "project",
        "payload": {"limit": 2, "dry_run": True},
    }
    with patch("script.workflows.project_ingest_workflow.workflow") as pipeline:
        result = await execute_kg_step(request)

    assert result["status"] == "completed"
    assert result["domain"] == "project"
    assert result["output"] == request["payload"]
    pipeline.assert_not_called()
