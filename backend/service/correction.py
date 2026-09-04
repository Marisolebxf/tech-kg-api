"""人工修正账本、审核状态机和 MySQL/图库可靠同步。"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from db_model.platform_governance import (
    AdminAuditLog,
    CorrectionProjection,
    CorrectionReview,
    CorrectionSyncTask,
    ManualCorrection,
)
from infra.graph_db import TRSGraphClient, get_techkg_client
from service.platform_access import PlatformActor

PENDING_REVIEW = "PENDING_REVIEW"
PENDING_SYNC = "PENDING_SYNC"
SYNC_FAILED = "SYNC_FAILED"
COMPLETED = "COMPLETED"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"

logger = logging.getLogger(__name__)

_EDGE_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class CorrectionService:
    def __init__(
        self,
        session: Session,
        graph_factory: Callable[[], TRSGraphClient] = get_techkg_client,
        sync_mode: str | None = None,
    ) -> None:
        self.session = session
        self.graph_factory = graph_factory
        configured_mode = (
            (sync_mode or os.getenv("CORRECTION_SYNC_MODE", "projection")).strip().lower()
        )
        if configured_mode not in {"projection", "dual"}:
            raise ValueError("CORRECTION_SYNC_MODE 只支持 projection 或 dual")
        self.sync_mode = configured_mode

    def create(self, payload: dict[str, Any], actor: PlatformActor) -> dict[str, Any]:
        correction = ManualCorrection(
            **payload,
            status=PENDING_REVIEW,
            submitter_id=actor.user_id,
            submitter_name=actor.display_name,
        )
        self.session.add(correction)
        self.session.flush()
        self._review(correction, "SUBMIT", actor, "提交人工修正申请")
        self._audit(actor, "CREATE_CORRECTION", correction.id, {"status": correction.status})
        return self.detail(correction, include_history=True)

    def list(
        self,
        actor: PlatformActor,
        *,
        all_users: bool = False,
        status: str | None = None,
        statuses: tuple[str, ...] = (),
        target_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        conditions = []
        if not (all_users and actor.is_admin):
            conditions.append(ManualCorrection.submitter_id == actor.user_id)
        if status:
            conditions.append(ManualCorrection.status == status)
        elif statuses:
            conditions.append(ManualCorrection.status.in_(statuses))
        if target_type:
            conditions.append(ManualCorrection.target_type == target_type)
        if keyword:
            value = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    ManualCorrection.title.like(value),
                    ManualCorrection.target_id.like(value),
                    ManualCorrection.reason.like(value),
                    ManualCorrection.submitter_name.like(value),
                )
            )
        size = min(max(page_size, 1), 100)
        current_page = max(page, 1)
        total = (
            self.session.scalar(
                select(func.count()).select_from(ManualCorrection).where(*conditions)
            )
            or 0
        )
        count_rows = self.session.execute(
            select(ManualCorrection.status, func.count())
            .where(*conditions)
            .group_by(ManualCorrection.status)
        ).all()
        rows = self.session.scalars(
            select(ManualCorrection)
            .where(*conditions)
            .order_by(ManualCorrection.created_at.desc(), ManualCorrection.id.desc())
            .offset((current_page - 1) * size)
            .limit(size)
        ).all()
        return {
            "items": [self.detail(item) for item in rows],
            "total": total,
            "page": current_page,
            "pageSize": size,
            "statusCounts": dict(count_rows),
        }

    def get(self, correction_id: str, actor: PlatformActor) -> dict[str, Any]:
        return self.detail(self._get_owned(correction_id, actor), include_history=True)

    def update(
        self, correction_id: str, payload: dict[str, Any], actor: PlatformActor
    ) -> dict[str, Any]:
        correction = self._get_owned(correction_id, actor)
        if correction.status != PENDING_REVIEW:
            raise ValueError("只有待审核记录可以修改")
        for key, value in payload.items():
            if value is not None:
                setattr(correction, key, value)
        if correction.operation != "delete" and not correction.after_data:
            raise ValueError("新增或修改必须填写修正后的数据")
        correction.version += 1
        self._review(correction, "EDIT", actor, "修改待审核修正记录")
        self._audit(actor, "UPDATE_CORRECTION", correction.id, {"version": correction.version})
        self.session.flush()
        return self.detail(correction, include_history=True)

    def cancel(self, correction_id: str, actor: PlatformActor) -> dict[str, Any]:
        correction = self._get_owned(correction_id, actor)
        if correction.status != PENDING_REVIEW:
            raise ValueError("只有待审核记录可以撤销")
        correction.status = CANCELLED
        self._review(correction, "CANCEL", actor, "撤销人工修正申请")
        self._audit(actor, "CANCEL_CORRECTION", correction.id, {})
        self.session.flush()
        return self.detail(correction, include_history=True)

    def decide(
        self,
        correction_id: str,
        decision: str,
        note: str,
        actor: PlatformActor,
    ) -> dict[str, Any]:
        correction = self._get(correction_id)
        if correction.status != PENDING_REVIEW:
            raise ValueError("该记录已处理，不能重复审核")
        if decision == "reject" and not note.strip():
            raise ValueError("驳回时必须填写原因")
        correction.reviewer_id = actor.user_id
        correction.reviewer_name = actor.display_name
        correction.reviewed_at = _now()
        correction.decision_note = note.strip()
        if decision == "reject":
            correction.status = REJECTED
            self._review(correction, "REJECT", actor, note)
            self._audit(actor, "REJECT_CORRECTION", correction.id, {"note": note})
            self.session.flush()
            return self.detail(correction, include_history=True)

        correction.status = PENDING_SYNC
        task = self.session.scalar(
            select(CorrectionSyncTask).where(CorrectionSyncTask.correction_id == correction.id)
        )
        if task is None:
            task = CorrectionSyncTask(
                correction_id=correction.id,
                idempotency_key=f"correction:{correction.id}:v{correction.version}",
                max_attempts=max(1, int(os.getenv("CORRECTION_SYNC_MAX_ATTEMPTS", "8"))),
            )
            self.session.add(task)
        self._review(correction, "APPROVE", actor, note or "审核通过")
        self._audit(actor, "APPROVE_CORRECTION", correction.id, {"note": note})
        self.session.flush()
        return self.detail(correction, include_history=True)

    def retry(self, correction_id: str, note: str, actor: PlatformActor) -> dict[str, Any]:
        correction = self._get(correction_id)
        task = self.session.scalar(
            select(CorrectionSyncTask).where(CorrectionSyncTask.correction_id == correction.id)
        )
        if task is None or correction.status not in {SYNC_FAILED, PENDING_SYNC}:
            raise ValueError("该记录当前不需要重新同步")
        task.status = "PENDING"
        task.attempts = 0
        task.next_retry_at = None
        task.last_error = ""
        correction.status = PENDING_SYNC
        self._review(correction, "RETRY", actor, note or "管理员手动重试")
        self._audit(actor, "RETRY_CORRECTION", correction.id, {"note": note})
        self.session.flush()
        return self.detail(correction, include_history=True)

    def process_task(self, task_id: str) -> None:
        task = self.session.get(CorrectionSyncTask, task_id)
        if task is None or task.status == "SUCCEEDED":
            return
        correction = self._get(task.correction_id)
        task.status = "PROCESSING"
        task.attempts += 1
        task.next_retry_at = None
        self.session.flush()
        try:
            self._apply_mysql_projection(correction)
            task.mysql_status = "SUCCEEDED"
            self.session.flush()
        except Exception as exc:  # noqa: BLE001 - 失败必须持久化后重试
            task.mysql_status = "FAILED"
            if self.sync_mode == "projection":
                task.graph_status = "SKIPPED"
            self._schedule_failure(task, correction, exc)
            self.session.flush()
            return

        if self.sync_mode == "projection":
            task.graph_status = "SKIPPED"
            self._complete_task(task, correction, "修正投影已落库，业务数据保持隔离")
            self.session.flush()
            return

        try:
            self._apply_graph_projection(correction)
            task.graph_status = "SUCCEEDED"
            self._complete_task(task, correction, "MySQL 与图库同步完成")
        except Exception as exc:  # noqa: BLE001 - 失败必须持久化后重试
            task.graph_status = "FAILED"
            self._schedule_failure(task, correction, exc)
        self.session.flush()

    def _complete_task(
        self,
        task: CorrectionSyncTask,
        correction: ManualCorrection,
        note: str,
    ) -> None:
        task.status = "SUCCEEDED"
        task.last_error = ""
        task.next_retry_at = None
        correction.status = COMPLETED
        correction.completed_at = _now()
        self._review(correction, "SYNC_SUCCEEDED", self._system_actor(), note)

    @staticmethod
    def _schedule_failure(
        task: CorrectionSyncTask,
        correction: ManualCorrection,
        exc: Exception,
    ) -> None:
        task.last_error = str(exc)[:2000]
        correction.status = SYNC_FAILED
        if task.attempts >= task.max_attempts:
            task.status = "FAILED"
            task.next_retry_at = None
        else:
            task.status = "RETRYING"
            seconds = min(3600, 30 * (2 ** max(0, task.attempts - 1)))
            task.next_retry_at = _now() + timedelta(seconds=seconds)

    def _apply_mysql_projection(self, correction: ManualCorrection) -> None:
        projection = self.session.scalar(
            select(CorrectionProjection).where(
                CorrectionProjection.target_type == correction.target_type,
                CorrectionProjection.target_id == correction.target_id,
            )
        )
        if projection is not None and projection.last_correction_id == correction.id:
            return
        if projection is None:
            projection = CorrectionProjection(
                target_type=correction.target_type,
                target_id=correction.target_id,
                payload={},
                active=True,
                version=0,
                last_correction_id=correction.id,
            )
            self.session.add(projection)
        if correction.operation == "create":
            projection.payload = dict(correction.after_data)
            projection.active = True
        elif correction.operation == "update":
            projection.payload = {**dict(projection.payload or {}), **dict(correction.after_data)}
            projection.active = True
        else:
            projection.active = False
        projection.version += 1
        projection.last_correction_id = correction.id

    def _apply_graph_projection(self, correction: ManualCorrection) -> None:
        graph = self.graph_factory()
        if correction.target_type in {"expert", "organization"}:
            self._apply_graph_node(graph, correction)
        else:
            self._apply_graph_relation(graph, correction)

    @staticmethod
    def _apply_graph_node(graph: TRSGraphClient, correction: ManualCorrection) -> None:
        label = "Scholar" if correction.target_type == "expert" else "Organization"
        metadata = {
            "manual_disabled": correction.operation == "delete",
            "correction_id": correction.id,
            "corrected_at": _now().isoformat(),
        }
        if correction.operation == "delete":
            if graph.get_node(correction.target_id) is None:
                return
            graph.update_node(correction.target_id, metadata)
            return
        identity_key = "scholar_id" if label == "Scholar" else "org_id"
        properties = {
            identity_key: correction.target_id,
            **dict(correction.after_data),
            **metadata,
        }
        graph.merge_node(
            [label],
            {identity_key: correction.target_id},
            properties,
        )

    @staticmethod
    def _apply_graph_relation(graph: TRSGraphClient, correction: ManualCorrection) -> None:
        payload = {**dict(correction.before_data or {}), **dict(correction.after_data or {})}
        source_id = str(payload.get("sourceId") or payload.get("source_id") or "")
        target_id = str(payload.get("targetId") or payload.get("target_id") or "")
        edge_type = str(payload.get("edgeType") or payload.get("edge_type") or "")
        if not source_id or not target_id or not _EDGE_TYPE.fullmatch(edge_type):
            raise ValueError("关系修正必须包含合法的 sourceId、targetId 和 edgeType")
        if edge_type != "EMPLOYED_BY":
            raise ValueError("首期关系修正仅支持专家与机构的 EMPLOYED_BY 关系")
        edge_id = (
            correction.target_id
            if "->" in correction.target_id and "@" in correction.target_id
            else f"{source_id}->{target_id}@0"
        )
        metadata = {
            "manual_disabled": correction.operation == "delete",
            "correction_id": correction.id,
            "corrected_at": _now().isoformat(),
        }
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            properties = {
                key: value
                for key, value in correction.after_data.items()
                if key
                not in {
                    "sourceId",
                    "source_id",
                    "targetId",
                    "target_id",
                    "edgeType",
                    "edge_type",
                }
            }
        properties = {**properties, **metadata}
        if correction.operation == "create":
            graph.merge_edge(
                source_id,
                target_id,
                edge_type,
                {"correction_id": correction.id},
                properties,
            )
        else:
            graph.update_edge(edge_id, properties, edge_type=edge_type)

    def detail(
        self, correction: ManualCorrection, *, include_history: bool = False
    ) -> dict[str, Any]:
        task = self.session.scalar(
            select(CorrectionSyncTask).where(CorrectionSyncTask.correction_id == correction.id)
        )
        result: dict[str, Any] = {
            "id": correction.id,
            "targetType": correction.target_type,
            "operation": correction.operation,
            "targetId": correction.target_id,
            "title": correction.title,
            "reason": correction.reason,
            "beforeData": correction.before_data or {},
            "afterData": correction.after_data or {},
            "status": correction.status,
            "submitterId": correction.submitter_id,
            "submitterName": correction.submitter_name,
            "reviewerId": correction.reviewer_id,
            "reviewerName": correction.reviewer_name,
            "decisionNote": correction.decision_note,
            "version": correction.version,
            "submittedAt": _iso(correction.submitted_at),
            "reviewedAt": _iso(correction.reviewed_at),
            "completedAt": _iso(correction.completed_at),
            "updatedAt": _iso(correction.updated_at),
            "sync": self._task_dict(task),
        }
        if include_history:
            action_order = case(
                (CorrectionReview.action == "SUBMIT", 0),
                (CorrectionReview.action == "EDIT", 10),
                (CorrectionReview.action.in_(["APPROVE", "REJECT", "CANCEL"]), 20),
                (CorrectionReview.action == "RETRY", 30),
                (CorrectionReview.action == "SYNC_SUCCEEDED", 40),
                else_=50,
            )
            reviews = self.session.scalars(
                select(CorrectionReview)
                .where(CorrectionReview.correction_id == correction.id)
                .order_by(
                    CorrectionReview.created_at.asc(),
                    action_order.asc(),
                    CorrectionReview.id.asc(),
                )
            ).all()
            result["history"] = [
                {
                    "id": review.id,
                    "action": review.action,
                    "actorId": review.actor_id,
                    "actorName": review.actor_name,
                    "note": review.note,
                    "createdAt": _iso(review.created_at),
                }
                for review in reviews
            ]
        return result

    @staticmethod
    def _task_dict(task: CorrectionSyncTask | None) -> dict[str, Any] | None:
        if task is None:
            return None
        return {
            "id": task.id,
            "status": task.status,
            "mysqlStatus": task.mysql_status,
            "graphStatus": task.graph_status,
            "attempts": task.attempts,
            "maxAttempts": task.max_attempts,
            "nextRetryAt": _iso(task.next_retry_at),
            "lastError": task.last_error,
        }

    def _get(self, correction_id: str) -> ManualCorrection:
        correction = self.session.get(ManualCorrection, correction_id)
        if correction is None:
            raise KeyError(correction_id)
        return correction

    def _get_owned(self, correction_id: str, actor: PlatformActor) -> ManualCorrection:
        correction = self._get(correction_id)
        if not actor.is_admin and correction.submitter_id != actor.user_id:
            raise PermissionError(correction_id)
        return correction

    def _review(
        self, correction: ManualCorrection, action: str, actor: PlatformActor, note: str
    ) -> None:
        self.session.add(
            CorrectionReview(
                correction_id=correction.id,
                action=action,
                actor_id=actor.user_id,
                actor_name=actor.display_name,
                note=note,
                snapshot={"status": correction.status, "version": correction.version},
            )
        )

    def _audit(
        self, actor: PlatformActor, action: str, resource_id: str, detail: dict[str, Any]
    ) -> None:
        self.session.add(
            AdminAuditLog(
                actor_id=actor.user_id,
                actor_name=actor.display_name,
                action=action,
                resource_type="manual_correction",
                resource_id=resource_id,
                detail=detail,
            )
        )

    @staticmethod
    def _system_actor() -> PlatformActor:
        return PlatformActor(
            user_id="system",
            username="system",
            display_name="同步服务",
            email="",
            is_admin=True,
        )


def process_due_sync_tasks(
    session: Session,
    *,
    limit: int = 20,
    graph_factory: Callable[[], TRSGraphClient] = get_techkg_client,
    sync_mode: str | None = None,
) -> int:
    now = _now()
    tasks = session.scalars(
        select(CorrectionSyncTask)
        .where(
            CorrectionSyncTask.status.in_(["PENDING", "RETRYING"]),
            or_(
                CorrectionSyncTask.next_retry_at.is_(None),
                CorrectionSyncTask.next_retry_at <= now,
            ),
        )
        .order_by(CorrectionSyncTask.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    service = CorrectionService(session, graph_factory=graph_factory, sync_mode=sync_mode)
    for task in tasks:
        service.process_task(task.id)
    return len(tasks)
