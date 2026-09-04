from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewValidationError,
    canonical_template,
    validate_action,
    validate_step_template,
)
from service.manual_review_production import ManualReviewService


def service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


def report(
    step="align",
    template="T_LINK",
    event="evt-1",
    fingerprint="fp-1",
    severity="P1",
    scope="OBJECT",
):
    return {
        "eventId": event,
        "occurredAt": datetime.now(UTC),
        "sourceTaskId": "TASK-001",
        "batchId": "BATCH-001",
        "stepId": step,
        "workflow": {
            "workflowType": "GraphBuildWorkflow",
            "workflowId": "wf-1",
            "runId": "run-1",
            "taskQueue": "graph",
            "resumeToken": "opaque-token",
        },
        "object": {"id": "OBJ-1", "type": "ExpertCandidate", "name": "脱敏专家"},
        "exception": {
            "code": "ALIGN_AMBIGUOUS",
            "message": "候选实体存在歧义",
            "fingerprint": fingerprint,
            "severity": severity,
            "scope": scope,
        },
        "templateId": template,
        "templateVersion": "1.0",
        "domain": "talent",
        "inputSnapshot": {"name": "脱敏专家"},
        "candidateSnapshot": {"existingCandidates": [{"id": "E-1"}]},
        "evidence": [],
        "ruleVersion": "align-v3",
    }


@pytest.mark.parametrize(
    "step,template",
    [
        ("source", "T_RUNTIME"),
        ("normalize", "T_DQ_FILL"),
        ("schema", "T_MAP"),
        ("extract", "T_RUNTIME"),
        ("align", "T_LINK"),
        ("validate", "T_EVIDENCE"),
        ("persist", "T_RUNTIME"),
    ],
)
def test_seven_steps_accept_only_registered_templates(step, template):
    assert validate_step_template(step, template) == template
    with pytest.raises(ReviewValidationError):
        validate_step_template(step, "T_ATTR" if step != "validate" else "T_LINK")


def test_template_aliases_confirm_type_and_client_rerun_rejected():
    assert canonical_template("T_ENTITY") == "T_LINK"
    assert canonical_template("T_RELATION") == "T_EVIDENCE"
    validate_action("T_MAP", "confirm-type", {"entityType": "Expert"})
    with pytest.raises(ReviewValidationError):
        validate_action("T_LINK", "entity-confirm", {"entityVerdict": "merge"})
    with pytest.raises(ReviewValidationError):
        validate_action("T_MAP", "confirm-type", {"entityType": "Expert", "rerunStepId": "persist"})


def test_event_and_business_idempotency():
    svc = service()
    first = svc.create_review_required(report(), "graph-build")
    same_event = svc.create_review_required(report(), "graph-build")
    same_business = svc.create_review_required(report(event="evt-2"), "graph-build")
    assert first["reviewId"] == same_event["reviewId"] == same_business["reviewId"]
    assert same_event["duplicate"] is True and same_business["duplicate"] is True


def test_batch_requires_p0():
    with pytest.raises(ReviewValidationError):
        service().create_review_required(report(severity="P1", scope="BATCH"), "graph-build")


