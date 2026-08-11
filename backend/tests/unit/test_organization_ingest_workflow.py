from __future__ import annotations

from contextlib import contextmanager

import pytest

import script.organization_entity_etl as entity
import script.organization_etl_common as common
import script.organization_relation_etl as relation
from infra.graph_db.client import TRSGraphClient
from script.workflows.organization_ingest_workflow import workflow


@pytest.fixture(autouse=True)
def isolate_graph_connection(monkeypatch):
    monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)


def test_workflow_runs_entities_before_relations_and_forwards_scope(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    @contextmanager
    def fake_lock(name: str, batch: str):
        calls.append(("lock", {"name": name, "batch": batch}))
        yield

    def fake_entities(**kwargs):
        calls.append(("entity", kwargs))
        return {"dwd_org_base_info": entity.EntityStats(queried=2, valid=2)}

    def fake_relations(**kwargs):
        calls.append(("relation", kwargs))
        return {"dwd_org_shareholder_info": relation.RelationStats(queried=1, valid=1)}

    monkeypatch.setattr(common, "exclusive_etl_lock", fake_lock)
    monkeypatch.setattr(entity, "run_etl", fake_entities)
    monkeypatch.setattr(relation, "run_etl", fake_relations)

    result = workflow(
        {
            "stage": "all",
            "scope": "domestic",
            "max_records": 5,
            "dry_run": True,
            "ingest_batch": "TEST-BATCH",
            "report": False,
        }
    )

    assert [name for name, _ in calls] == ["lock", "entity", "relation"]
    assert calls[1][1]["domestic_only"] is True
    assert calls[1][1]["foreign_only"] is False
    assert calls[2][1]["max_records"] == 5
    assert result["entities"]["dwd_org_base_info"]["queried"] == 2
    assert result["relations"]["dwd_org_shareholder_info"]["queried"] == 1
    assert result["dryRun"] is True
    assert result["space"] == "dev"


def test_workflow_defaults_to_safe_dry_run(monkeypatch) -> None:
    captured: dict = {}

    @contextmanager
    def fake_lock(name: str, batch: str):
        yield

    def fake_entities(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(common, "exclusive_etl_lock", fake_lock)
    monkeypatch.setattr(entity, "run_etl", fake_entities)

    result = workflow({"stage": "entity", "max_records": 1, "report": False})
    assert captured["dry_run"] is True
    assert result["dryRun"] is True


def test_workflow_supports_full_run_and_strict_boolean(monkeypatch) -> None:
    captured: dict = {}

    @contextmanager
    def fake_lock(name: str, batch: str):
        yield

    def fake_entities(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(common, "exclusive_etl_lock", fake_lock)
    monkeypatch.setattr(entity, "run_etl", fake_entities)
    monkeypatch.setattr(entity, "initialize_schema", lambda graph: None)
    result = workflow({"stage": "entity", "dry_run": "false", "report": False, "max_records": None})
    assert captured["max_records"] is None
    assert result["dryRun"] is False


def test_workflow_rejects_ambiguous_boolean() -> None:
    with pytest.raises(ValueError, match="JSON boolean"):
        workflow({"stage": "entity", "dry_run": "not-a-bool", "report": False})
