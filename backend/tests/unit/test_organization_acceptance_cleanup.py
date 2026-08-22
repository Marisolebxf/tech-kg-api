from __future__ import annotations

import json
from pathlib import Path

import pytest

from script.cleanup_organization_virtual_graph import build_cleanup_plan, run
from script.organization_acceptance import collect_graph_snapshot, write_acceptance_report


class Result:
    def __init__(self, records):
        self.records = records


class SnapshotGraph:
    def labels(self):
        return ["Organization", "organization_base", "Person", "News", "Event", "Product"]

    def edge_types(self):
        from script.organization_acceptance import OWNED_EDGE_TYPES

        return list(OWNED_EDGE_TYPES)

    def execute_read(self, query):
        if "extra_json CONTAINS" in query and "MATCH (v:" in query:
            return Result([])
        if "MATCH (v:" in query:
            return Result([{"total": 4, "confidence_count": 3, "organization_id_count": 4}])
        return Result([{"total": 2, "confidence_count": 2, "organization_id_count": 2}])


def test_acceptance_report_is_scoped_and_durable(tmp_path: Path) -> None:
    snapshot = collect_graph_snapshot(SnapshotGraph())
    assert snapshot["tags"]["Organization"]["total"] == 4
    artifacts = write_acceptance_report(
        batch="ORG-TEST",
        workflow_result={"dryRun": True},
        before=snapshot,
        after=snapshot,
        output_dir=tmp_path,
    )
    payload = json.loads(Path(artifacts["json"]).read_text(encoding="utf-8"))
    assert payload["domain"] == "domestic_and_foreign_organization"
    assert Path(artifacts["markdown"]).is_file()


class CleanupGraph:
    def __init__(self):
        self.writes = []

    def labels(self):
        return ["Organization", "organization_base", "Person", "News", "Event", "Product"]

    def execute_read(self, query):
        if "MATCH (v:`Organization`)" in query:
            return Result(
                [
                    {"vid": "org_stub_owned", "source_table": "stub", "properties": {}},
                    {"vid": "org_stub_shared", "source_table": "stub", "properties": {}},
                ]
            )
        return Result(
            [
                {
                    "edge_type": "INVESTS_IN",
                    "source_vid": "org_stub_owned",
                    "target_vid": "org_real",
                    "edge_rank": 1,
                    "properties": {"source_table": "dwd_org_invest_info"},
                },
                {
                    "edge_type": "WORKS_AT",
                    "source_vid": "person_real",
                    "target_vid": "org_stub_shared",
                    "edge_rank": 2,
                    "properties": {"source_table": "scholar_profile"},
                },
            ]
        )

    def edge_types(self):
        return ["INVESTS_IN"]

    def execute_write(self, query):
        self.writes.append(query)
        return Result([])


def test_cleanup_blocks_shared_domain_vertices_and_defaults_to_dry_run(tmp_path: Path) -> None:
    graph = CleanupGraph()
    plan = build_cleanup_plan(graph)
    assert [item["vid"] for item in plan["deletableVertices"]] == ["org_stub_owned"]
    assert [item["vid"] for item in plan["blockedVertices"]] == ["org_stub_shared"]
    result = run(graph=graph, report_path=tmp_path / "cleanup.json")
    assert result["dryRun"] is True
    assert graph.writes == []


def test_cleanup_write_requires_matching_confirmation(tmp_path: Path) -> None:
    graph = CleanupGraph()
    with pytest.raises(ValueError, match="matching"):
        run(
            graph=graph,
            dry_run=False,
            cleanup_batch="ORG_CLEAN_TEST",
            confirm_batch="wrong",
            report_path=tmp_path / "cleanup.json",
        )
