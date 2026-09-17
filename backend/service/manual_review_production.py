"""生产人工审核服务（队列 / 直审裁决 / 直判写图 / 抽取失败重跑）。

2026-09-15 起移除「外部 graph-build 服务」移交通道（内部入口 / correction /
outbox / resume 派发 / 执行回调）：审核模块只管裁决与记录决议。
2026-09-17 起 T_LINK 裁决接入真实执行（写前扣留 case 写图 + 待定关系补写，
见 ``_apply_link_verdict``）；存量写后 case（无 ``_incoming`` 快照）仍只记录决议。
2026-09-17 起改为直审模式：OPEN 打开即可 submit（领取为可选保留），一切提交
即执行——审批环节（PENDING_APPROVAL 四方签核）已移除。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from db_model.manual_review import (
    ReviewAuditLog,
    ReviewCase,
    ReviewDecision,
    ReviewDraft,
    ReviewEvidence,
)
from infra.mysql import get_session_factory
from infra.s3 import S3Storage
from service.manual_review_domain import (
    EDITABLE_STATUSES,
    PIPELINE_STEPS,
    SUBMITTABLE_STATUSES,
    TEMPLATES,
    TERMINAL_STATUSES,
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
    canonical_template,
    require_domain_access,
    require_role,
    role_can_review,
    template_contract,
    validate_action,
    write_target,
)

STATE_OR_VERSION_CONFLICT = "状态或版本冲突"


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
    def __init__(self, session_factory=None):
        self.sf = session_factory or get_session_factory()

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
        # T_LINK 是实体对齐，按实体兜底
        if f.get("kind") == "entity":
            q.append(or_(ReviewCase.object_type == "entity", ReviewCase.template_id == "T_LINK"))
        elif f.get("kind") == "relation":
            q.append(ReviewCase.object_type == "relation")
        queues = {
            "mine": ReviewCase.assignee_id == a.user_id,
            "unclaimed": ReviewCase.status == "OPEN",
            "approval": ReviewCase.status == "PENDING_APPROVAL",
            "failed": ReviewCase.status.in_(("APPLY_FAILED", "RERUN_FAILED")),
            "history": ReviewCase.status.in_(TERMINAL_STATUSES),
        }
        if f.get("queue") in queues:
            q.append(queues[f["queue"]])
        # category 过滤：A=入库决策（T_DIRECT/T_LINK）；C=抽取失败重跑（T_EXTRACT_FAIL）；
        # 不传=所有 template
        categories = {
            "A": ("T_DIRECT", "T_LINK"),
            "C": ("T_EXTRACT_FAIL",),
        }
        if f.get("category") in categories:
            q.append(ReviewCase.template_id.in_(categories[f["category"]]))
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
        # 排序：sort=updatedAt 时按更新时间（order=asc|desc，默认 desc）；
        # 不传 sort 保持既有默认 风险级→创建时间升序（前端 e2e 按创建时间升序的假设依赖它）
        if f.get("sort") == "updatedAt":
            ordering = (
                (
                    ReviewCase.updated_at.asc()
                    if f.get("order") == "asc"
                    else ReviewCase.updated_at.desc()
                ),
            )
        else:
            ordering = (
                case(
                    {"高": "P0", "中": "P1"},
                    value=ReviewCase.risk_level,
                    else_=ReviewCase.risk_level,
                ),
                ReviewCase.created_at,
            )
        with self.sf() as s:
            total = s.scalar(select(func.count()).select_from(ReviewCase).where(*q)) or 0
            rows = s.scalars(
                select(ReviewCase)
                .where(*q)
                .order_by(*ordering)
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
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            s.merge(ReviewDraft(case_id=i, payload=dump(p), updated_by=a.user_id, updated_at=now()))
            old = c.status
            c.status = "IN_REVIEW"
            c.version += 1
            c.updated_at = now()
            self.audit(s, c, a, "DRAFT_SAVED", old, c.status, {})
            s.commit()
            return self.detail(s, c)

    def submit(self, i, v, action, result, note, a):
        """直审模式：OPEN 可直接提交（领取为可选），一切提交即执行、不设审批。

        已被他人领取的 case 仍限领取人 / review_admin 操作；并发仍是 version
        乐观锁——两人同开一个 case，先提交者生效，后提交者报版本冲突。
        """
        with self.sf() as s:
            c = self.need(s, i)
            require_domain_access(a, c.domain)
            if not role_can_review(a, c.phase):
                raise ReviewForbiddenError("角色与任务阶段不匹配")
            if c.status in ("CLAIMED", "IN_REVIEW") and c.assignee_id != a.user_id:
                if not a.has_any("review_admin"):
                    raise ReviewForbiddenError("任务未由当前用户领取")
            if c.version != v or c.status not in SUBMITTABLE_STATUSES:
                raise ReviewConflictError(STATE_OR_VERSION_CONFLICT)
            validate_action(c.template_id, action, result)
            t = now()
            d = ReviewDecision(
                case_id=i,
                action_id=action,
                result=dump(result),
                note=note,
                submitted_by=a.user_id,
                status="APPROVED",
                created_at=t,
                decided_at=t,
            )
            s.add(d)
            s.flush()
            old = c.status
            c.submitted_by = a.user_id
            # OPEN 直审时记录处理人，历史里可追溯（队列不再显示"待领取"）
            if not c.assignee_id:
                c.assignee_id = a.user_id
                c.assignee_name = a.user_name
            apply_detail: dict[str, Any] | None = None
            if canonical_template(c.template_id) == "T_LINK" and action == "entity-confirm":
                # 消歧裁决真实执行（写前扣留 case 写图；存量写后 case 仅记录决议）
                apply_detail = self._apply_link_verdict(c, result)
            c.status = "RESOLVED"
            c.completed_at = t
            c.version += 1
            c.updated_at = t
            self.audit(
                s,
                c,
                a,
                "DECISION_SUBMITTED",
                old,
                c.status,
                {"actionId": action, **(apply_detail or {})},
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
        """直接 OPEN 状态入队（打开即可裁决，无需领取）。

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

    # ------------------------------------------------------------------
    # T_LINK：实体对齐裁决执行（写前扣留 case 真实写图）
    # ------------------------------------------------------------------

    def park_or_rewrite_edges(
        self, edge_type: str, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """关系写图前端点消歧处理（``write_records`` 关系分支调用，跨执行兜底）。

        - 端点命中未决 T_LINK 灰区 case → 该边挂到 case 快照 ``_pendingRelations``
          （裁决 merge/create 时统一补写，不产生 Nebula 悬挂点；按边类型+端点去重幂等）；
        - 端点 case 已裁决 merge → 端点改写为目标实体后正常返回写；
        - 端点实体已被驳回（verdict=reject）→ 该边一并丢弃；
        - 其余（含已裁决 create，预留 vid 已入库）→ 原样返回写。
        """
        if not records:
            return {"records": [], "parked": 0, "dropped": 0}
        endpoints = {str(r.get("fromId")) for r in records} | {str(r.get("toId")) for r in records}
        verdicts: dict[str, tuple[str | None, str | None]] = {}
        with self.sf() as s:
            cases = s.scalars(
                select(ReviewCase).where(
                    ReviewCase.template_id == "T_LINK",
                    ReviewCase.object_id.in_(endpoints),
                )
            ).all()
            open_cases = {c.object_id: c for c in cases if c.status not in TERMINAL_STATUSES}
            for c in cases:
                if c.object_id in open_cases:
                    continue
                d = s.scalar(
                    select(ReviewDecision)
                    .where(ReviewDecision.case_id == c.id)
                    .order_by(ReviewDecision.id.desc())
                )
                res = (load(d.result) or {}) if d else {}
                verdicts[c.object_id] = (res.get("entityVerdict"), res.get("targetEntityId"))
            parked_records = [
                r
                for r in records
                if str(r.get("fromId")) in open_cases or str(r.get("toId")) in open_cases
            ]
            for record in parked_records:
                vid = next(
                    v
                    for v in (str(record.get("fromId")), str(record.get("toId")))
                    if v in open_cases
                )
                case = open_cases[vid]
                snapshot = load(case.candidate_snapshot) or {}
                pending = snapshot.setdefault("_pendingRelations", [])
                rel = {
                    "edgeType": edge_type,
                    "fromId": str(record.get("fromId")),
                    "toId": str(record.get("toId")),
                    "props": record.get("props") or {},
                }
                if not any(
                    p.get("edgeType") == rel["edgeType"]
                    and p.get("fromId") == rel["fromId"]
                    and p.get("toId") == rel["toId"]
                    for p in pending
                ):
                    pending.append(rel)
                    case.candidate_snapshot = dump(snapshot)
                    case.updated_at = now()
            s.commit()
        kept: list[dict[str, Any]] = []
        dropped = 0
        for record in records:
            frm, to = str(record.get("fromId")), str(record.get("toId"))
            if frm in open_cases or to in open_cases:
                continue
            if "reject" in (verdicts.get(frm, (None, None))[0], verdicts.get(to, (None, None))[0]):
                dropped += 1
                continue
            out = dict(record)
            for key, vid in (("fromId", frm), ("toId", to)):
                verdict, target = verdicts.get(vid, (None, None))
                if verdict == "merge" and target:
                    out[key] = str(target)
            kept.append(out)
        return {"records": kept, "parked": len(parked_records), "dropped": dropped}

    def _graph_client_for(self, snapshot: dict[str, Any]) -> Any:
        """按快照记载的图空间建客户端（缺省走环境默认空间）并完成连接。"""
        from infra.graph_db.client import TRSGraphClient
        from infra.graph_db.config import TRSGraphSettings

        settings = TRSGraphSettings.from_env()
        space = snapshot.get("_graphSpace")
        if space:
            settings.space = space
        client = TRSGraphClient(settings)
        client.connect()
        return client

    def _apply_link_verdict(self, c: ReviewCase, result: dict[str, Any]) -> dict[str, Any]:
        """T_LINK 裁决执行：merge→扣留记录并入所选候选；create→按预留 vid 新建。

        写前扣留 case（快照含 ``_incoming``）：INSERT VERTEX 幂等 upsert，merge 与
        create 是同一条语句、仅 vid 不同；空值列不写＝不覆盖目标已有值；``_pendingRelations``
        里的待定边在实体落图后按改写端点补写。图写失败异常上抛 → 事务回滚 → 审核
        员重新提交即重试（幂等安全）。存量写后 case（无 ``_incoming``）只记录决议。
        """
        snapshot = load(c.candidate_snapshot) or {}
        incoming = snapshot.get("_incoming")
        if not incoming:
            return {"applied": False, "note": "存量写后 case：实体已在图，仅记录决议"}
        verdict = result.get("entityVerdict")
        if verdict == "merge":
            target = str(result.get("targetEntityId") or "")
            allowed = {
                str(x.get("vid")) for x in snapshot.get("existingCandidates") or [] if x.get("vid")
            }
            if target not in allowed:
                raise ReviewValidationError("目标实体不在候选集内")
            vid = target
        elif verdict == "create":
            vid = str(incoming.get("vid") or c.object_id)
        else:
            raise ReviewValidationError("retype 暂不支持：请驳回后修正脚本重跑")
        client = self._graph_client_for(snapshot)
        try:
            self._insert_withheld_vertex(client, c, snapshot, incoming, vid)
            old_vid = str(incoming.get("vid") or c.object_id)
            written_edges = 0
            for rel in snapshot.get("_pendingRelations") or []:
                edge_type = rel.get("edgeType")
                frm, to = str(rel.get("fromId")), str(rel.get("toId"))
                if not edge_type:
                    continue
                if frm == old_vid:
                    frm = vid
                if to == old_vid:
                    to = vid
                props = self._coerce_to_schema(
                    client, edge_type, rel.get("props") or {}, is_edge=True
                )
                client.create_edge(frm, to, edge_type, props)
                written_edges += 1
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭图客户端失败")
        return {
            "applied": True,
            "verdict": verdict,
            "vid": vid,
            "pendingRelationsWritten": written_edges,
        }

    @staticmethod
    def _tag_fields(client: Any, label: str) -> set[str] | None:
        """DESCRIBE TAG 取列集合；失败返回 None（调用方走兜底）。"""
        try:
            desc = client.execute_query(f"DESCRIBE TAG `{label}`")
            return {f for f in (r.get("Field") for r in desc.records or []) if isinstance(f, str)}
        except Exception:  # noqa: BLE001
            logger.warning("DESCRIBE TAG %s 失败，写图按旧兜底补审计列", label)
            return None

    def _insert_withheld_vertex(
        self,
        client: Any,
        c: ReviewCase,
        snapshot: dict[str, Any],
        incoming: dict[str, Any],
        vid: str,
    ) -> None:
        """扣留实体写入指定 vid（幂等 upsert；空值列不写＝不覆盖目标已有值）。"""
        import json as _json
        from datetime import datetime as _dt

        node_label = snapshot.get("_nodeLabel")
        if not node_label:
            raise ReviewValidationError("实体候选缺 nodeLabel")
        props = {
            key: value
            for key, value in (incoming.get("props") or {}).items()
            if value not in (None, "")
        }
        props = self._coerce_to_schema(client, node_label, props)
        # 审计/身份列按 tag 实际 schema 补（vendor ETL 的 Organization 没有
        # id/create_time 等列，强塞会 Unknown column 400）；schema 查不出来时
        # 维持旧兜底让 trs-graph 报错暴露问题
        fields = self._tag_fields(client, node_label)
        now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        audit = {
            "id": vid,
            "create_time": now_str,
            "update_time": now_str,
            "source_table": incoming.get("sourceTable") or "schema_extract",
        }
        for key, value in audit.items():
            if fields is None or key in fields:
                props.setdefault(key, value)

        def _ngql_value(value: Any) -> str:
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            return _json.dumps(str(value), ensure_ascii=False)

        cols = ", ".join(f"`{key}`" for key in props)
        values = ", ".join(_ngql_value(props[key]) for key in props)
        client.execute_write(f'INSERT VERTEX `{node_label}`({cols}) VALUES "{vid}":({values})')

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

        不重启 workflow、不要求 submit 阶段。
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
                f"({', '.join(_ngql_value(props[col]) for col in cols)})"
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

    def cancel(self, i, v, reason, a):
        _ = reason
        require_role(a, "review_admin")
        return self.mutate(
            i, v, a, {"status": "CANCELLED", "completed_at": now()}, "CASE_CANCELLED", True
        )

    def delete_case(self, i, a):
        """物理删除未处理 case（连同草稿/决议/附件/审计一并删除，不可恢复）。

        仅非终态（OPEN/RERUN_FAILED 等未处理）可删——与可重跑同门控；
        已处理的记录保留作历史，不给删。review_admin 专用。
        """
        require_role(a, "review_admin")
        with self.sf() as s:
            c = self.need(s, i)
            if c.status in TERMINAL_STATUSES:
                raise ReviewConflictError("已处理的记录不可删除")
            s.execute(delete(ReviewDraft).where(ReviewDraft.case_id == i))
            s.execute(delete(ReviewDecision).where(ReviewDecision.case_id == i))
            s.execute(delete(ReviewEvidence).where(ReviewEvidence.case_id == i))
            s.execute(delete(ReviewAuditLog).where(ReviewAuditLog.case_id == i))
            s.delete(c)
            s.commit()
        return {"id": i, "deleted": True}

    def delete_cases(self, ids, a):
        """硬删除 T_EXTRACT_FAIL case（连同草稿/证据/裁决/审计记录），供失败列表清理。

        仅限 T_EXTRACT_FAIL——A 类入库决策 case 不走此通道；不存在或模板不符的
        id 跳过并在 skipped 里计数。删除不可恢复，调用方（前端）需自行二次确认。
        """
        require_role(a, "review_admin")
        wanted = list(dict.fromkeys(ids or []))
        if not wanted:
            return {"deleted": 0, "skipped": 0}
        with self.sf() as s:
            rows = s.scalars(
                select(ReviewCase).where(
                    ReviewCase.id.in_(wanted), ReviewCase.template_id == "T_EXTRACT_FAIL"
                )
            ).all()
            for c in rows:
                for model in (ReviewDraft, ReviewDecision, ReviewEvidence, ReviewAuditLog):
                    s.execute(delete(model).where(model.case_id == c.id))
                s.delete(c)
            s.commit()
        return {"deleted": len(rows), "skipped": len(wanted) - len(rows)}

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

    def case_dict(self, c):
        return {
            "id": c.id,
            "sourceTaskId": c.source_task_id,
            "batchId": c.batch_id,
            # 图谱构建ID：产生该 case 的抽取执行（EXEC-xxx，前端跳 /processing-instance）
            "executionId": (load(c.input_snapshot) or {}).get("executionId"),
            "workflowId": c.workflow_id,
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
                "duplicate": duplicate,
            }
        )
        return d


manual_review_service = ManualReviewService()