def test_correction_hash_and_execution_ordering():
    from service.manual_review_domain import ReviewIdentity

    svc = service()
    identity = ReviewIdentity(
        "r1", "r1", frozenset({"reviewer"}), frozenset({"talent"}), "org", "req"
    )
    created = svc.create_review_required(report(), "graph-build")
    case = svc.get_case(created["reviewId"], identity)
    case = svc.claim(case["id"], case["version"], identity)
    case = svc.submit(
        case["id"], case["version"], "entity-confirm", {"entityVerdict": "create"}, "", identity
    )
    correction = svc.correction(case["id"])
    encoded = json.dumps(
        correction["payload"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    assert correction["payloadSha256"] == hashlib.sha256(encoded).hexdigest()
    common = {
        "executionId": "EXEC-1",
        "occurredAt": datetime.now(UTC),
        "stepId": "align",
        "workflowId": "wf-2",
        "runId": "run-2",
        "result": {},
        "error": None,
        "metrics": {},
    }
    svc.execution_event(case["id"], {**common, "eventId": "e1", "type": "CORRECTION_ACCEPTED"})
    svc.execution_event(case["id"], {**common, "eventId": "e2", "type": "RERUN_SUCCEEDED"})
    with pytest.raises(ReviewConflictError):
        svc.execution_event(case["id"], {**common, "eventId": "e3", "type": "RERUN_STARTED"})
    assert (
        svc.execution_event(case["id"], {**common, "eventId": "e2", "type": "RERUN_SUCCEEDED"})[
            "duplicate"
        ]
        is True
    )
    assert (
        svc.execution_event(
            case["id"], {**common, "eventId": "e4", "type": "VERIFICATION_SUCCEEDED"}
        )["status"]
        == "RESOLVED"
    )


class FakeGraph:
    def __init__(self, fields):
        self.fields = fields
        self.merged: list[tuple[list[str], dict, dict]] = []
        self.edges: list[tuple[str, str, str, dict]] = []
        self.writes: list[str] = []

    def execute_query(self, ngql):
        return {"records": [{"Field": f} for f in self.fields]}

    def execute_write(self, ngql):
        self.writes.append(ngql)
        return {"records": []}

    def merge_node(self, labels, key, props):
        self.merged.append((labels, key, props))

    def create_edge(self, from_id, to_id, edge_type, props):
        self.edges.append((from_id, to_id, edge_type, props))


def _reviewer():
    from service.manual_review_domain import ReviewIdentity

    return ReviewIdentity(
        "r1", "r1", frozenset({"reviewer"}), frozenset({"*"}), "org", "req-direct"
    )


def _direct_case(svc, monkeypatch, **overrides):
    graph = FakeGraph(["scholar_id", "name_zh", "name_en"])
    monkeypatch.setattr("infra.graph_db.get_trs_graph_client", lambda: graph)
    kwargs = dict(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="extract",
        kind="entity",
        candidate={"scholar_id": "S-1", "name_zh": "张三", "name_en": "Zhang San"},
        object_id="S-1",
        node_label="Scholar",
        reason="low confidence",
        confidence=0.4,
    )
    kwargs.update(overrides)
    created = svc.create_direct_case(**kwargs)
    return created["reviewId"], graph


def test_direct_decide_accept_with_modified_candidate_writes_corrected_fields(monkeypatch):
    svc = service()
    case_id, graph = _direct_case(svc, monkeypatch)
    identity = _reviewer()
    result = svc.direct_decide(
        case_id,
        1,
        True,
        "字段修正",
        identity,
        candidate={"scholar_id": "S-1", "name_zh": "李四", "org": "清华"},
    )
    assert result["status"] == "RESOLVED"
    assert graph.writes, "实体直写走 nGQL INSERT VERTEX"
    stmt = graph.writes[0]
    assert stmt.startswith("INSERT VERTEX Scholar(")  # label 以快照为准
    assert '"S-1":' in stmt  # 写图 vid 固定取 object_id
    assert '"李四"' in stmt  # 修正后的字段值
    # org 不在 schema 且无 extra_json，被 _coerce_to_schema 丢弃
    assert "org" not in stmt
    assert '"S-1"' in stmt  # scholar_id


def test_direct_decide_candidate_meta_fields_ignored(monkeypatch):
    svc = service()
    case_id, graph = _direct_case(svc, monkeypatch)
    svc.direct_decide(
        case_id,
        1,
        True,
        "",
        _reviewer(),
        candidate={
            "scholar_id": "S-1",
            "name_zh": "李四",
            "_nodeLabel": "Paper",
            "_fromId": "EVIL",
        },
    )
    assert graph.writes, "实体直写走 nGQL INSERT VERTEX"
    assert graph.writes[0].startswith("INSERT VERTEX Scholar(")  # 元字段以快照为准（Scholar），传入 _nodeLabel=Paper 被忽略


def test_direct_decide_empty_or_underscore_only_candidate_rejected(monkeypatch):
    svc = service()
    case_id, _ = _direct_case(svc, monkeypatch)
    with pytest.raises(ReviewValidationError, match="不能为空"):
        svc.direct_decide(case_id, 1, True, "", _reviewer(), candidate={"_nodeLabel": "Paper"})


def test_direct_decide_reject_with_candidate_rejected(monkeypatch):
    svc = service()
    case_id, graph = _direct_case(svc, monkeypatch)
    with pytest.raises(ReviewValidationError, match="驳回"):
        svc.direct_decide(case_id, 1, False, "", _reviewer(), candidate={"name_zh": "李四"})
    assert graph.merged == []


def test_direct_decide_audit_records_modified_fields(monkeypatch):
    svc = service()
    case_id, _ = _direct_case(svc, monkeypatch)
    svc.direct_decide(
        case_id,
        1,
        True,
        "修正",
        _reviewer(),
        candidate={"scholar_id": "S-1", "name_zh": "李四", "title": "教授"},
    )
    entries = svc.logs(case_id, _reviewer())
    accept = [e for e in entries if e["eventType"] == "DIRECT_ACCEPTED"][-1]
    detail = accept["detail"]
    assert detail["candidateModified"] is True
    assert detail["modifiedFields"]["added"] == ["title"]
    assert detail["modifiedFields"]["changed"] == ["name_zh"]
    assert detail["modifiedFields"]["removed"] == ["name_en"]
    assert detail["originalCandidateSha256"]
