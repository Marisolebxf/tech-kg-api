"""项目抽取工作流封装脚本单测。"""

from __future__ import annotations

from unittest.mock import ANY, patch

from script.workflows.project_ingest_workflow import workflow


def test_workflow_runs_pipeline_stages():
    """workflow 应依次调用 schema/load/align/cleanup，并汇总 stages。"""
    fake_load = {"ingest_batch": "BATCH_X", "projects_merged": 3, "dry_run": True}
    fake_align = {"edges_FUNDED_BY": 1}
    fake_cleanup = {"stubs_found": 0}
    with (
        patch("script.load_project_graph.load_project_graph", return_value=fake_load) as mock_load,
        patch(
            "script.align_project_relations.align_project_relations", return_value=fake_align
        ) as mock_align,
        patch(
            "script.cleanup_project_stubs.cleanup_project_stubs", return_value=fake_cleanup
        ) as mock_cleanup,
        patch("script.load_project_graph.get_dev_graph_client") as mock_graph,
        patch("script.project_edge_schema.ensure_alignment_edge_schema") as mock_schema,
        patch("script.project_edge_schema.ensure_project_tag_confidence"),
        patch("infra.graph_db.close_trs_graph_client"),
    ):
        result = workflow({"limit": 5, "dry_run": True, "id_prefix": "P"})

    assert result["status"] == "completed"
    assert result["stages"]["load"] == fake_load
    assert result["stages"]["align"] == fake_align
    assert result["stages"]["cleanup"] == fake_cleanup
    assert result["stages"]["schema"]["status"] == "skipped"  # dry_run
    mock_schema.assert_not_called()
    mock_graph.assert_not_called()
    mock_load.assert_called_once()
    assert mock_load.call_args.kwargs["limit"] == 5
    assert mock_load.call_args.kwargs["dry_run"] is True
    assert mock_load.call_args.kwargs["id_prefix"] == "P"
    mock_align.assert_called_once()
    mock_cleanup.assert_called_once_with(dry_run=True, graph=ANY)


def test_workflow_defaults_limit_when_missing():
    with (
        patch(
            "script.load_project_graph.load_project_graph", return_value={"ok": True}
        ) as mock_load,
        patch("script.align_project_relations.align_project_relations", return_value={}),
        patch("script.cleanup_project_stubs.cleanup_project_stubs", return_value={}),
        patch("script.load_project_graph.get_dev_graph_client"),
        patch("script.project_edge_schema.ensure_alignment_edge_schema"),
        patch("script.project_edge_schema.ensure_project_tag_confidence"),
        patch("infra.graph_db.close_trs_graph_client"),
    ):
        workflow({})
    assert mock_load.call_args.kwargs["limit"] == 50


def test_workflow_skip_align_and_cleanup():
    with (
        patch("script.load_project_graph.load_project_graph", return_value={"ok": True}),
        patch("script.align_project_relations.align_project_relations") as mock_align,
        patch("script.cleanup_project_stubs.cleanup_project_stubs") as mock_cleanup,
        patch("script.load_project_graph.get_dev_graph_client"),
        patch("script.project_edge_schema.ensure_alignment_edge_schema"),
        patch("script.project_edge_schema.ensure_project_tag_confidence"),
        patch("infra.graph_db.close_trs_graph_client"),
    ):
        result = workflow({"skip_align": True, "skip_cleanup": True, "dry_run": True, "limit": 1})
    assert result["stages"]["align"]["status"] == "skipped"
    assert result["stages"]["cleanup"]["status"] == "skipped"
    mock_align.assert_not_called()
    mock_cleanup.assert_not_called()


def test_workflow_respects_nodes_only_skips_align():
    with (
        patch(
            "script.load_project_graph.load_project_graph", return_value={"ok": True}
        ) as mock_load,
        patch("script.align_project_relations.align_project_relations") as mock_align,
        patch("script.cleanup_project_stubs.cleanup_project_stubs", return_value={}),
        patch("script.load_project_graph.get_dev_graph_client"),
        patch("script.project_edge_schema.ensure_alignment_edge_schema"),
        patch("script.project_edge_schema.ensure_project_tag_confidence"),
        patch("infra.graph_db.close_trs_graph_client"),
    ):
        workflow({"nodes_only": True, "limit": 1, "dry_run": True})
    assert mock_load.call_args.kwargs["nodes_only"] is True
    mock_align.assert_not_called()


def test_workflow_backfill_confidence_only():
    """backfill_confidence 应仅回填 confidence，跳过 load/align/cleanup。"""
    fake_backfill = {"dry_run": False, "scanned": 3994, "updated": 3994, "skipped": 0}
    with (
        patch("script.load_project_graph.load_project_graph") as mock_load,
        patch("script.align_project_relations.align_project_relations") as mock_align,
        patch("script.cleanup_project_stubs.cleanup_project_stubs") as mock_cleanup,
        patch("script.load_project_graph.get_dev_graph_client"),
        patch(
            "script.load_project_graph.backfill_project_confidence", return_value=fake_backfill
        ) as mock_backfill,
        patch("script.project_edge_schema.ensure_alignment_edge_schema"),
        patch("script.project_edge_schema.ensure_project_tag_confidence"),
        patch("infra.graph_db.close_trs_graph_client"),
    ):
        result = workflow({"backfill_confidence": True})
    assert result["status"] == "completed"
    assert result["stages"]["backfill_confidence"] == fake_backfill
    assert result["stages"]["load"]["status"] == "skipped"
    mock_load.assert_not_called()
    mock_align.assert_not_called()
    mock_cleanup.assert_not_called()
    mock_backfill.assert_called_once()
