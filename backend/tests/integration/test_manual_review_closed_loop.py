"""【图谱构建】→【人工处理】→【图谱构建】端到端闭环测试。

图谱构建尚未开发，本文件按 handoff.md 伪造图谱构建服务（FakeGraphBuild），
真实地实现其契约义务：接收 resume → 回拉 correction → SHA-256 校验 → 返回 executionId
→ 驱动执行回调。人工处理侧使用真实 service / FastAPI app。借此验证整条闭环是否闭合。

闭环六段：
  L1 图谱构建→人工处理：POST /internal/manual-reviews/review-required
  L2 人工处理内部：领取 / 裁决 /（P0）双人审批 → 生成 correction + Outbox
  L3 人工处理→图谱构建：Outbox worker 调 POST /internal/review-resumes
  L4 图谱构建→人工处理：FakeGraphBuild 回拉 GET /correction 并校验 SHA-256
  L5 图谱构建→人工处理：POST /execution-events 回调
  L6 人工处理：仅 VERIFICATION_SUCCEEDED 关闭审核单 → RESOLVED
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from json import dumps as json_dumps
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.review_identity import get_review_identity
from db_model.base import Base
from db_model.manual_review import ReviewCorrection
from service.manual_review_domain import ReviewIdentity
from service.manual_review_production import ManualReviewService

SERVICE_TOKEN = "test-service-token"
HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def identity(uid="reviewer-1", roles=("reviewer",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"talent"}), "org", "closed-loop")


def set_identity(app, uid, roles):
    app.dependency_overrides[get_review_identity] = lambda: identity(uid, roles)


@pytest.fixture
def loop_env(monkeypatch):
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
    monkeypatch.setenv("REVIEW_RERUN_MODE", "remote")
    monkeypatch.setenv("GRAPH_BUILD_INTERNAL_URL", "http://graph-build.test")
    monkeypatch.setenv("REVIEW_RESUME_MAX_ATTEMPTS", "5")
    app.dependency_overrides[get_review_identity] = identity
    yield app, service
    app.dependency_overrides.pop(get_review_identity, None)


def review_required_body(step, template, *, event_id, scope="OBJECT", severity="P1", obj_id=None):
    return {
        "eventId": event_id,
        "occurredAt": datetime.now(UTC).isoformat(),
        "sourceTaskId": f"TASK-{step}",
        "batchId": "BATCH-1",
        "stepId": step,
        "workflow": {
            "workflowType": "GraphBuildWorkflow",
            "workflowId": f"wf-{step}",
            "runId": "run-1",
            "taskQueue": "graph-build",
            "resumeToken": f"opaque-{step}",
        },
        "object": {"id": obj_id or f"OBJ-{step}", "type": "Candidate", "name": f"脱敏对象-{step}"},
        "exception": {
            "code": f"{step.upper()}_REVIEW_REQUIRED",
            "message": f"{step} 需要人工处理",
            "fingerprint": f"fp-{step}-{template}",
            "severity": severity,
            "scope": scope,
        },
        "templateId": template,
        "templateVersion": "1.0",
        "domain": "talent",
        "inputSnapshot": {"raw": "真实脱敏输入"},
        "candidateSnapshot": {"existingCandidates": [{"id": "E-1"}]},
        "evidence": [],
        "ruleVersion": f"{step}-v1",
    }


class _Resp:
    """最小化 httpx.Response 替身，供伪图谱构建客户端返回。"""

    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("graph-build error", request=None, response=self)

    def json(self) -> dict[str, Any]:
        return self._payload

    def get(self, _key, default=None):  # 兼容 .get("accepted")
        return self._payload.get(_key, default)


class FakeGraphBuild:
    """伪图谱构建服务：实现 handoff §5/§6/§7 的恢复与回调契约。

    - 接收 POST /internal/review-resumes，幂等键为 correctionId（§6）
    - 回拉 GET /correction，按 canonical JSON 计算 SHA-256 并常量时间比对（§5）
    - 校验 stepId/scope 与 resume 请求一致
    - 失败重试时返回新的 executionId（§7），纯重投返回同一 executionId（§6）
    """

    def __init__(self, review_client_factory, token):
        self._review_client_factory = review_client_factory
        self._token = token
        self.executions: dict[str, str] = {}  # correctionId -> 当前 executionId
        self.failed: set[str] = set()  # 已失败的 correctionId（下次重试给新 executionId）
        self.resume_requests: list[dict] = []
        self.corrections_pulled: list[dict] = []
        self.sha_mismatches = 0
        self._seq = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, json=None, headers=None, timeout=None):
        body = json
        cid = body["correctionId"]
        self.resume_requests.append(body)
        # handoff §6：Idempotency-Key 必须等于 correctionId
        assert headers["Idempotency-Key"] == cid
        # 回拉 correction（L4：图谱构建→人工处理）
        async with self._review_client_factory() as c:
            r = await c.get(
                f"/api/v1/internal/manual-reviews/{body['reviewId']}/correction",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            assert r.status_code == 200, r.text
            corr = r.json()["data"]
        self.corrections_pulled.append(corr)
        # handoff §5：canonical JSON + SHA-256 常量时间比对
        canonical = json_dumps(
            corr["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        if not hmac.compare_digest(hashlib.sha256(canonical).hexdigest(), corr["payloadSha256"]):
            self.sha_mismatches += 1
            return _Resp(200, {"accepted": False, "error": "payload sha256 mismatch"})
        # 校验恢复位置与隔离范围与 resume 请求一致
        assert corr["stepId"] == body["stepId"], "correction stepId 与 resume 不一致"
        assert corr["scope"] == body["scope"], "correction scope 与 resume 不一致"
        # 幂等：同 correctionId 且未失败过 → 同一 executionId（§6）；失败后重试 → 新 executionId（§7）
        if cid in self.executions and cid not in self.failed:
            return _Resp(
                200,
                {
                    "accepted": True,
                    "executionId": self.executions[cid],
                    "workflowId": body["workflow"]["workflowId"],
                    "runId": "run-2",
                    "status": "QUEUED",
                },
            )
        self.failed.discard(cid)
        self._seq += 1
        exec_id = f"GRAPH-RERUN-{self._seq:04d}"
        self.executions[cid] = exec_id
        return _Resp(
            200,
            {
                "accepted": True,
                "executionId": exec_id,
                "workflowId": body["workflow"]["workflowId"],
                "runId": "run-2",
                "status": "QUEUED",
            },
        )


def install_fake_graph_build(loop_env, monkeypatch):
    app, service = loop_env

    def review_client_factory():
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    fake = FakeGraphBuild(review_client_factory, SERVICE_TOKEN)
    service.http_client_factory = lambda: fake
    return fake


async def _post_review(async_client, body):
    return await async_client.post(
        "/api/v1/internal/manual-reviews/review-required",
        json=body,
        headers={**HEADERS, "Idempotency-Key": body["eventId"]},
    )


async def _claim_submit(async_client, rid, version, action, result):
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{rid}/claim", json={"version": version}
        )
    ).json()["data"]
    return (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{rid}/submit",
            json={
                "version": claimed["version"],
                "actionId": action,
                "result": result,
                "note": "已核验",
            },
        )
    ).json()["data"]


async def _fire_event(async_client, rid, exec_id, event_id, etype, *, error=None, step="align"):
    return (
        await async_client.post(
            f"/api/v1/internal/manual-reviews/{rid}/execution-events",
            json={
                "eventId": event_id,
                "executionId": exec_id,
                "type": etype,
                "occurredAt": datetime.now(UTC).isoformat(),
                "stepId": step,
                "workflowId": "wf-align",
                "runId": "run-2",
                "result": {},
                "error": error,
                "metrics": {},
            },
            headers={**HEADERS, "Idempotency-Key": event_id},
        )
    ).json()["data"]


# --------------------------------------------------------------------------- #
# 1. 完整闭环：成功路径 + 重复投递幂等 + 重复回调幂等
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_full_closed_loop_success(async_client, loop_env, monkeypatch):
    app, service = loop_env
    fake = install_fake_graph_build(loop_env, monkeypatch)

    # L1：图谱构建上报异常
    body = review_required_body("align", "T_LINK", event_id="evt-loop-1")
    created = (await _post_review(async_client, body)).json()["data"]
    rid = created["reviewId"]
    assert created["status"] == "OPEN"
    assert created["isolationStrategy"] == "ISOLATE_OBJECT"

    # L2：人工处理领取 + 裁决（P1 无需双人审批）→ APPLYING + correction + outbox
    submitted = await _claim_submit(
        async_client, rid, 1, "entity-confirm", {"entityVerdict": "create"}
    )
    assert submitted["status"] == "APPLYING"

    # L3：Outbox 投递 → 伪图谱构建收到 resume
    assert (await service.process_outbox()) == {"processed": 1, "failed": 0}
    assert len(fake.resume_requests) == 1
    resume = fake.resume_requests[0]
    assert resume["stepId"] == "align"
    assert resume["scope"] == "OBJECT"
    assert resume["correctionUrl"].endswith(f"/api/v1/internal/manual-reviews/{rid}/correction")

    # L4：伪图谱构建已回拉 correction 并通过 SHA-256 校验
    assert len(fake.corrections_pulled) == 1
    assert fake.sha_mismatches == 0
    corr = fake.corrections_pulled[0]
    assert corr["stepId"] == "align"
    assert corr["payloadSha256"]
    assert len(corr["payloadSha256"]) == 64
    exec_id = fake.executions[resume["correctionId"]]
    detail = (await async_client.get(f"/api/v1/manual-reviews/production/{rid}")).json()["data"]
    assert detail["status"] == "RERUNNING"
    assert detail["executions"][0]["id"] == exec_id

    # 重复投递同一 resume（§6）→ 同一 executionId，不重复启动工作流
    with service.sf() as s:
        c = service.need(s, rid)
        cor = s.scalar(select(ReviewCorrection).where(ReviewCorrection.case_id == rid))
    r1 = await service.dispatch_resume(c, cor)
    r2 = await service.dispatch_resume(c, cor)
    assert r1["executionId"] == r2["executionId"] == exec_id
    assert len(fake.resume_requests) == 3  # 两次显式重投
    assert len(fake.executions) == 1  # 仍只有一个 execution

    # L5：图谱构建驱动回调（L6：仅 VERIFICATION_SUCCEEDED 关闭）
    assert (await _fire_event(async_client, rid, exec_id, "cb-1", "CORRECTION_ACCEPTED"))[
        "status"
    ] == "RERUNNING"
    assert (await _fire_event(async_client, rid, exec_id, "cb-2", "RERUN_STARTED"))[
        "status"
    ] == "RERUNNING"
    assert (await _fire_event(async_client, rid, exec_id, "cb-3", "RERUN_SUCCEEDED"))[
        "status"
    ] == "VERIFYING"
    resolved = (await _fire_event(async_client, rid, exec_id, "cb-4", "VERIFICATION_SUCCEEDED"))[
        "status"
    ]
    assert resolved == "RESOLVED"

    # 重复回调幂等
    replay = await _fire_event(async_client, rid, exec_id, "cb-4", "VERIFICATION_SUCCEEDED")
    assert replay["duplicate"] is True
    assert replay["status"] == "RESOLVED"
    # correction 落为 APPLIED
    with service.sf() as s:
        cor = s.scalar(select(ReviewCorrection).where(ReviewCorrection.case_id == rid))
        assert cor.status == "APPLIED"
        assert cor.applied_at is not None


# --------------------------------------------------------------------------- #
# 2. 拒绝分支：闭环在人工处理侧短路，图谱构建从未被调用
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_closed_loop_reject_short_circuits(async_client, loop_env, monkeypatch):
    app, service = loop_env
    fake = install_fake_graph_build(loop_env, monkeypatch)

    body = review_required_body(
        "schema", "T_MAP", event_id="evt-loop-reject", scope="BATCH", severity="P0"
    )
    created = (await _post_review(async_client, body)).json()["data"]
    rid = created["reviewId"]
    submitted = await _claim_submit(
        async_client, rid, 1, "save-map-rerun", {"mappings": [{"source": "a", "target": "b"}]}
    )
    assert submitted["status"] == "PENDING_APPROVAL"
    # 审批前图谱构建不应被调用
    assert (await service.process_outbox()) == {"processed": 0, "failed": 0}
    assert fake.resume_requests == []

    # 第二审批人拒绝 → REJECTED，仍不投递 resume
    set_identity(app, "approver-2", ("approver",))
    rejected = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{rid}/reject",
            json={"version": submitted["version"], "note": "拒绝"},
        )
    ).json()["data"]
    assert rejected["status"] == "REJECTED"
    assert (await service.process_outbox()) == {"processed": 0, "failed": 0}
    assert fake.resume_requests == []  # 闭环在人工处理侧终止，图谱构建零调用


# --------------------------------------------------------------------------- #
# 3. 重跑失败 → 重试 → 伪图谱构建返回新 executionId → 再次闭环成功
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_closed_loop_rerun_failed_then_retry_re_runs(async_client, loop_env, monkeypatch):
    app, service = loop_env
    fake = install_fake_graph_build(loop_env, monkeypatch)

    body = review_required_body("align", "T_LINK", event_id="evt-loop-retry")
    created = (await _post_review(async_client, body)).json()["data"]
    rid = created["reviewId"]
    await _claim_submit(async_client, rid, 1, "entity-confirm", {"entityVerdict": "create"})
    await service.process_outbox()
    first_exec = fake.executions[fake.resume_requests[0]["correctionId"]]

    # 重跑失败
    assert (await _fire_event(async_client, rid, first_exec, "f-1", "RERUN_FAILED", error="boom"))[
        "status"
    ] == "RERUN_FAILED"
    fake.failed.add(fake.resume_requests[0]["correctionId"])  # 标记失败，重试应给新 executionId

    # 人工点击重试（同一 correction）
    latest = (await async_client.get(f"/api/v1/manual-reviews/production/{rid}")).json()["data"]
    set_identity(app, "admin", ("review_admin",))
    retried = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{rid}/retry", json={"version": latest["version"]}
        )
    ).json()["data"]
    assert retried["status"] == "APPLYING"
    await service.process_outbox()
    # §7：失败后重试 → 新 executionId，独立事件序列
    second_exec = fake.executions[fake.resume_requests[-1]["correctionId"]]
    assert second_exec != first_exec

    # 新 execution 走完整回调闭环 → RESOLVED
    await _fire_event(async_client, rid, second_exec, "f-2", "RERUN_SUCCEEDED")
    assert (await _fire_event(async_client, rid, second_exec, "f-3", "VERIFICATION_SUCCEEDED"))[
        "status"
    ] == "RESOLVED"
    # 旧 execution 的事件不会因新 execution 倒退
    assert len(fake.executions) == 1  # 同一 correctionId 复用键，但值已更新为新 executionId


# --------------------------------------------------------------------------- #
# 4. Correction 被篡改：伪图谱构建 SHA-256 校验失败 → 拒绝恢复 → APPLY_FAILED
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_closed_loop_tampered_correction_rejected(async_client, loop_env, monkeypatch):
    app, service = loop_env
    monkeypatch.setenv("REVIEW_RESUME_MAX_ATTEMPTS", "1")
    fake = install_fake_graph_build(loop_env, monkeypatch)

    body = review_required_body("align", "T_LINK", event_id="evt-loop-tamper")
    created = (await _post_review(async_client, body)).json()["data"]
    rid = created["reviewId"]
    await _claim_submit(async_client, rid, 1, "entity-confirm", {"entityVerdict": "create"})

    # 篡改 correction 的 payload_sha256（模拟传输/存储中被改动）
    with service.sf() as s:
        cor = s.scalar(select(ReviewCorrection).where(ReviewCorrection.case_id == rid))
        cor.payload_sha256 = "0" * 64
        s.commit()

    # 图谱构建回拉后 SHA 校验失败 → 接收失败 → 闭环中断于 APPLY_FAILED
    await service.process_outbox()
    assert fake.sha_mismatches >= 1
    assert fake.executions == {}  # 未启动任何重跑
    detail = (await async_client.get(f"/api/v1/manual-reviews/production/{rid}")).json()["data"]
    assert detail["status"] == "APPLY_FAILED"
