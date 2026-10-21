"""Exercise actual CAS predicate conflicts, using isolated in-memory fixtures."""
import importlib.util
import json
import os
from pathlib import Path

os.environ.update(AUTH_ENABLED="false", APP_ENV="test", AUTH_ALLOW_INSECURE_DEV_CONTEXT="true")

import pytest

ROOT = Path(os.environ["GRAY_GATE_REVIEW_BACKEND"]).resolve()
spec = importlib.util.spec_from_file_location("cas_review_fixtures", ROOT / "tests/unit/test_gray_gate_v2_review.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
service = r.service

@pytest.fixture(autouse=True)
def isolate_metadata(monkeypatch):
    monkeypatch.setattr("service.manual_review_production.resolve_job_ids", lambda *args: {})

def test_stale_snapshot_cas_retries_after_other_successful_park(service):
    from db_model.manual_review import ReviewCase
    from service.gray_gate import decision_policy
    case_id = r._link_case(service, vid="a")
    attempts = []
    def mutate(snapshot):
        attempts.append(1)
        snapshot.setdefault("_pendingRelations", []).append({"edgeType": "LINK", "fromId": "a", "toId": "b", "props": {}})
        if len(attempts) == 1:
            service.park_or_rewrite_edges("LINK", [{"fromId": "a", "toId": "c", "props": {}}], "dev2", decision_policy=decision_policy())
    service._cas_mutate_case_snapshot(case_id, mutate, require_submittable=True)
    assert len(attempts) == 2
    with service.sf() as session:
        pending = json.loads(session.get(ReviewCase, case_id).candidate_snapshot)["_pendingRelations"]
    assert {rel["toId"] for rel in pending} == {"b", "c"}

def test_stale_detach_retries_and_preserves_newly_attached_edge(service):
    from db_model.manual_review import ReviewCase
    from service.gray_gate import decision_policy
    case_id = r._link_case(service, vid="a")
    service.park_or_rewrite_edges("LINK", [{"fromId": "a", "toId": "b", "props": {}}], "dev2", decision_policy=decision_policy())
    attempts = []
    def detach(snapshot):
        attempts.append(1)
        snapshot["_pendingRelations"] = [rel for rel in snapshot["_pendingRelations"] if rel["toId"] != "b"]
        if len(attempts) == 1:
            service.park_or_rewrite_edges("LINK", [{"fromId": "a", "toId": "c", "props": {}}], "dev2", decision_policy=decision_policy())
    service._cas_mutate_case_snapshot(case_id, detach)
    assert len(attempts) == 2
    with service.sf() as session:
        pending = json.loads(session.get(ReviewCase, case_id).candidate_snapshot)["_pendingRelations"]
    assert {rel["toId"] for rel in pending} == {"c"}
