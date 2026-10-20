"""Read-only review probes: only fake graphs and in-memory SQLite."""
import importlib.util
import os
from pathlib import Path

os.environ.update(AUTH_ENABLED="false", APP_ENV="test", AUTH_ALLOW_INSECURE_DEV_CONTEXT="true")

import pytest
from temporalio.exceptions import ApplicationError

ROOT = Path(os.environ["GRAY_GATE_REVIEW_BACKEND"]).resolve()

def load_fixture_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests/unit" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

p = load_fixture_module("pipeline_review_fixtures", "test_gray_gate_v2_pipeline.py")
r = load_fixture_module("service_review_fixtures", "test_gray_gate_v2_review.py")
review_service = p.review_service
pipeline_env = p.pipeline_env
service = r.service

@pytest.fixture(autouse=True)
def isolate_execution_metadata(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("service.manual_review_production.resolve_job_ids", lambda *args: {})
    monkeypatch.setattr("service.temporal_workflows._execution_context_for_cases", lambda: (SimpleNamespace(workflow_id="probe-wf", workflow_run_id="probe-run"), "probe-task", "probe-execution", {}))


@pytest.mark.asyncio
async def test_batch_merge_obeys_v2_fail_closed(review_service, pipeline_env, monkeypatch):
    from service.temporal_workflows import resolve_entity_batch
    p.use_graph(monkeypatch, p.FakeGraph())
    records = [{"id": vid, "props": {"name": "张三", "org": "A"}} for vid in ("a", "b")]
    with pytest.raises(ApplicationError, match="DEFERRED_MERGE_BLOCKED"):
        await resolve_entity_batch(p._resolve_request(records))


def test_descriptor_transport_error_is_not_invalid(monkeypatch):
    from service.temporal_workflows import _pending_write_descriptor_ok
    def broken_db():
        raise RuntimeError("transient DB transport failure")
    monkeypatch.setattr("infra.mysql.get_session_factory", broken_db)
    with pytest.raises(RuntimeError, match="transport"):
        _pending_write_descriptor_ok(p.FakeGraph(), "Person", "dev2")


def test_event_key_uses_source_row_not_generated_audit_time(monkeypatch):
    from service.temporal_workflows import _gray_ingress_material
    monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "review-only-test-key")
    record = {"id": "v1", "sourceRecordId": "real-source-row", "props": {"name": "张三", "update_time": "2026-10-21 01:00:00"}}
    first, _, _ = _gray_ingress_material(step_id="source:s#main", record=record, graph_space="dev2", name_tag="Person")
    record["props"]["update_time"] = "2026-10-21 02:00:00"
    second, _, _ = _gray_ingress_material(step_id="source:s#main", record=record, graph_space="dev2", name_tag="Person")
    assert first[1] == "real-source-row"
    assert first == second

def test_event_key_ignores_volatile_output_time(monkeypatch):
    from service.temporal_workflows import _gray_ingress_material
    monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "review-only-test-key")
    record = {"id": "v1", "sourceRecordId": "r1", "props": {"name": "张三", "ingest_time": "2026-10-21 01:00:00"}}
    first, _, _ = _gray_ingress_material(step_id="source:s#main", record=record, graph_space="dev2", name_tag="Person")
    record["props"]["ingest_time"] = "2026-10-21 02:00:00"
    second, _, _ = _gray_ingress_material(step_id="source:s#main", record=record, graph_space="dev2", name_tag="Person")
    assert first == second


def test_apply_failed_case_blocks_new_edges(service):
    from db_model.manual_review import ReviewCase, ReviewVerdictApplication
    from service.gray_gate import VerdictNotAppliedError, decision_policy
    case_id = r._link_case(service)
    with service.sf() as s:
        c = s.get(ReviewCase, case_id)
        c.status = "APPLY_FAILED"
        s.add(ReviewVerdictApplication(case_id=case_id, verdict="create", apply_status="FAILED", created_at=c.created_at, updated_at=c.updated_at))
        s.commit()
    with pytest.raises(VerdictNotAppliedError):
        service.park_or_rewrite_edges("AUTHORED_BY", [r._edge()], "dev2", decision_policy=decision_policy())


@pytest.mark.asyncio
async def test_rejected_event_stays_rejected_if_candidate_recall_changes(review_service, pipeline_env, monkeypatch):
    from service.temporal_workflows import resolve_pending_entities
    p.schema_catalog(monkeypatch, "Person")
    p.use_graph(monkeypatch, p.FakeGraph(recall={"Person": [{"vid": "p9", "props": {"name": "王五", "org": "A", "city": "X", "email": "E"}}]}))
    item = p._pending_item("王五", props={"name": "王五", "org": "A", "city": "Y", "email": "F"})
    await resolve_pending_entities(p._pending_request([item]))
    case_id, _ = p._cases(review_service)[0]
    review_service.submit(case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "review probe", r.actor())
    graph = p.use_graph(monkeypatch, p.FakeGraph())
    result = await resolve_pending_entities(p._pending_request([item]))
    assert result["written"] == 0
    assert graph.writes == []


def test_parked_edge_does_not_bypass_second_pending_endpoint(service, monkeypatch):
    from service.gray_gate import decision_policy
    from service.manual_review_production import ManualReviewService
    from types import SimpleNamespace
    a = r._link_case(service, vid="a")
    r._link_case(service, vid="b")
    service.park_or_rewrite_edges("LINK", [{"fromId": "a", "toId": "b", "props": {}}], "dev2", decision_policy=decision_policy())
    edges = []
    fake_graph = SimpleNamespace(create_edge=lambda frm, to, edge_type, props: edges.append((frm,to)))
    monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda *args: fake_graph)
    monkeypatch.setattr(ManualReviewService, "_insert_withheld_vertex", lambda *args: None)
    monkeypatch.setattr(ManualReviewService, "_coerce_to_schema", lambda *args, **kwargs: {})
    monkeypatch.setattr(ManualReviewService, "_edge_fields", lambda *args: set())
    monkeypatch.setattr(ManualReviewService, "_sync_entity_search_after_write", lambda *args: None)
    service.submit(a, 1, "entity-confirm", {"entityVerdict": "create"}, "review probe", r.actor())
    assert edges == []

def test_detail_keeps_build_time_evidence(service, monkeypatch):
    import json
    from db_model.manual_review import ReviewCase
    from service.manual_review_production import ManualReviewService
    case_id = r._link_case(service)
    with service.sf() as s:
        c = s.get(ReviewCase, case_id)
        snap = json.loads(c.candidate_snapshot)
        snap["_incoming"]["props"] = {"name": "张三", "org": "A"}
        snap["existingCandidates"][0].update(propsAgree=0.5, propCompared=0, propMatched=0, comparedProps=[])
        monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda *args: object())
        monkeypatch.setattr(ManualReviewService, "_es_same_name_by_vid", lambda *args: {"sch_9": {"props": {"name": "张三", "org": "A"}}})
        out = service._enrich_link_snapshot(c, snap)
        assert out["existingCandidates"][0]["propsAgree"] == 0.5
