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
    assert same_event["duplicate"] is True
    assert same_business["duplicate"] is True


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
