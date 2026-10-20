"""Follow-up review probes using isolated fixtures and in-memory SQLite."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.update(AUTH_ENABLED="false", APP_ENV="test", AUTH_ALLOW_INSECURE_DEV_CONTEXT="true")

import pytest

ROOT = Path(os.environ["GRAY_GATE_REVIEW_BACKEND"]).resolve()

def load_fixture_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/unit" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

p = load_fixture_module("pipeline_followup_fixtures", "test_gray_gate_v2_pipeline.py")
r = load_fixture_module("service_followup_fixtures", "test_gray_gate_v2_review.py")
review_service = p.review_service
pipeline_env = p.pipeline_env
service = r.service

@pytest.fixture(autouse=True)
def isolate_metadata(monkeypatch):
    monkeypatch.setattr("service.manual_review_production.resolve_job_ids", lambda *args: {})
    monkeypatch.setattr("service.temporal_workflows._execution_context_for_cases", lambda: (SimpleNamespace(workflow_id="probe-wf", workflow_run_id="probe-run"), "probe-task", "probe-execution", {}))


@pytest.mark.asyncio
async def test_applied_create_survives_resolve_then_prewrite(service, pipeline_env, monkeypatch):
    from db_model.manual_review import ReviewCase
    from service.gray_gate import decision_policy
    from service.manual_review_production import sha
    from service.temporal_workflows import _gray_ingress_material, _prewrite_recheck, resolve_entity_batch
    record = {"id": "sch_new", "sourceRecordId": "row-1", "props": {"name": "张三", "org": "A"}}
    material, _, _ = _gray_ingress_material(step_id="source:bind-1#main", record=record, graph_space="dev2", name_tag="Scholar")
    case_id = r._link_case(service, vid="sch_new")
    with service.sf() as session:
        session.get(ReviewCase, case_id).dedupe_key = sha(material)
        session.commit()
    r._resolve(service, case_id, result={"entityVerdict": "create"})
    graph = p.use_graph(monkeypatch, p.FakeGraph(recall={"Scholar": [{"vid": "sch_9", "props": {"name": "张三", "org": "A"}}]}))
    resolved = await resolve_entity_batch(p._resolve_request([record]))
    assert resolved["keptAsNew"] == 1
    await _prewrite_recheck(graph, "Scholar", resolved["records"], graph={"space": "dev2"}, source_table="test", step_id="source:bind-1#main", decision_policy=decision_policy())
    assert resolved["records"][0]["id"] == "sch_new"


def test_two_successful_concurrent_parks_preserve_both_edges(service, monkeypatch):
    from db_model.manual_review import ReviewCase
    from service.gray_gate import decision_policy
    case_id = r._link_case(service, vid="a")
    original_factory = service.sf
    injected = False
    def factory():
        nonlocal injected
        session = original_factory()
        if not injected:
            injected = True
            original_commit = session.commit
            def commit_after_other_writer():
                service.park_or_rewrite_edges("LINK", [{"fromId": "a", "toId": "c", "props": {}}], "dev2", decision_policy=decision_policy())
                original_commit()
            session.commit = commit_after_other_writer
        return session
    monkeypatch.setattr(service, "sf", factory)
    result = service.park_or_rewrite_edges("LINK", [{"fromId": "a", "toId": "b", "props": {}}], "dev2", decision_policy=decision_policy())
    assert result["parked"] == 1
    with original_factory() as session:
        pending = json.loads(session.get(ReviewCase, case_id).candidate_snapshot)["_pendingRelations"]
    assert {rel["toId"] for rel in pending} == {"b", "c"}


@pytest.mark.asyncio
async def test_pending_declared_event_version_is_transmitted(review_service, pipeline_env, monkeypatch):
    from service.temporal_workflows import resolve_pending_entities
    p.schema_catalog(monkeypatch, "Person")
    p.use_graph(monkeypatch, p.FakeGraph(recall={"Person": [{"vid": "p9", "props": {"name": "王五", "org": "A", "city": "X", "email": "E"}}]}))
    item = p._pending_item("王五", props={"name": "王五", "org": "A", "city": "Y", "email": "F"})
    item["sourceEventVersion"] = "business-version-1"
    await resolve_pending_entities(p._pending_request([item]))
    case_id, _ = p._cases(review_service)[0]
    review_service.submit(case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "review probe", r.actor())
    item["sourceEventVersion"] = "business-version-2"
    second = await resolve_pending_entities(p._pending_request([item]))
    assert second["grayCases"] == 1
    assert len(p._cases(review_service)) == 2
