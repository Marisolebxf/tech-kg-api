"""Production manual-review service and graph-build handoff boundary."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from db_model.manual_review import (
    ReviewAuditLog,
    ReviewCase,
    ReviewCorrection,
    ReviewDecision,
    ReviewDraft,
    ReviewEvidence,
    ReviewExecution,
    ReviewExecutionEvent,
    ReviewOutbox,
)
from infra.mysql import get_session_factory
from infra.s3 import S3Storage
from service.manual_review_domain import (
    EDITABLE_STATUSES,
    EVENT_STAGE,
    PIPELINE_STEPS,
    TEMPLATES,
    TERMINAL_STATUSES,
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
    canonical_template,
    choose_template,
    require_domain_access,
    require_role,
    requires_approval,
    rerun_step,
    risk_policy,
    role_can_review,
    template_contract,
    validate_action,
    validate_step_template,
    write_target,
)


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def load(v):
    return json.loads(v) if v else None


def sha(v):
    return hashlib.sha256(dump(v).encode()).hexdigest()


class ManualReviewService:
    def __init__(self, session_factory=None, http_client_factory=None):
        self.sf = session_factory or get_session_factory()
        self.http_client_factory = http_client_factory or (lambda: httpx.AsyncClient())

    def _legacy_step(self, p):
        n = str(p.get("stepId") or p.get("nodeId") or "").lower()
        phase = p.get("phase")
        for x in PIPELINE_STEPS:
            if x in n:
                return x
        if phase == "数据处理":
            return "normalize"
        return "validate"

    def create_case(self, p, a):
        step = self._legacy_step(p)
        tpl = canonical_template(
            p.get("templateId")
            or choose_template(
                p.get("errorType", ""), p.get("nodeId", step), p.get("objectType", "")
            )
        )
        legacy_batch = p.get("scopeHint") == "batch" or (
            step == "schema" and "映射失败" in p.get("errorType", "")
        )
        p = {
            **p,
            "stepId": step,
            "templateId": tpl,
            "eventId": p.get("eventId") or f"legacy-{uuid4().hex}",
            "occurredAt": now(),
            "workflow": p.get("workflow")
            or {
                "workflowType": "legacy",
                "workflowId": p.get("sourceTaskId", "legacy"),
                "runId": None,
                "taskQueue": "legacy",
                "resumeToken": f"legacy:{p.get('sourceTaskId', 'unknown')}",
            },
            "object": {
                "id": p.get("objectId", ""),
                "type": p.get("objectType", ""),
                "name": p.get("objectName", ""),
            },
            "exception": {
                "code": p.get("exceptionCode", "LEGACY_REVIEW_REQUIRED"),
                "message": p.get("diagnosis") or p.get("errorType", "人工审核"),
                "fingerprint": p.get("errorFingerprint")
                or sha([p.get("errorType"), p.get("candidate")]),
                "severity": p.get("riskLevel") or ("P0" if legacy_batch else "P1"),
                "scope": "BATCH" if legacy_batch else "OBJECT",
            },
            "inputSnapshot": p.get("input", {}),
            "candidateSnapshot": p.get("candidate", {}),
            "evidence": p.get("evidence", []),
        }
        ingress = self.create_review_required(p, a.user_id)
        detail = self.get_case(ingress["reviewId"], a)
        detail["duplicate"] = ingress["duplicate"]
        return detail

    def create_review_required(self, p, service_actor="graph-build"):
        step = p["stepId"]
        tpl = validate_step_template(step, p["templateId"])
        ex = p["exception"]
        obj = p["object"]
        wf = p["workflow"]
        if ex["scope"] == "BATCH" and ex["severity"] != "P0":
            raise ReviewValidationError("BATCH 异常必须为 P0")
        snapshot_size = len(
            dump(
                {
                    "input": p.get("inputSnapshot", {}),
                    "candidate": p.get("candidateSnapshot", {}),
                    "evidence": p.get("evidence", []),
                }
            ).encode()
        )
        if snapshot_size > int(os.getenv("REVIEW_SNAPSHOT_MAX_BYTES", "2097152")):
            raise ReviewValidationError("异常快照超过大小限制，请改用证据附件")
        dk = sha([p["sourceTaskId"], step, obj["id"], ex["fingerprint"]])
        risk, scope, claim, resolve = risk_policy(ex["message"], ex["scope"], ex["severity"])
        t = now()
        c = ReviewCase(
            id=f"MR-{t:%Y%m%d}-{uuid4().hex[:12].upper()}",
            dedupe_key=dk,
            event_id=p["eventId"],
            source_task_id=p["sourceTaskId"],
            batch_id=p.get("batchId"),
            node_id=step,
            pipeline_step_id=step,
            object_id=obj["id"],
            object_type=obj["type"],
            object_name=obj["name"],
            error_type=ex["message"],
            error_fingerprint=ex["fingerprint"],
            category=TEMPLATES[tpl]["title"],
            template_id=tpl,
            template_version=p.get("templateVersion", "1.0"),
            domain=p.get("domain", "graph"),
            phase=PIPELINE_STEPS[step]["phase"],
            risk_level=risk,
            scope=scope,
            status="OPEN",
            version=1,
            sla_claim_at=claim,
            sla_resolve_at=resolve,
            source_table=p.get("sourceTable"),
            source_record_id=p.get("sourceRecordId"),
            rule_version=p.get("ruleVersion"),
            model_version=p.get("modelVersion"),
            workflow_type=wf["workflowType"],
            workflow_id=wf["workflowId"],
            workflow_run_id=wf.get("runId"),
            task_queue=wf["taskQueue"],
            resume_token=wf["resumeToken"],
            exception_code=ex["code"],
            isolation_scope=ex["scope"],
            template_payload_version=p.get("templateVersion", "1.0"),
            input_snapshot=dump(p.get("inputSnapshot", {})),
            candidate_snapshot=dump(
                {**p.get("candidateSnapshot", {}), "reportedEvidence": p.get("evidence", [])}
            ),
            diagnosis=ex["message"],
            created_at=t,
            updated_at=t,
        )
        actor = ReviewIdentity(
            service_actor,
            service_actor,
            frozenset({"review_admin"}),
            frozenset({"*"}),
            "service",
            p["eventId"],
        )
        with self.sf() as s:
            existing = s.scalar(
                select(ReviewCase).where(
                    or_(ReviewCase.event_id == p["eventId"], ReviewCase.dedupe_key == dk)
                )
            )
            if existing:
                return self._ingress_response(existing, True)
            try:
                s.add(c)
                self.audit(
                    s,
                    c,
                    actor,
                    "CASE_CREATED",
                    None,
                    "OPEN",
                    {"stepId": step, "exceptionCode": ex["code"]},
                )
                s.commit()
            except IntegrityError:
                s.rollback()
                c = s.scalar(
                    select(ReviewCase).where(
                        or_(ReviewCase.event_id == p["eventId"], ReviewCase.dedupe_key == dk)
                    )
                )
                if not c:
                    raise
                return self._ingress_response(c, True)
            return self._ingress_response(c, False)

    def _ingress_response(self, c, duplicate):
        return {
            "reviewId": c.id,
            "status": c.status,
            "riskLevel": c.risk_level,
            "isolationStrategy": "BLOCK_BATCH_AND_DOWNSTREAM"
            if c.isolation_scope == "BATCH"
            else "ISOLATE_OBJECT",
            "duplicate": duplicate,
        }

    def list_cases(self, f, a):
        require_role(
            a,
            "reviewer",
            "data_quality_reviewer",
            "graph_governance_reviewer",
            "approver",
            "auditor",
        )
        page = max(int(f.get("page") or 1), 1)
        size = min(max(int(f.get("page_size") or 50), 1), 200)
        q = []
        for k, col in (
            ("status", ReviewCase.status),
            ("risk", ReviewCase.risk_level),
            ("domain", ReviewCase.domain),
            ("template_id", ReviewCase.template_id),
            ("assignee_id", ReviewCase.assignee_id),
        ):
            if f.get(k):
                q.append(col == f[k])
        queues = {
            "mine": ReviewCase.assignee_id == a.user_id,
            "unclaimed": ReviewCase.status == "OPEN",
            "approval": ReviewCase.status == "PENDING_APPROVAL",
            "failed": ReviewCase.status.in_(("APPLY_FAILED", "RERUN_FAILED")),
            "history": ReviewCase.status.in_(TERMINAL_STATUSES),
        }
        if f.get("queue") in queues:
            q.append(queues[f["queue"]])
        if a.domains and "*" not in a.domains and not a.has_any("review_admin", "auditor"):
            q.append(ReviewCase.domain.in_(a.domains))
        if f.get("keyword"):
            x = f"%{f['keyword']}%"
            q.append(
                or_(
                    ReviewCase.id.like(x),
                    ReviewCase.object_name.like(x),
                    ReviewCase.source_record_id.like(x),
                )
            )
        with self.sf() as s:
            total = s.scalar(select(func.count()).select_from(ReviewCase).where(*q)) or 0
            rows = s.scalars(
                select(ReviewCase)
                .where(*q)
                .order_by(ReviewCase.risk_level, ReviewCase.created_at)
                .offset((page - 1) * size)
                .limit(size)
            ).all()
            return {
                "items": [self.case_dict(x) for x in rows],
                "total": total,
                "page": page,
                "pageSize": size,
            }

    def get_case(self, i, a):
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            return self.detail(s, c)

    def claim(self, i, v, a):
        t = now()
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            if not role_can_review(a, c.phase):
                raise ReviewForbiddenError("角色与任务阶段不匹配")
            r = s.execute(
                update(ReviewCase)
                .where(ReviewCase.id == i, ReviewCase.version == v, ReviewCase.status == "OPEN")
                .values(
                    status="CLAIMED",
                    assignee_id=a.user_id,
                    assignee_name=a.user_name,
                    claimed_at=t,
                    heartbeat_at=t,
                    updated_at=t,
                    version=ReviewCase.version + 1,
                )
            )
            if r.rowcount != 1:
                raise ReviewConflictError("任务已被领取或版本冲突")
            self.audit(s, c, a, "CASE_CLAIMED", "OPEN", "CLAIMED", {})
            s.commit()
        return self.get_case(i, a)

    def mutate(self, i, v, a, values, event, admin=False):
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            if not admin and c.assignee_id != a.user_id:
                raise ReviewForbiddenError("任务不属于当前用户")
            if c.version != v:
                raise ReviewConflictError("版本冲突")
            old = c.status
            for k, x in values.items():
                setattr(c, k, x)
            c.version += 1
            c.updated_at = now()
            self.audit(s, c, a, event, old, c.status, {})
            s.commit()
            return self.detail(s, c)

    def heartbeat(self, i, v, a):
        return self.mutate(i, v, a, {"heartbeat_at": now()}, "HEARTBEAT")

    def release(self, i, v, a):
        return self.mutate(
            i,
            v,
            a,
            {
                "status": "OPEN",
                "assignee_id": None,
                "assignee_name": None,
                "claimed_at": None,
                "heartbeat_at": None,
            },
            "CASE_RELEASED",
        )

    def transfer(self, i, v, uid, name, a):
        require_role(a, "review_admin")
        return self.mutate(
            i,
            v,
            a,
            {"assignee_id": uid, "assignee_name": name, "heartbeat_at": now()},
            "CASE_TRANSFERRED",
            True,
        )

    def draft(self, i, v, p, a):
        with self.sf() as s:
            c = self.owned(s, i, a)
            if c.version != v or c.status not in EDITABLE_STATUSES:
                raise ReviewConflictError("状态或版本冲突")
            s.merge(ReviewDraft(case_id=i, payload=dump(p), updated_by=a.user_id, updated_at=now()))
            old = c.status
            c.status = "IN_REVIEW"
            c.version += 1
            c.updated_at = now()
            self.audit(s, c, a, "DRAFT_SAVED", old, c.status, {})
            s.commit()
            return self.detail(s, c)

    def submit(self, i, v, action, result, note, a):
        with self.sf() as s:
            c = self.owned(s, i, a)
            if c.version != v or c.status not in EDITABLE_STATUSES:
                raise ReviewConflictError("状态或版本冲突")
            validate_action(c.template_id, action, result)
            approval = requires_approval(c.risk_level, action, result)
            t = now()
            d = ReviewDecision(
                case_id=i,
                action_id=action,
                result=dump(result),
                note=note,
                submitted_by=a.user_id,
                status="PENDING_APPROVAL" if approval else "APPROVED",
                created_at=t,
                decided_at=None if approval else t,
            )
            s.add(d)
            s.flush()
            old = c.status
            c.submitted_by = a.user_id
            if approval:
                c.status = "PENDING_APPROVAL"
            else:
                self.enqueue_correction(s, c, d, result)
                c.status = "APPLYING"
            c.version += 1
            c.updated_at = t
            self.audit(s, c, a, "DECISION_SUBMITTED", old, c.status, {"actionId": action})
            s.commit()
            return self.detail(s, c)

    def approve(self, i, v, ok, note, a):
        require_role(a, "approver")
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            if c.version != v or c.status != "PENDING_APPROVAL":
                raise ReviewConflictError("状态或版本冲突")
            d = s.scalar(
                select(ReviewDecision)
                .where(ReviewDecision.case_id == i, ReviewDecision.status == "PENDING_APPROVAL")
                .order_by(ReviewDecision.id.desc())
            )
            if not d:
                raise ReviewConflictError("待审批裁决不存在")
            if d.submitted_by == a.user_id:
                raise ReviewForbiddenError("提交人与批准人必须不同")
            old = c.status
            d.approved_by = a.user_id
            d.note = (d.note + "\n审批意见: " + note).strip()
            d.decided_at = now()
            if ok:
                d.status = "APPROVED"
                self.enqueue_correction(s, c, d, load(d.result))
                c.status = "APPLYING"
            else:
                d.status = "REJECTED"
                c.status = "REJECTED"
                c.completed_at = now()
            c.version += 1
            c.updated_at = now()
            self.audit(
                s, c, a, "DECISION_APPROVED" if ok else "DECISION_REJECTED", old, c.status, {}
            )
            s.commit()
            return self.detail(s, c)

    def enqueue_correction(self, s, c, d, result):
        payload = {"decisionId": d.id, "result": result}
        digest = sha(payload)
        step = rerun_step(c.pipeline_step_id, d.action_id)
        x = ReviewCorrection(
            id=f"COR-{uuid4().hex[:16].upper()}",
            case_id=c.id,
            adapter=TEMPLATES[canonical_template(c.template_id)]["adapter"],
            payload=dump(payload),
            correction_version=1,
            payload_sha256=digest,
            rerun_step_id=step,
            status="PENDING",
            attempts=0,
            created_at=now(),
        )
        s.add(x)
        self.outbox(s, c.id, "RESUME_REQUESTED", {"correctionId": x.id})

    def correction(self, i):
        with self.sf() as s:
            c = self.need(s, i)
            x = s.scalar(
                select(ReviewCorrection)
                .where(ReviewCorrection.case_id == i)
                .order_by(ReviewCorrection.created_at.desc())
            )
            if not x:
                raise KeyError(i)
            d = s.scalar(
                select(ReviewDecision)
                .where(ReviewDecision.case_id == i, ReviewDecision.status == "APPROVED")
                .order_by(ReviewDecision.id.desc())
            )
            ev = s.scalars(select(ReviewEvidence).where(ReviewEvidence.case_id == i)).all()
            return {
                "reviewId": i,
                "correctionId": x.id,
                "correctionVersion": x.correction_version,
                "templateId": canonical_template(c.template_id),
                "actionId": d.action_id if d else None,
                "stepId": x.rerun_step_id,
                "scope": c.isolation_scope,
                "payload": load(x.payload),
                "evidenceRefs": [{"id": e.id, "sha256": e.sha256} for e in ev],
                "ruleSedimentation": bool((load(d.result) if d else {}).get("sedimentRule")),
                "submittedBy": d.submitted_by if d else None,
                "approvedBy": d.approved_by if d else None,
                "payloadSha256": x.payload_sha256,
            }

    async def process_outbox(self, limit=20):
        done = failed = 0
        stale_before = now() - timedelta(
            seconds=int(os.getenv("REVIEW_OUTBOX_LOCK_TIMEOUT_SECONDS", "60"))
        )
        with self.sf() as s:
            s.execute(
                update(ReviewOutbox)
                .where(ReviewOutbox.status == "PROCESSING", ReviewOutbox.locked_at < stale_before)
                .values(status="RETRY", available_at=now(), locked_at=None)
            )
            s.commit()
            ids = [
                x.id
                for x in s.scalars(
                    select(ReviewOutbox)
                    .where(
                        ReviewOutbox.status.in_(("PENDING", "RETRY")),
                        ReviewOutbox.available_at <= now(),
                    )
                    .order_by(ReviewOutbox.created_at)
                    .limit(limit)
                ).all()
            ]
        for oid in ids:
            with self.sf() as claim_session:
                claimed = claim_session.execute(
                    update(ReviewOutbox)
                    .where(
                        ReviewOutbox.id == oid,
                        ReviewOutbox.status.in_(("PENDING", "RETRY")),
                        ReviewOutbox.available_at <= now(),
                    )
                    .values(status="PROCESSING", locked_at=now())
                )
                claim_session.commit()
                if claimed.rowcount != 1:
                    continue
            with self.sf() as s:
                x = s.get(ReviewOutbox, oid)
                if not x or x.status != "PROCESSING":
                    continue
                if x.event_type != "RESUME_REQUESTED":
                    x.status = "DONE"
                    x.processed_at = now()
                    s.commit()
                    done += 1
                    continue
                c = self.need(s, x.case_id)
                cor = s.scalar(
                    select(ReviewCorrection).where(
                        ReviewCorrection.id == load(x.payload)["correctionId"]
                    )
                )
                try:
                    response = await self.dispatch_resume(c, cor)
                    execution_id = response["executionId"]
                    existing = s.get(ReviewExecution, execution_id)
                    if existing and existing.case_id != c.id:
                        raise RuntimeError("图谱构建返回了已属于其他审核单的 executionId")
                    if not existing:
                        s.add(
                            ReviewExecution(
                                id=execution_id,
                                case_id=c.id,
                                resume_node=cor.rerun_step_id,
                                workflow_type=c.workflow_type or "graph-build",
                                workflow_id=response.get("workflowId") or c.workflow_id or "",
                                run_id=response.get("runId"),
                                status=response.get("status", "QUEUED"),
                                created_at=now(),
                            )
                        )
                    old_status = c.status
                    cor.status = "DISPATCHED"
                    c.status = "RERUNNING"
                    c.version += 1
                    c.updated_at = now()
                    x.status = "DONE"
                    x.processed_at = now()
                    self.audit(
                        s,
                        c,
                        ReviewIdentity(
                            "outbox-worker",
                            "Outbox Worker",
                            frozenset({"review_admin"}),
                            frozenset({"*"}),
                            "system",
                            oid,
                        ),
                        "RESUME_ACCEPTED",
                        old_status,
                        "RERUNNING",
                        {"executionId": execution_id},
                    )
                    s.commit()
                    done += 1
                except Exception as exc:
                    s.rollback()
                    x = s.get(ReviewOutbox, oid)
                    c = self.need(s, x.case_id)
                    cor = s.scalar(
                        select(ReviewCorrection).where(
                            ReviewCorrection.id == load(x.payload)["correctionId"]
                        )
                    )
                    x.attempts += 1
                    x.last_error = str(exc)
                    x.status = (
                        "DEAD"
                        if x.attempts >= int(os.getenv("REVIEW_RESUME_MAX_ATTEMPTS", "5"))
                        else "RETRY"
                    )
                    x.available_at = now() + timedelta(seconds=min(300, 2**x.attempts))
                    c.status = "APPLY_FAILED"
                    c.version += 1
                    c.updated_at = now()
                    cor.status = "PENDING"
                    cor.last_error = str(exc)
                    cor.attempts += 1
                    s.commit()
                    failed += 1
        return {"processed": done, "failed": failed}

    async def dispatch_resume(self, c, cor):
        payload = {
            "reviewId": c.id,
            "correctionId": cor.id,
            "correctionVersion": cor.correction_version,
            "stepId": cor.rerun_step_id,
            "scope": c.isolation_scope,
            "sourceTaskId": c.source_task_id,
            "batchId": c.batch_id,
            "workflow": {
                "workflowType": c.workflow_type,
                "workflowId": c.workflow_id,
                "runId": c.workflow_run_id,
                "taskQueue": c.task_queue,
                "resumeToken": c.resume_token,
            },
            "correctionUrl": f"/api/v1/internal/manual-reviews/{c.id}/correction",
        }
        if os.getenv("REVIEW_RERUN_MODE", "mock") == "mock":
            return {
                "accepted": True,
                "executionId": f"MOCK-{cor.id}",
                "workflowId": c.workflow_id or f"mock-{c.id}",
                "runId": "mock",
                "status": "QUEUED",
            }
        base = os.getenv("GRAPH_BUILD_INTERNAL_URL", "").rstrip("/")
        if not base:
            raise RuntimeError("GRAPH_BUILD_INTERNAL_URL 未配置")
        headers = {
            "Authorization": f"Bearer {os.getenv('GRAPH_BUILD_SERVICE_TOKEN', '')}",
            "Idempotency-Key": cor.id,
        }
        async with self.http_client_factory() as client:
            r = await client.post(
                base + "/internal/review-resumes",
                json=payload,
                headers=headers,
                timeout=float(os.getenv("REVIEW_RESUME_TIMEOUT_SECONDS", "10")),
            )
            r.raise_for_status()
            data = r.json()
        if not data.get("accepted") or not data.get("executionId"):
            raise RuntimeError("图谱构建拒绝或返回无效恢复响应")
        return data

    def execution_event(self, i, p):
        stage = EVENT_STAGE[p["type"]]
        occurred = p["occurredAt"]
        occurred = occurred.replace(tzinfo=None) if hasattr(occurred, "replace") else now()
        with self.sf() as s:
            c = self.need(s, i)
            # 允许回调 stepId == 审核单原节点（同节点重跑）；唯一例外是 validate +
            # reject-extract 回退到 extract。其余跨节点回调一律拒绝。
            step_ok = p["stepId"] == c.pipeline_step_id or (
                p["stepId"] == "extract" and c.pipeline_step_id == "validate"
            )
            if not step_ok:
                raise ReviewValidationError("回调 stepId 与审核单不匹配")
            if s.get(ReviewExecutionEvent, p["eventId"]):
                return {"reviewId": i, "status": c.status, "duplicate": True}
            previous = (
                s.scalar(
                    select(func.max(ReviewExecutionEvent.stage)).where(
                        ReviewExecutionEvent.case_id == i,
                        ReviewExecutionEvent.execution_id == p["executionId"],
                    )
                )
                or 0
            )
            if stage < previous:
                raise ReviewConflictError("执行事件乱序，禁止状态回退")
            typ = p["type"]
            allowed = {
                "CORRECTION_ACCEPTED": {"APPLYING", "RERUNNING"},
                "RERUN_STARTED": {"APPLYING", "RERUNNING"},
                "RERUN_PROGRESS": {"RERUNNING"},
                "RERUN_SUCCEEDED": {"RERUNNING"},
                "RERUN_FAILED": {"RERUNNING"},
                "VERIFICATION_SUCCEEDED": {"VERIFYING"},
                "VERIFICATION_FAILED": {"VERIFYING"},
            }
            if c.status not in allowed[typ]:
                raise ReviewConflictError(f"状态 {c.status} 不接受事件 {typ}")
            x = s.get(ReviewExecution, p["executionId"])
            if x and x.case_id != i:
                raise ReviewValidationError("executionId 已属于其他审核单")
            if not x:
                x = ReviewExecution(
                    id=p["executionId"],
                    case_id=i,
                    resume_node=p["stepId"],
                    workflow_type=c.workflow_type or "graph-build",
                    workflow_id=p.get("workflowId") or c.workflow_id or "",
                    run_id=p.get("runId"),
                    status="QUEUED",
                    created_at=now(),
                )
                s.add(x)
            old = c.status
            if typ in ("CORRECTION_ACCEPTED", "RERUN_STARTED", "RERUN_PROGRESS"):
                c.status = "RERUNNING"
                x.status = "RUNNING"
            elif typ == "RERUN_SUCCEEDED":
                c.status = "VERIFYING"
                x.status = "RERUN_SUCCEEDED"
            elif typ in ("RERUN_FAILED", "VERIFICATION_FAILED"):
                c.status = "RERUN_FAILED"
                x.status = "FAILED"
                x.error = p.get("error")
                x.completed_at = now()
            elif typ == "VERIFICATION_SUCCEEDED":
                c.status = "RESOLVED"
                c.completed_at = now()
                x.status = "COMPLETED"
                x.completed_at = now()
                cor = s.scalar(
                    select(ReviewCorrection)
                    .where(ReviewCorrection.case_id == i)
                    .order_by(ReviewCorrection.created_at.desc())
                )
                cor.status = "APPLIED"
                cor.applied_at = now()
            s.add(
                ReviewExecutionEvent(
                    event_id=p["eventId"],
                    case_id=i,
                    execution_id=p["executionId"],
                    event_type=typ,
                    stage=stage,
                    payload=dump(p),
                    occurred_at=occurred,
                    created_at=now(),
                )
            )
            c.version += 1
            c.updated_at = now()
            self.audit(
                s,
                c,
                ReviewIdentity(
                    "graph-build",
                    "Graph Build",
                    frozenset({"review_admin"}),
                    frozenset({"*"}),
                    "service",
                    p["eventId"],
                ),
                typ,
                old,
                c.status,
                {"executionId": p["executionId"]},
            )
            s.commit()
            return {"reviewId": i, "status": c.status, "duplicate": False}

    def complete_execution(self, i, eid, success, error, a):
        require_role(a, "review_admin")
        with self.sf() as s:
            c = self.need(s, i)
            step = c.pipeline_step_id
        return self.execution_event(
            i,
            {
                "eventId": f"legacy-{eid}-{uuid4().hex}",
                "executionId": eid,
                "type": "VERIFICATION_SUCCEEDED" if success else "RERUN_FAILED",
                "occurredAt": now(),
                "stepId": step,
                "workflowId": None,
                "runId": None,
                "result": {},
                "error": error,
                "metrics": {},
            },
        )

    def retry(self, i, v, a):
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            if c.version != v or c.status not in ("APPLY_FAILED", "RERUN_FAILED"):
                raise ReviewConflictError("仅失败任务可重试，且版本必须匹配")
            cor = s.scalar(
                select(ReviewCorrection)
                .where(ReviewCorrection.case_id == i)
                .order_by(ReviewCorrection.created_at.desc())
            )
            old = c.status
            cor.status = "PENDING"
            cor.last_error = None
            cor.attempts += 1
            c.status = "APPLYING"
            c.version += 1
            c.updated_at = now()
            self.outbox(s, i, "RESUME_REQUESTED", {"correctionId": cor.id, "retry": True})
            self.audit(s, c, a, "CASE_RETRIED", old, c.status, {})
            s.commit()
            return self.detail(s, c)

    def cancel(self, i, v, reason, a):
        require_role(a, "review_admin")
        return self.mutate(
            i, v, a, {"status": "CANCELLED", "completed_at": now()}, "CASE_CANCELLED", True
        )

    def logs(self, i, a):
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            return [
                {
                    "eventType": x.event_type,
                    "actorId": x.actor_id,
                    "actorName": x.actor_name,
                    "requestId": x.request_id,
                    "oldStatus": x.old_status,
                    "newStatus": x.new_status,
                    "detail": load(x.detail),
                    "createdAt": x.created_at.isoformat(),
                }
                for x in s.scalars(
                    select(ReviewAuditLog)
                    .where(ReviewAuditLog.case_id == i)
                    .order_by(ReviewAuditLog.created_at)
                ).all()
            ]

    def executions(self, i, a):
        return self.get_case(i, a)["executions"]

    def evidence_upload(self, i, file_name, content_type, size, digest, a):
        if size < 1 or size > int(os.getenv("REVIEW_EVIDENCE_MAX_BYTES", "20971520")):
            raise ReviewValidationError("附件大小不合法")
        if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
            raise ReviewValidationError("sha256 格式不合法")
        if content_type not in {
            x.strip()
            for x in os.getenv(
                "REVIEW_EVIDENCE_CONTENT_TYPES", "application/pdf,image/png,image/jpeg,text/plain"
            ).split(",")
        }:
            raise ReviewValidationError("附件类型不允许")
        safe = os.path.basename(file_name).replace("\\", "_")
        self.get_case(i, a)
        eid = f"EVD-{uuid4().hex[:16].upper()}"
        key = f"{i}/{eid}/{safe}"
        st = self.storage()
        st.ensure_bucket()
        url = st.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": st.bucket,
                "Key": key,
                "ContentType": content_type,
                "Metadata": {"sha256": digest.lower()},
            },
            ExpiresIn=900,
        )
        return {
            "evidenceId": eid,
            "bucket": st.bucket,
            "objectKey": key,
            "uploadUrl": url,
            "expiresIn": 900,
        }

    def evidence_complete(self, i, p, a):
        st = self.storage()
        head = st.client.head_object(Bucket=p["bucket"], Key=p["objectKey"])
        if (
            int(head.get("ContentLength", -1)) != int(p["sizeBytes"])
            or head.get("ContentType") != p["contentType"]
            or head.get("Metadata", {}).get("sha256", "").lower() != p["sha256"].lower()
        ):
            raise ReviewValidationError("附件完整性校验失败")
        with self.sf() as s:
            c = self.owned(s, i, a)
            x = ReviewEvidence(
                id=p["evidenceId"],
                case_id=i,
                file_name=p["fileName"],
                content_type=p["contentType"],
                size_bytes=p["sizeBytes"],
                sha256=p["sha256"],
                bucket=p["bucket"],
                object_key=p["objectKey"],
                source=p.get("source", ""),
                trust_level=p.get("trustLevel", "UNVERIFIED"),
                status="READY",
                uploaded_by=a.user_id,
                created_at=now(),
            )
            s.add(x)
            self.audit(s, c, a, "EVIDENCE_ADDED", c.status, c.status, {"evidenceId": x.id})
            s.commit()
            return {"id": x.id, "status": x.status}

    def storage(self):
        return S3Storage(
            endpoint_url=os.getenv("REVIEW_S3_ENDPOINT_URL", "http://127.0.0.1:9020"),
            access_key=os.getenv("REVIEW_S3_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("REVIEW_S3_SECRET_KEY", "minioadmin"),
            region=os.getenv("REVIEW_S3_REGION", "us-east-1"),
            bucket=os.getenv("REVIEW_S3_BUCKET", "tech-kg-review-evidence"),
            secure=os.getenv("REVIEW_S3_SECURE", "false").lower() == "true",
        )

    def reclaim_expired(self, minutes=5):
        cutoff = now() - timedelta(minutes=minutes)
        actor = ReviewIdentity(
            "system", "system", frozenset({"review_admin"}), frozenset({"*"}), "", "reclaimer"
        )
        with self.sf() as s:
            rows = s.scalars(
                select(ReviewCase).where(
                    ReviewCase.status.in_(("CLAIMED", "IN_REVIEW")),
                    ReviewCase.heartbeat_at < cutoff,
                )
            ).all()
            for c in rows:
                old = c.status
                c.status = "OPEN"
                c.assignee_id = None
                c.assignee_name = None
                c.claimed_at = None
                c.heartbeat_at = None
                c.version += 1
                c.updated_at = now()
                self.audit(s, c, actor, "CLAIM_EXPIRED", old, "OPEN", {})
            s.commit()
            return len(rows)

    def need(self, s, i):
        c = s.get(ReviewCase, i)
        if not c:
            raise KeyError(i)
        return c

    def owned(self, s, i, a):
        c = self.need(s, i)
        require_domain_access(a, c.domain)
        if c.assignee_id != a.user_id and not a.has_any("review_admin"):
            raise ReviewForbiddenError("任务未由当前用户领取")
        return c

    def audit(self, s, c, a, e, old, new, d):
        s.add(
            ReviewAuditLog(
                case_id=c.id,
                event_type=e,
                actor_id=a.user_id,
                actor_name=a.user_name,
                request_id=a.request_id,
                old_status=old,
                new_status=new,
                detail=dump(d),
                created_at=now(),
            )
        )

    def outbox(self, s, i, e, p):
        s.add(
            ReviewOutbox(
                id=f"OUT-{uuid4().hex[:16].upper()}",
                case_id=i,
                event_type=e,
                payload=dump(p),
                status="PENDING",
                attempts=0,
                available_at=now(),
                created_at=now(),
            )
        )

    def case_dict(self, c):
        return {
            "id": c.id,
            "sourceTaskId": c.source_task_id,
            "batchId": c.batch_id,
            "nodeId": c.pipeline_step_id,
            "pipelineStepId": c.pipeline_step_id,
            "pipelineStepName": PIPELINE_STEPS[c.pipeline_step_id]["name"],
            "objectId": c.object_id,
            "objectType": c.object_type,
            "objectName": c.object_name,
            "errorType": c.error_type,
            "exceptionCode": c.exception_code,
            "category": c.category,
            "templateId": canonical_template(c.template_id),
            "domain": c.domain,
            "phase": c.phase,
            "riskLevel": c.risk_level,
            "scope": c.scope,
            "isolationScope": c.isolation_scope,
            "status": c.status,
            "assigneeId": c.assignee_id,
            "assigneeName": c.assignee_name,
            "version": c.version,
            "slaClaimAt": c.sla_claim_at.isoformat(),
            "slaResolveAt": c.sla_resolve_at.isoformat(),
            "diagnosis": c.diagnosis,
            "sourceTable": c.source_table,
            "sourceRecordId": c.source_record_id,
            "createdAt": c.created_at.isoformat(),
            "updatedAt": c.updated_at.isoformat(),
        }

    def detail(self, s, c, duplicate=False):
        d = self.case_dict(c)
        dr = s.get(ReviewDraft, c.id)
        reported = (load(c.candidate_snapshot) or {}).pop("reportedEvidence", [])
        files = [
            {
                "id": x.id,
                "fileName": x.file_name,
                "contentType": x.content_type,
                "sizeBytes": x.size_bytes,
                "sha256": x.sha256,
                "source": x.source,
                "trustLevel": x.trust_level,
                "status": x.status,
            }
            for x in s.scalars(
                select(ReviewEvidence)
                .where(ReviewEvidence.case_id == c.id)
                .order_by(ReviewEvidence.created_at)
            ).all()
        ]
        execs = [
            {
                "id": x.id,
                "resumeNode": x.resume_node,
                "workflowType": x.workflow_type,
                "workflowId": x.workflow_id,
                "runId": x.run_id,
                "status": x.status,
                "error": x.error,
            }
            for x in s.scalars(
                select(ReviewExecution)
                .where(ReviewExecution.case_id == c.id)
                .order_by(ReviewExecution.created_at.desc())
            ).all()
        ]
        d.update(
            {
                "draft": load(dr.payload) if dr else {},
                "template": template_contract(c.template_id),
                "data": {
                    "input": load(c.input_snapshot),
                    "candidate": load(c.candidate_snapshot),
                    "evidence": reported + files,
                },
                "input": load(c.input_snapshot),
                "candidate": load(c.candidate_snapshot),
                "evidence": reported + files,
                "consequence": {
                    "writeTarget": write_target(c.template_id),
                    "rerunStepId": c.pipeline_step_id,
                    "scope": c.isolation_scope,
                },
                "workflow": {
                    "workflowType": c.workflow_type,
                    "workflowId": c.workflow_id,
                    "runId": c.workflow_run_id,
                    "taskQueue": c.task_queue,
                },
                "executions": execs,
                "duplicate": duplicate,
            }
        )
        return d


manual_review_service = ManualReviewService()
