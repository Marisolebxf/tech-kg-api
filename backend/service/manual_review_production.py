"""Production manual-review service and graph-build handoff boundary."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import case, func, or_, select, update
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


logger = logging.getLogger("service.manual_review")


# 存量 T_DIRECT 案例的 risk_level 是中文"中/高"（旧口径），序列化时归一到 P1/P0，
# 保证展示与过滤口径统一；排序用同款 CASE 归一，避免"高"按码点沉底。
_RISK_NORMALIZE = {"中": "P1", "高": "P0"}


def _risk_label(v: str | None) -> str:
    return _RISK_NORMALIZE.get(v or "", v or "")


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
            "riskLevel": _risk_label(c.risk_level),
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
        # 状态分组：pending=待处理（非终态）；processed=已处理（终态）
        status_groups = {
            "pending": ReviewCase.status.notin_(TERMINAL_STATUSES),
            "processed": ReviewCase.status.in_(TERMINAL_STATUSES),
        }
        if f.get("status_group") in status_groups:
            q.append(status_groups[f["status_group"]])
        # 对象种类：T_DIRECT 案例 object_type 即 kind（entity/relation）；
        # 其他模板按模板语义兜底（T_LINK=实体对齐、T_EVIDENCE=关系证据）
        if f.get("kind") in ("entity", "relation"):
            q.append(
                or_(
                    ReviewCase.object_type == f["kind"],
                    ReviewCase.template_id == ("T_LINK" if f["kind"] == "entity" else "T_EVIDENCE"),
                )
            )
        queues = {
            "mine": ReviewCase.assignee_id == a.user_id,
            "unclaimed": ReviewCase.status == "OPEN",
            "approval": ReviewCase.status == "PENDING_APPROVAL",
            "failed": ReviewCase.status.in_(("APPLY_FAILED", "RERUN_FAILED")),
            "history": ReviewCase.status.in_(TERMINAL_STATUSES),
        }
        if f.get("queue") in queues:
            q.append(queues[f["queue"]])
        # category 过滤：A=入库决策（T_DIRECT/T_LINK/T_EVIDENCE）；B=数据修正（T_MAP/T_DQ_FILL/T_DQ_MERGE/T_ATTR）；
        # C=抽取失败重跑（T_EXTRACT_FAIL）；不传=所有 template；T_RUNTIME 始终不进审核队列
        # （属于代码问题，自动重试/告警另行处理）
        categories = {
            "A": ("T_DIRECT", "T_LINK", "T_EVIDENCE"),
            "B": ("T_MAP", "T_DQ_FILL", "T_DQ_MERGE", "T_ATTR"),
            "C": ("T_EXTRACT_FAIL",),
        }
        if f.get("category") in categories:
            q.append(ReviewCase.template_id.in_(categories[f["category"]]))
        else:
            # 默认排除 T_RUNTIME（即使没传 category，T_RUNTIME 也不应在审核队列显示）
            q.append(ReviewCase.template_id != "T_RUNTIME")
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
                .order_by(
                    case(
                        {"高": "P0", "中": "P1"},
                        value=ReviewCase.risk_level,
                        else_=ReviewCase.risk_level,
                    ),
                    ReviewCase.created_at,
                )
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
            approval = requires_approval(_risk_label(c.risk_level), action, result)
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

    def create_direct_case(
        self,
        *,
        task_id: str,
        execution_id: str | None,
        step_id: str,
        kind: str,
        candidate: dict[str, Any],
        object_id: str | None = None,
        object_name: str | None = None,
        node_label: str | None = None,
        edge_type: str | None = None,
        from_id: str | None = None,
        to_id: str | None = None,
        reason: str = "",
        confidence: float | None = None,
        evidence: list[Any] | None = None,
        workflow_id: str | None = None,
        workflow_run_id: str | None = None,
        domain: str = "graph",
        service_actor: str = "kg.custom.steps",
        source_record: dict[str, Any] | None = None,
        source_table: str | None = None,
        source_record_id: str | None = None,
        llm_input: dict[str, Any] | None = None,
        llm_output: str | None = None,
        template_id: str = "T_DIRECT",
        workflow_type: str | None = None,
        exception_code: str | None = None,
        resume_token: str | None = None,
        extra_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """直接 OPEN 状态入队（不走 4-eyes claim/submit）。

        默认 T_DIRECT（kg.custom.steps pendingReview）：candidate_snapshot 附加
        kind/nodeLabel/edgeType/fromId/toId 元字段，direct_decide 读这些字段写图。
        ``template_id`` 可选 T_EXTRACT_FAIL（抽取失败重跑）/ T_LINK（同名冲突对齐），
        ``extra_snapshot`` 合入 input_snapshot 供对应处理端读取。
        """
        t = now()
        obj_id = (
            object_id
            or candidate.get("id")
            or candidate.get("scholar_id")
            or f"{step_id}-{uuid4().hex[:8]}"
        )
        obj_name = object_name or candidate.get("name_zh") or candidate.get("name") or obj_id
        snapshot = {
            **candidate,
            "_kind": kind,
            "_nodeLabel": node_label,
            "_edgeType": edge_type,
            "_fromId": from_id,
            "_toId": to_id,
            "_confidence": confidence,
        }
        dedupe_key = sha([task_id, step_id, obj_id, sha(snapshot)])
        risk = "P1" if (confidence is None or confidence >= 0.7) else "P0"
        effective_workflow_type = workflow_type or "kg.custom.steps"
        c = ReviewCase(
            id=f"MR-{t:%Y%m%d}-{uuid4().hex[:12].upper()}",
            dedupe_key=dedupe_key,
            event_id=f"kg-step-{uuid4().hex}",
            source_task_id=task_id,
            batch_id=None,
            node_id=step_id,
            pipeline_step_id=step_id,
            object_id=obj_id,
            object_type=kind,
            object_name=obj_name,
            error_type=reason or "需要人工审核",
            error_fingerprint=sha([reason, snapshot]),
            category=TEMPLATES[template_id]["title"],
            template_id=template_id,
            template_version="1.0",
            domain=domain,
            phase="图谱构建",
            risk_level=risk,
            scope="OBJECT",
            status="OPEN",
            version=1,
            sla_claim_at=t + timedelta(hours=1),
            sla_resolve_at=t + timedelta(hours=24),
            workflow_type=effective_workflow_type,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            task_queue="tech-kg-workflows",
            resume_token=resume_token or f"kg-step:{task_id}:{step_id}",
            exception_code=exception_code or "KG_STEP_PENDING_REVIEW",
            isolation_scope="OBJECT",
            template_payload_version="1.0",
            input_snapshot=dump(
                {
                    "evidence": evidence or [],
                    "executionId": execution_id,
                    "confidence": confidence,
                    "source_record": source_record,
                    "llm_input": llm_input,
                    "llm_output": llm_output,
                    **(extra_snapshot or {}),
                }
            ),
            source_table=source_table,
            source_record_id=source_record_id,
            candidate_snapshot=dump(snapshot),
            diagnosis=reason or "需要人工审核",
            created_at=t,
            updated_at=t,
        )
        actor = ReviewIdentity(
            service_actor,
            service_actor,
            frozenset({"review_admin"}),
            frozenset({"*"}),
            "service",
            c.event_id,
        )
        with self.sf() as s:
            existing = s.scalar(select(ReviewCase).where(ReviewCase.dedupe_key == dedupe_key))
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
                    {"stepId": step_id, "kind": kind, "reason": reason},
                )
                s.commit()
            except IntegrityError:
                s.rollback()
                existing = s.scalar(select(ReviewCase).where(ReviewCase.dedupe_key == dedupe_key))
                if not existing:
                    raise
                return self._ingress_response(existing, True)
        return self._ingress_response(c, False)

    # ------------------------------------------------------------------
    # T_EXTRACT_FAIL：抽取失败记录重跑生命周期
    # ------------------------------------------------------------------

    def _extract_service_actor(self, tag: str) -> ReviewIdentity:
        return ReviewIdentity(
            "kg.schema.extract",
            "kg.schema.extract",
            frozenset({"review_admin"}),
            frozenset({"*"}),
            "service",
            f"{tag}-{uuid4().hex[:8]}",
        )

    def list_extract_fail_cases(
        self,
        *,
        case_ids: list[str] | None = None,
        execution_id: str | None = None,
        statuses: tuple[str, ...] = ("OPEN", "RERUN_FAILED"),
    ) -> list[dict[str, Any]]:
        """查可重跑的 T_EXTRACT_FAIL case（供重跑服务分组、下发）。"""
        with self.sf() as s:
            q = select(ReviewCase).where(ReviewCase.template_id == "T_EXTRACT_FAIL")
            if case_ids:
                q = q.where(ReviewCase.id.in_(case_ids))
            if statuses:
                q = q.where(ReviewCase.status.in_(statuses))
            rows = s.scalars(q).all()
        result: list[dict[str, Any]] = []
        for c in rows:
            snapshot = load(c.input_snapshot) or {}
            if execution_id and snapshot.get("executionId") != execution_id:
                continue
            record_id = str(c.source_record_id or "")
            if not record_id:
                continue
            result.append(
                {
                    "caseId": c.id,
                    "recordId": record_id,
                    "sourceBindingId": str(snapshot.get("sourceBindingId") or ""),
                    "schemaId": snapshot.get("schemaId"),
                    "schemaKey": snapshot.get("schemaKey"),
                    "executionId": snapshot.get("executionId"),
                    "jobId": snapshot.get("jobId"),
                    "attempt": int(snapshot.get("attempt") or 1),
                    "sourceTable": c.source_table,
                    "status": c.status,
                }
            )
        return result

    def mark_extract_rerun(
        self, case_ids: list[str], *, rerun_execution_id: str | None = None
    ) -> int:
        """重跑下发前把 T_EXTRACT_FAIL case 标 RERUNNING（必须在触发执行**之前**调用）。

        先标记再触发，避免竞态（执行先完成而 case 尚未标记导致回写落空）。
        执行 id 由 ``attach_rerun_execution`` 在触发成功后补写进 snapshot。
        触发失败由调用方 ``revert_extract_rerun`` 回滚为 OPEN。
        """
        actor = self._extract_service_actor("rerun")
        t = now()
        marked = 0
        with self.sf() as s:
            for case_id in case_ids:
                c = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                if c is None or c.template_id != "T_EXTRACT_FAIL":
                    continue
                if c.status in TERMINAL_STATUSES or c.status == "RERUNNING":
                    continue
                snapshot = load(c.input_snapshot) or {}
                if rerun_execution_id:
                    snapshot["rerunExecutionId"] = rerun_execution_id
                c.input_snapshot = dump(snapshot)
                old = c.status
                c.status = "RERUNNING"
                c.version += 1
                c.updated_at = t
                self.audit(
                    s,
                    c,
                    actor,
                    "RERUN_STARTED",
                    old,
                    c.status,
                    {"rerunExecutionId": rerun_execution_id},
                )
                marked += 1
            s.commit()
        return marked

    def attach_rerun_execution(self, case_ids: list[str], rerun_execution_id: str) -> int:
        """触发成功后把重跑执行 id 补写进 case snapshot（前端展示/追踪）。"""
        t = now()
        attached = 0
        try:
            with self.sf() as s:
                for case_id in case_ids:
                    c = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                    if c is None:
                        continue
                    snapshot = load(c.input_snapshot) or {}
                    snapshot["rerunExecutionId"] = rerun_execution_id
                    c.input_snapshot = dump(snapshot)
                    c.updated_at = t
                    attached += 1
                s.commit()
        except Exception:  # noqa: BLE001
            logger.warning("补写 rerunExecutionId 失败 cases=%s", case_ids, exc_info=True)
        return attached

    def revert_extract_rerun(self, case_ids: list[str], *, reason: str) -> int:
        """重跑触发失败时把 RERUNNING 回滚为 OPEN（best-effort，不抛错）。"""
        actor = self._extract_service_actor("rerun-revert")
        t = now()
        reverted = 0
        try:
            with self.sf() as s:
                for case_id in case_ids:
                    c = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
                    if c is None or c.status != "RERUNNING":
                        continue
                    old = c.status
                    c.status = "OPEN"
                    c.version += 1
                    c.updated_at = t
                    self.audit(s, c, actor, "RERUN_PROGRESS", old, c.status, {"reason": reason})
                    reverted += 1
                s.commit()
        except Exception:  # noqa: BLE001
            return reverted
        return reverted

    def resolve_extract_rerun(
        self,
        *,
        rerun_case_ids: list[str],
        failed_records: list[dict[str, Any]],
        rerun_execution_id: str | None,
        task_id: str,
        kind: str = "entity",
        name: str | None = None,
    ) -> dict[str, Any]:
        """重跑执行结束后回写 T_EXTRACT_FAIL case。

        记录不在本次 failures → RESOLVED（RERUN_SUCCEEDED）；仍失败 → 原 case
        RESOLVED（被取代）+ 新 case（attempt+1，绑本次重跑执行），供再次点击重跑。
        """
        failed_by_key: dict[tuple[str, str], dict[str, Any]] = {
            (str(f.get("sourceBindingId") or ""), str(f.get("recordId") or "")): f
            for f in failed_records
            if isinstance(f, dict)
        }
        actor = self._extract_service_actor("rerun-resolve")
        t = now()
        resolved = 0
        refailed: list[dict[str, Any]] = []
        with self.sf() as s:
            cases = s.scalars(
                select(ReviewCase).where(ReviewCase.id.in_(rerun_case_ids or []))
            ).all()
            for c in cases:
                if c.template_id != "T_EXTRACT_FAIL" or c.status != "RERUNNING":
                    continue
                snapshot = load(c.input_snapshot) or {}
                key = (str(snapshot.get("sourceBindingId") or ""), str(c.source_record_id))
                old = c.status
                c.status = "RESOLVED"
                c.updated_at = t
                if key in failed_by_key:
                    self.audit(
                        s,
                        c,
                        actor,
                        "RERUN_FAILED",
                        old,
                        "RESOLVED",
                        {"rerunExecutionId": rerun_execution_id, "superseded": True},
                    )
                    refailed.append(
                        {"case": c, "snapshot": snapshot, "failure": failed_by_key[key]}
                    )
                else:
                    self.audit(
                        s,
                        c,
                        actor,
                        "RERUN_SUCCEEDED",
                        old,
                        "RESOLVED",
                        {"rerunExecutionId": rerun_execution_id},
                    )
                resolved += 1
            s.commit()
        recreated = 0
        for item in refailed:
            case = item["case"]
            snapshot = item["snapshot"]
            failure = item["failure"]
            try:
                self.create_direct_case(
                    task_id=case.source_task_id or task_id,
                    execution_id=rerun_execution_id,
                    step_id=case.pipeline_step_id or "extract",
                    kind=case.object_type or kind,
                    candidate={
                        "recordId": str(case.source_record_id),
                        "error": str(failure.get("error") or ""),
                        "schemaKey": snapshot.get("schemaKey"),
                    },
                    object_id=str(case.source_record_id),
                    object_name=case.object_name,
                    node_label=(name if (case.object_type or kind) == "entity" else None),
                    edge_type=(name if (case.object_type or kind) != "entity" else None),
                    reason=f"重跑仍失败: {str(failure.get('error') or '')[:500]}",
                    workflow_id=case.workflow_id,
                    source_table=case.source_table,
                    source_record_id=str(case.source_record_id),
                    domain=case.domain or "graph",
                    service_actor="kg.schema.extract",
                    template_id="T_EXTRACT_FAIL",
                    workflow_type="kg.schema.extract",
                    exception_code="KG_EXTRACT_RECORD_FAILED",
                    resume_token=f"extract-fail:{rerun_execution_id}:{case.source_record_id}",
                    extra_snapshot={
                        **{k: v for k, v in snapshot.items() if k != "rerunExecutionId"},
                        "attempt": int(snapshot.get("attempt") or 1) + 1,
                        "rerunOfExecutionId": snapshot.get("executionId"),
                        "executionId": rerun_execution_id,
                    },
                )
                recreated += 1
            except Exception:  # noqa: BLE001
                logger.warning("重跑仍失败的新 case 创建失败: %s", case.id, exc_info=True)
        return {"resolved": resolved, "refailed": len(refailed), "recreated": recreated}

    def direct_decide(
        self,
        case_id: str,
        version: int,
        accepted: bool,
        note: str,
        identity: Any,
        candidate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """kg.custom.steps T_DIRECT 案例两步决策：accept 直接写图，reject 丢弃。

        不调 enqueue_correction、不重启 workflow、不要求 submit 阶段。
        candidate 传"修正后的完整候选"（仅 accept 有效）：``_`` 前缀元字段
        （写图目标/审计元数据）一律以快照为准，防止改写 label/端点注入。
        """
        require_role(identity, "reviewer")
        stripped: dict[str, Any] | None = None
        if candidate is not None:
            if not accepted:
                raise ReviewValidationError("驳回不需要候选修正")
            stripped = {k: v for k, v in candidate.items() if not k.startswith("_")}
            if not stripped:
                raise ReviewValidationError("修正后的候选不能为空")
            if len(dump(stripped)) > int(os.getenv("REVIEW_SNAPSHOT_MAX_BYTES", "2097152")):
                raise ReviewValidationError("修正后的候选超出大小限制")
        with self.sf() as s:
            c = self.need(s, case_id)
            require_domain_access(identity, c.domain)
            if c.template_id != "T_DIRECT":
                raise ReviewValidationError("仅 T_DIRECT 案例支持 direct_decide")
            if c.version != version or c.status != "OPEN":
                raise ReviewConflictError("状态或版本冲突")
            old = c.status
            audit_detail: dict[str, Any] = {"note": note}
            if stripped is not None:
                old_snapshot = load(c.candidate_snapshot) or {}
                old_fields = {k: v for k, v in old_snapshot.items() if not k.startswith("_")}
                meta = {k: v for k, v in old_snapshot.items() if k.startswith("_")}
                # 只记 key 不记值，避免敏感数据/大快照进审计日志
                audit_detail["candidateModified"] = True
                audit_detail["modifiedFields"] = {
                    "added": sorted(k for k in stripped if k not in old_fields),
                    "changed": sorted(
                        k for k in stripped if k in old_fields and old_fields[k] != stripped[k]
                    ),
                    "removed": sorted(k for k in old_fields if k not in stripped),
                }
                audit_detail["originalCandidateSha256"] = sha(old_fields)
                c.candidate_snapshot = dump({**stripped, **meta})
                c.updated_at = now()
            if accepted:
                self._write_candidate_to_graph(c)
                c.status = "RESOLVED"
            else:
                c.status = "REJECTED"
            c.completed_at = now()
            c.version += 1
            c.updated_at = now()
            self.audit(
                s,
                c,
                identity,
                "DIRECT_ACCEPTED" if accepted else "DIRECT_REJECTED",
                old,
                c.status,
                audit_detail,
            )
            s.commit()
            return self.detail(s, c)

    def _write_candidate_to_graph(self, c: ReviewCase) -> None:
        """accept 时把 candidate_snapshot 灌图。entity→merge_node，relation→create_edge。

        字段先 ``_coerce_to_schema`` 对齐 tag/edge schema（多余字段塞 extra_json），
        避免 NebulaGraph ``Unknown column`` 400。
        """
        from infra.graph_db import get_trs_graph_client

        snapshot = load(c.candidate_snapshot)
        kind = snapshot.get("_kind") or c.object_type
        candidate = {k: v for k, v in snapshot.items() if not k.startswith("_")}
        graph = get_trs_graph_client()
        if kind == "entity":
            node_label = snapshot.get("_nodeLabel")
            if not node_label:
                raise ReviewValidationError("entity 候选缺 nodeLabel")
            candidate = self._coerce_to_schema(graph, node_label, candidate)
            # 实体走 nGQL INSERT VERTEX（列级 upsert 幂等）——REST /nodes/merge 会把
            # id/name/vid 当身份键从属性剥离，而 schema DDL 把 id/name 建成 NOT NULL，
            # merge 永远 400（与平台抽取 write_records 同一结论）
            import json as _json

            def _ngql_value(value: Any) -> str:
                if value is None:
                    return "NULL"
                if isinstance(value, bool):
                    return "true" if value else "false"
                if isinstance(value, (int, float)):
                    return str(value)
                return _json.dumps(str(value), ensure_ascii=False)

            from datetime import datetime as _dt

            props = dict(candidate)
            props.setdefault("id", c.object_id)
            now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
            props.setdefault("create_time", now_str)
            props.setdefault("update_time", now_str)
            props.setdefault("source_table", "manual_review")
            cols = list(props.keys())
            stmt = (
                f'INSERT VERTEX {node_label}({", ".join(cols)}) VALUES "{c.object_id}": '
                f'({", ".join(_ngql_value(props[col]) for col in cols)})'
            )
            graph.execute_write(stmt)
        elif kind == "relation":
            edge_type = snapshot.get("_edgeType")
            from_id = snapshot.get("_fromId")
            to_id = snapshot.get("_toId")
            if not (edge_type and from_id and to_id):
                raise ReviewValidationError("relation 候选缺 edgeType/fromId/toId")
            candidate = self._coerce_to_schema(graph, edge_type, candidate, is_edge=True)
            graph.create_edge(from_id, to_id, edge_type, candidate)
        else:
            raise ReviewValidationError(f"未知 kind: {kind}")

    def _coerce_to_schema(
        self,
        graph: Any,
        label: str,
        candidate: dict[str, Any],
        *,
        is_edge: bool = False,
    ) -> dict[str, Any]:
        """把 candidate 字段对齐到 tag/edge schema。

        - schema 里有的字段：保留，值转 string（NebulaGraph tag 属性多为 string）
        - schema 里有 ``extra_json``：多余字段塞进 extra_json（JSON 串），不丢数据
        - schema 里没有 extra_json：丢弃多余字段（记 warning）
        - schema 查询失败：原样发（让 trs-graph 报 400 暴露问题）
        """
        import json

        log = logger
        try:
            desc = graph.execute_query(
                f"DESCRIBE EDGE `{label}`" if is_edge else f"DESCRIBE TAG `{label}`"
            )
            records = (
                desc.records
                if hasattr(desc, "records")
                else (desc.get("records", []) if isinstance(desc, dict) else [])
            )
            schema_fields = {
                r.get("Field") for r in records if isinstance(r, dict) and r.get("Field")
            }
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "DESCRIBE %s %s 失败，原样灌图: %s", "EDGE" if is_edge else "TAG", label, exc
            )
            return {k: v if isinstance(v, str) else str(v) for k, v in candidate.items()}

        if not schema_fields:
            return {k: v if isinstance(v, str) else str(v) for k, v in candidate.items()}

        mapped: dict[str, Any] = {}
        extras: dict[str, Any] = {}
        for k, v in candidate.items():
            if k in schema_fields:
                mapped[k] = v if isinstance(v, str) else str(v)
            else:
                extras[k] = v

        if extras:
            if "extra_json" in schema_fields:
                mapped["extra_json"] = json.dumps(extras, ensure_ascii=False)
            else:
                log.warning(
                    "candidate 有 %d 个字段不在 %s %s schema 里且无 extra_json 兜底，丢弃: %s",
                    len(extras),
                    "edge" if is_edge else "tag",
                    label,
                    list(extras),
                )
        return mapped

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
            # kg.custom.steps 流水线的 step id 是 manifest 自定义的（如 seed），
            # 不在标准 PIPELINE_STEPS 里——取不到时回退原值，别让队列接口 404
            "pipelineStepName": (PIPELINE_STEPS.get(c.pipeline_step_id) or {}).get(
                "name", c.pipeline_step_id
            ),
            "objectId": c.object_id,
            "objectType": c.object_type,
            "objectName": c.object_name,
            "errorType": c.error_type,
            "exceptionCode": c.exception_code,
            "category": c.category,
            "templateId": canonical_template(c.template_id),
            "domain": c.domain,
            "phase": c.phase,
            "riskLevel": _risk_label(c.risk_level),
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
        input_data = load(c.input_snapshot) or {}
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
                    "input": input_data,
                    "candidate": load(c.candidate_snapshot),
                    "evidence": reported + files,
                    "source_record": input_data.get("source_record"),
                    "llm_input": input_data.get("llm_input"),
                    "llm_output": input_data.get("llm_output"),
                },
                "input": input_data,
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
