from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.review_identity import get_review_identity
from db_model.base import Base
from service.manual_review_domain import ReviewIdentity
from service.manual_review_production import ManualReviewService


def identity():
    return ReviewIdentity(
        "reviewer-1", "审核员", frozenset({"reviewer"}), frozenset({"talent"}), "org", "api-test"
    )


@pytest.fixture
def graph_handoff_api(monkeypatch):
    from biz.handler import manual_review as public_handler
    from biz.handler import manual_review_internal as internal_handler
    from main import app

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    service = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(public_handler, "production_service", service)
    monkeypatch.setattr(internal_handler, "manual_review_service", service)
    monkeypatch.setenv("GRAPH_BUILD_SERVICE_TOKEN", "test-service-token")
    monkeypatch.setenv("REVIEW_RERUN_MODE", "mock")
    app.dependency_overrides[get_review_identity] = identity
    yield app, service
    app.dependency_overrides.pop(get_review_identity, None)


def payload(step, template, index=1):
    return {
        "eventId": f"evt-{step}-{index}",
        "occurredAt": datetime.now(UTC).isoformat(),
        "sourceTaskId": f"TASK-{step}",
        "batchId": "BATCH-1",
        "stepId": step,
        "workflow": {
            "workflowType": "GraphBuildWorkflow",
            "workflowId": f"wf-{step}",
            "runId": "run-1",
            "taskQueue": "graph",
            "resumeToken": f"opaque-{step}",
        },
        "object": {"id": f"OBJ-{step}", "type": "Candidate", "name": f"脱敏对象-{step}"},
        "exception": {
            "code": f"{step.upper()}_REVIEW_REQUIRED",
            "message": f"{step} 需要人工处理",
            "fingerprint": f"fp-{step}",
            "severity": "P1",
            "scope": "OBJECT",
        },
        "templateId": template,
        "templateVersion": "1.0",
        "domain": "talent",
        "inputSnapshot": {"raw": "真实脱敏输入"},
        "candidateSnapshot": {"value": "候选值"},
        "evidence": [],
        "ruleVersion": "rule-v1",
        "modelVersion": "model-v1",
    }


HEADERS = {"Authorization": "Bearer test-service-token"}


@pytest.mark.anyio
async def test_all_seven_nodes_enter_queue_and_duplicate_is_idempotent(
    async_client, graph_handoff_api
):
    pairs = [
        ("source", "T_RUNTIME"),
        ("normalize", "T_DQ_FILL"),
        ("schema", "T_MAP"),
        ("extract", "T_RUNTIME"),
        ("align", "T_LINK"),
        ("validate", "T_ATTR"),
        ("persist", "T_RUNTIME"),
    ]
    ids = []
    for step, template in pairs:
        body = payload(step, template)
        response = await async_client.post(
            "/api/v1/internal/manual-reviews/review-required",
            json=body,
            headers={**HEADERS, "Idempotency-Key": body["eventId"]},
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["data"]["reviewId"])
    queue = (
        await async_client.get(
            "/api/v1/manual-reviews/production/queue", params={"queue": "unclaimed"}
        )
    ).json()["data"]
    # 7 个案例全部落库；T_RUNTIME 属代码问题，按现行口径不进审核队列
    assert queue["total"] == 4 and {item["pipelineStepId"] for item in queue["items"]} == {
        "normalize",
        "schema",
        "align",
        "validate",
    }
    body = payload("align", "T_LINK")
    duplicate = await async_client.post(
        "/api/v1/internal/manual-reviews/review-required",
        json=body,
        headers={**HEADERS, "Idempotency-Key": body["eventId"]},
    )
    assert duplicate.json()["data"] == {
        "reviewId": ids[4],
        "status": "OPEN",
        "riskLevel": "P1",
        "isolationStrategy": "ISOLATE_OBJECT",
        "duplicate": True,
    }


@pytest.mark.anyio
async def test_dynamic_detail_correction_resume_and_callbacks(async_client, graph_handoff_api):
    _, service = graph_handoff_api
    body = payload("align", "T_LINK", 2)
    created = (
        await async_client.post(
            "/api/v1/internal/manual-reviews/review-required",
            json=body,
            headers={**HEADERS, "Idempotency-Key": body["eventId"]},
        )
    ).json()["data"]
    review_id = created["reviewId"]
    detail = (await async_client.get(f"/api/v1/manual-reviews/production/{review_id}")).json()[
        "data"
    ]
    assert detail["template"]["displaySchema"]["sections"][0]["type"] == "entity-comparison"
    assert (
        detail["data"]["input"] == body["inputSnapshot"]
        and detail["consequence"]["rerunStepId"] == "align"
    )
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{review_id}/claim",
            json={"version": detail["version"]},
        )
    ).json()["data"]
    submitted = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{review_id}/submit",
            json={
                "version": claimed["version"],
                "actionId": "entity-confirm",
                "result": {"entityVerdict": "create"},
                "note": "已核验",
            },
        )
    ).json()["data"]
    assert submitted["status"] == "APPLYING"
    correction_response = await async_client.get(
        f"/api/v1/internal/manual-reviews/{review_id}/correction", headers=HEADERS
    )
    correction = correction_response.json()["data"]
    assert correction["stepId"] == "align" and len(correction["payloadSha256"]) == 64
    assert (await service.process_outbox()) == {"processed": 1, "failed": 0}
    assert (await service.process_outbox()) == {"processed": 0, "failed": 0}

    def event(event_id, event_type):
        return {
            "eventId": event_id,
            "executionId": f"MOCK-{correction['correctionId']}",
            "type": event_type,
            "occurredAt": datetime.now(UTC).isoformat(),
            "stepId": "align",
            "workflowId": "wf-align",
            "runId": "run-2",
            "result": {},
            "error": None,
            "metrics": {},
        }

    rerun = event("callback-1", "RERUN_SUCCEEDED")
    response = await async_client.post(
        f"/api/v1/internal/manual-reviews/{review_id}/execution-events",
        json=rerun,
        headers={**HEADERS, "Idempotency-Key": rerun["eventId"]},
    )
    assert response.json()["data"]["status"] == "VERIFYING"
    verified = event("callback-2", "VERIFICATION_SUCCEEDED")
    response = await async_client.post(
        f"/api/v1/internal/manual-reviews/{review_id}/execution-events",
        json=verified,
        headers={**HEADERS, "Idempotency-Key": verified["eventId"]},
    )
    assert response.json()["data"]["status"] == "RESOLVED"
    repeated = await async_client.post(
        f"/api/v1/internal/manual-reviews/{review_id}/execution-events",
        json=verified,
        headers={**HEADERS, "Idempotency-Key": verified["eventId"]},
    )
    assert repeated.json()["data"]["duplicate"] is True


@pytest.mark.anyio
async def test_internal_endpoints_reject_forged_service_identity(async_client, graph_handoff_api):
    body = payload("align", "T_LINK", 3)
    response = await async_client.post(
        "/api/v1/internal/manual-reviews/review-required",
        json=body,
        headers={"Authorization": "Bearer forged", "Idempotency-Key": body["eventId"]},
    )
    assert response.status_code == 401
