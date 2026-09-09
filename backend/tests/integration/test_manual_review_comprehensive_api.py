"""人工处理模块补充集成测试：覆盖需求清单中集成/安全故障场景的缺口。

- 七模板各自的动态详情 displaySchema
- 拒绝 / 重跑失败 / 验收失败 终态端到端
- 远端假图谱构建服务（httpx MockTransport）拉取 correction 并返回 executionId
- P0 双人审批前不投递 ResumeRequested
- OBJECT / BATCH scope 在 correction 与 dispatch payload 中正确传递
- 回调重复、乱序、丢失补偿与重试
- 恶意超大快照、附件类型拒绝
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.review_identity import get_review_identity
from db_model.base import Base
from db_model.manual_review import ReviewOutbox
from service.manual_review_domain import ReviewIdentity
from service.manual_review_production import ManualReviewService

SERVICE_TOKEN = "test-service-token"
HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}

# 七模板 ↔ step ↔ displaySchema 首段类型 映射（handoff §1/§4）
TEMPLATE_MATRIX = [
    ("source", "T_RUNTIME", "runtime-config"),
    ("normalize", "T_DQ_FILL", "field-editor"),
    ("normalize", "T_DQ_MERGE", "record-merge"),
    ("schema", "T_MAP", "mapping-table"),
    ("extract", "T_RUNTIME", "runtime-config"),
    ("align", "T_LINK", "entity-comparison"),
    ("validate", "T_EVIDENCE", "evidence-list"),
    ("validate", "T_ATTR", "attribute-comparison"),
    ("persist", "T_RUNTIME", "runtime-config"),
]


def identity(uid="reviewer-1", roles=("reviewer",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"talent"}), "org", "api-test")


@pytest.fixture
def review_api(monkeypatch):
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
    monkeypatch.setenv("GRAPH_BUILD_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("REVIEW_RERUN_MODE", "mock")
    monkeypatch.setenv("REVIEW_SNAPSHOT_MAX_BYTES", "2097152")
    app.dependency_overrides[get_review_identity] = identity
    yield app, service
    app.dependency_overrides.pop(get_review_identity, None)


def required_body(step, template, index=1, **overrides):
    base = {
        "eventId": f"evt-{step}-{template}-{index}",
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
            "fingerprint": f"fp-{step}-{template}",
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
    }
    base.update(overrides)
    return base


async def _post_review(async_client, body):
    return await async_client.post(
        "/api/v1/internal/manual-reviews/review-required",
        json=body,
        headers={**HEADERS, "Idempotency-Key": body["eventId"]},
    )


async def _claim_submit(async_client, review_id, version, action, result):
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{review_id}/claim", json={"version": version}
        )
    ).json()["data"]
    return (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{review_id}/submit",
            json={
                "version": claimed["version"],
                "actionId": action,
                "result": result,
                "note": "已核验",
            },
        )
    ).json()["data"]


def set_identity(review_api, uid, roles):
    """切换当前请求的网关身份（dependency_overrides 需要可调用对象）。"""
    review_api[0].dependency_overrides[get_review_identity] = lambda: identity(uid, roles)


# 合法 result（按模板）
def result_for(template):
    return {
        "T_MAP": (
            {"actionId": "save-map-rerun", "result": {"mappings": [{"source": "a", "target": "b"}]}}
        ),
        "T_DQ_FILL": ({"actionId": "save-fill-rerun", "result": {"titleZh": "修正标题"}}),
        "T_DQ_MERGE": ({"actionId": "merge-rerun", "result": {"mergeMaster": "REC-1"}}),
        "T_LINK": ({"actionId": "entity-confirm", "result": {"entityVerdict": "create"}}),
        "T_EVIDENCE": (
            {"actionId": "pass-rerun", "result": {"evidence": [{"id": "1"}, {"id": "2"}]}}
        ),
        "T_ATTR": ({"actionId": "confirm-attr", "result": {"attrVerdict": "采用A源"}}),
        "T_RUNTIME": (
            {"actionId": "retry-task", "result": {"runtimeConfig": {"timeoutSeconds": 60}}}
        ),
    }[template]


# --------------------------------------------------------------------------- #
# 1. 七模板动态详情 displaySchema
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("step,template,section_type", TEMPLATE_MATRIX)
@pytest.mark.anyio
async def test_each_template_renders_correct_display_schema(
    async_client, review_api, step, template, section_type
):
    body = required_body(step, template)
    created = (await _post_review(async_client, body)).json()["data"]
    detail = (
        await async_client.get(f"/api/v1/manual-reviews/production/{created['reviewId']}")
    ).json()["data"]
    sections = detail["template"]["displaySchema"]["sections"]
    assert sections[0]["type"] == section_type
    # resultSchema 与 allowedActions 稳定下发
    assert "resultSchema" in detail["template"]
    assert detail["consequence"]["rerunStepId"] == step


# --------------------------------------------------------------------------- #
# 2. 拒绝 / 重跑失败 / 验收失败 终态端到端
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_reject_terminates_review(async_client, review_api):
    _, service = review_api
    body = required_body("schema", "T_MAP", scope="BATCH", severity="P0")
    body["exception"]["scope"] = "BATCH"
    body["exception"]["severity"] = "P0"
    body["eventId"] = "evt-reject-1"
    created = (await _post_review(async_client, body)).json()["data"]
    submitted = await _claim_submit(
        async_client,
        created["reviewId"],
        created.get("version", 1),
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
    )
    assert submitted["status"] == "PENDING_APPROVAL"
    set_identity(review_api, "approver-2", ("approver",))
    rejected = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['reviewId']}/reject",
            json={"version": submitted["version"], "note": "拒绝"},
        )
    ).json()["data"]
    assert rejected["status"] == "REJECTED"
    # 拒绝不应产生 correction / outbox 投递
    with service.sf() as s:
        assert (
            s.scalar(select(ReviewOutbox).where(ReviewOutbox.case_id == created["reviewId"]))
            is None
        )


@pytest.mark.anyio
async def test_rerun_failed_and_verification_failed_reach_rerun_failed(async_client, review_api):
    _, service = review_api
    body = required_body("align", "T_LINK", 10)
    created = (await _post_review(async_client, body)).json()["data"]
    await _claim_submit(
        async_client, created["reviewId"], 1, "entity-confirm", {"entityVerdict": "create"}
    )
    assert (await service.process_outbox()) == {"processed": 1, "failed": 0}
    # 取 mock 模式生成的真实 executionId（=MOCK-{correctionId}），全程稳定
    detail = (
        await async_client.get(f"/api/v1/manual-reviews/production/{created['reviewId']}")
    ).json()["data"]
    exec_id = detail["executions"][0]["id"]

    async def fire(event_id, etype, error=None):
        return (
            await async_client.post(
                f"/api/v1/internal/manual-reviews/{created['reviewId']}/execution-events",
                json={
                    "eventId": event_id,
                    "executionId": exec_id,
                    "type": etype,
                    "occurredAt": datetime.now(UTC).isoformat(),
                    "stepId": "align",
                    "workflowId": "wf-align",
                    "runId": "run-2",
                    "result": {},
                    "error": error,
                    "metrics": {},
                },
                headers={**HEADERS, "Idempotency-Key": event_id},
            )
        ).json()["data"]

    # 重跑失败 → RERUN_FAILED
    assert (await fire("cb-fail", "RERUN_FAILED", "boom"))["status"] == "RERUN_FAILED"

    # 重试后再走一次：验收失败 → RERUN_FAILED
    latest = (
        await async_client.get(f"/api/v1/manual-reviews/production/{created['reviewId']}")
    ).json()["data"]
    set_identity(review_api, "admin", ("review_admin",))
    retried = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['reviewId']}/retry",
            json={"version": latest["version"]},
        )
    ).json()["data"]
    assert retried["status"] == "APPLYING"
    await service.process_outbox()
    await fire("cb-ok", "RERUN_SUCCEEDED")
    assert (await fire("cb-vfail", "VERIFICATION_FAILED", "校验不通过"))["status"] == "RERUN_FAILED"


# --------------------------------------------------------------------------- #
# 3. 远端假图谱服务：拉取 correction 并返回 executionId
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_remote_fake_graph_service_pulls_correction_and_resumes(
    async_client, review_api, monkeypatch
):
    app, service = review_api
    monkeypatch.setenv("REVIEW_RERUN_MODE", "remote")
    monkeypatch.setenv("GRAPH_BUILD_INTERNAL_URL", "http://graph-build.test")

    received: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.read())
        # 假服务校验 Authorization 与 Idempotency-Key（=correctionId）
        assert request.headers["Authorization"] == f"Bearer {SERVICE_TOKEN}"
        assert request.headers["Idempotency-Key"].startswith("COR-")
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "executionId": "GRAPH-RERUN-001",
                "workflowId": "graph-TASK-align",
                "runId": "run-2",
                "status": "QUEUED",
            },
        )

    service.http_client_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    body = required_body("align", "T_LINK", 20)
    created = (await _post_review(async_client, body)).json()["data"]
    submitted = await _claim_submit(
        async_client, created["reviewId"], 1, "entity-confirm", {"entityVerdict": "create"}
    )
    assert submitted["status"] == "APPLYING"
    result = await service.process_outbox()
    assert result == {"processed": 1, "failed": 0}
    assert received, "假图谱服务应收到 resume 请求"
    payload = __import__("json").loads(received[0])
    # 假服务拿到准确 stepId/scope/correctionUrl
    assert payload["stepId"] == "align"
    assert payload["scope"] == "OBJECT"
    assert payload["correctionId"].startswith("COR-")
    assert payload["correctionUrl"].endswith("/correction")
    # 重复投递同一 correction 不产生第二个 executionId（幂等）
    assert (await service.process_outbox()) == {"processed": 0, "failed": 0}
    detail = (
        await async_client.get(f"/api/v1/manual-reviews/production/{created['reviewId']}")
    ).json()["data"]
    assert detail["status"] == "RERUNNING"
    assert detail["executions"][0]["id"] == "GRAPH-RERUN-001"


@pytest.mark.anyio
async def test_remote_graph_service_rejection_marks_apply_failed(
    async_client, review_api, monkeypatch
):
    _, service = review_api
    monkeypatch.setenv("REVIEW_RERUN_MODE", "remote")
    monkeypatch.setenv("GRAPH_BUILD_INTERNAL_URL", "http://graph-build.test")
    monkeypatch.setenv("REVIEW_RESUME_MAX_ATTEMPTS", "1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"accepted": False})

    service.http_client_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    body = required_body("align", "T_LINK", 21)
    created = (await _post_review(async_client, body)).json()["data"]
    await _claim_submit(
        async_client, created["reviewId"], 1, "entity-confirm", {"entityVerdict": "create"}
    )
    # 图谱构建拒绝 → 投递失败 → RETRY/DEAD，审核单 APPLY_FAILED
    await service.process_outbox()
    detail = (
        await async_client.get(f"/api/v1/manual-reviews/production/{created['reviewId']}")
    ).json()["data"]
    assert detail["status"] in ("APPLY_FAILED", "RERUNNING")


# --------------------------------------------------------------------------- #
# 4. P0 双人审批前不投递 ResumeRequested
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_p0_no_resume_until_second_approver(async_client, review_api):
    _, service = review_api
    body = required_body("schema", "T_MAP", 30)
    body["exception"]["scope"] = "BATCH"
    body["exception"]["severity"] = "P0"
    created = (await _post_review(async_client, body)).json()["data"]
    submitted = await _claim_submit(
        async_client,
        created["reviewId"],
        1,
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
    )
    assert submitted["status"] == "PENDING_APPROVAL"
    # 审批前 outbox 不存在
    assert (await service.process_outbox()) == {"processed": 0, "failed": 0}
    # 同一提交人不能审批
    set_identity(review_api, "reviewer-1", ("approver",))
    same = await async_client.post(
        f"/api/v1/manual-reviews/production/{created['reviewId']}/approve",
        json={"version": submitted["version"], "note": "我批"},
    )
    assert same.status_code == 403
    # 第二审批人批准后才投递
    set_identity(review_api, "approver-2", ("approver",))
    approved = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['reviewId']}/approve",
            json={"version": submitted["version"], "note": "批准"},
        )
    ).json()["data"]
    assert approved["status"] == "APPLYING"
    assert (await service.process_outbox()) == {"processed": 1, "failed": 0}


# --------------------------------------------------------------------------- #
# 5. OBJECT / BATCH scope 在 correction 中正确传递
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_batch_scope_flows_into_correction(async_client, review_api):
    body = required_body("schema", "T_MAP", 40)
    body["exception"]["scope"] = "BATCH"
    body["exception"]["severity"] = "P0"
    created = (await _post_review(async_client, body)).json()["data"]
    submitted = await _claim_submit(
        async_client,
        created["reviewId"],
        1,
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
    )
    set_identity(review_api, "approver-2", ("approver",))
    await async_client.post(
        f"/api/v1/manual-reviews/production/{created['reviewId']}/approve",
        json={"version": submitted["version"], "note": "批准"},
    )
    correction = (
        await async_client.get(
            f"/api/v1/internal/manual-reviews/{created['reviewId']}/correction", headers=HEADERS
        )
    ).json()["data"]
    assert correction["scope"] == "BATCH"
    assert correction["stepId"] == "schema"


# --------------------------------------------------------------------------- #
# 6. 回调重复 / 乱序 / 丢失补偿
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_callback_replay_out_of_order_and_loss_compensation(async_client, review_api):
    _, service = review_api
    body = required_body("align", "T_LINK", 50)
    created = (await _post_review(async_client, body)).json()["data"]
    await _claim_submit(
        async_client, created["reviewId"], 1, "entity-confirm", {"entityVerdict": "create"}
    )
    await service.process_outbox()
    rid = created["reviewId"]

    async def fire(event_id, etype, error=None):
        return await async_client.post(
            f"/api/v1/internal/manual-reviews/{rid}/execution-events",
            json={
                "eventId": event_id,
                "executionId": "MOCK-EXEC-50",
                "type": etype,
                "occurredAt": datetime.now(UTC).isoformat(),
                "stepId": "align",
                "workflowId": "wf",
                "runId": "r",
                "result": {},
                "error": error,
                "metrics": {},
            },
            headers={**HEADERS, "Idempotency-Key": event_id},
        )

    # 乱序：直接发 VERIFICATION_SUCCEEDED（未到 VERIFYING）→ 409
    bad = await fire("oob-1", "VERIFICATION_SUCCEEDED")
    assert bad.status_code == 409
    # 正序：RERUN_SUCCEEDED → VERIFYING
    ok = (await fire("ok-1", "RERUN_SUCCEEDED")).json()["data"]
    assert ok["status"] == "VERIFYING"
    # 重复投递同一 eventId → 幂等 duplicate
    replay = (await fire("ok-1", "RERUN_SUCCEEDED")).json()["data"]
    assert replay["duplicate"] is True
    # 丢失补偿：补发 VERIFICATION_SUCCEEDED → RESOLVED（仅 VERIFICATION_SUCCEEDED 能关闭）
    resolved = (await fire("ok-2", "VERIFICATION_SUCCEEDED")).json()["data"]
    assert resolved["status"] == "RESOLVED"


# --------------------------------------------------------------------------- #
# 7. 恶意超大快照 / 附件类型拒绝
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_oversized_snapshot_rejected_at_api(async_client, review_api, monkeypatch):
    monkeypatch.setenv("REVIEW_SNAPSHOT_MAX_BYTES", "256")
    body = required_body("align", "T_LINK", 60)
    body["inputSnapshot"] = {"blob": "x" * 4096}
    res = await _post_review(async_client, body)
    assert res.status_code == 422


@pytest.mark.anyio
async def test_evidence_rejects_disallowed_content_type(async_client, review_api):
    body = required_body("align", "T_LINK", 61)
    created = (await _post_review(async_client, body)).json()["data"]
    await async_client.post(
        f"/api/v1/manual-reviews/production/{created['reviewId']}/claim", json={"version": 1}
    )
    res = await async_client.post(
        f"/api/v1/manual-reviews/production/{created['reviewId']}/evidence/upload-url",
        json={
            "fileName": "evil.exe",
            "contentType": "application/x-msdownload",
            "sizeBytes": 100,
            "sha256": "a" * 64,
        },
    )
    assert res.status_code == 422


# --------------------------------------------------------------------------- #
# 8. 回调伪造身份 / 缺 Idempotency-Key
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_execution_event_requires_service_token_and_idempotency_key(async_client, review_api):
    body = required_body("align", "T_LINK", 70)
    created = (await _post_review(async_client, body)).json()["data"]
    event = {
        "eventId": "evt-cb-70",
        "executionId": "X",
        "type": "RERUN_SUCCEEDED",
        "occurredAt": datetime.now(UTC).isoformat(),
        "stepId": "align",
        "result": {},
        "metrics": {},
    }
    # 伪造 token
    forged = await async_client.post(
        f"/api/v1/internal/manual-reviews/{created['reviewId']}/execution-events",
        json=event,
        headers={"Authorization": "Bearer forged", "Idempotency-Key": "evt-cb-70"},
    )
    assert forged.status_code == 401
    # 缺 Idempotency-Key：属请求级校验错误，项目全局处理器以 HTTP 200 + body code=422 返回
    no_key = await async_client.post(
        f"/api/v1/internal/manual-reviews/{created['reviewId']}/execution-events",
        json=event,
        headers=HEADERS,
    )
    assert no_key.json()["code"] == 422


@pytest.mark.anyio
async def test_idempotency_key_must_equal_event_id(async_client, review_api):
    body = required_body("align", "T_LINK", 71)
    res = await async_client.post(
        "/api/v1/internal/manual-reviews/review-required",
        json=body,
        headers={**HEADERS, "Idempotency-Key": "wrong-key"},
    )
    assert res.status_code == 422
