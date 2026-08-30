"""平台角色、人工修正、可靠同步与管理审计模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


def _uuid() -> str:
    return str(uuid4())


class PlatformUser(Base):
    __tablename__ = "kg_platform_user"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    nickname: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PlatformUserRole(Base):
    __tablename__ = "kg_platform_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_code", name="uk_kg_platform_user_role"),
        Index("idx_kg_platform_user_role_code", "role_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("kg_platform_user.user_id", ondelete="CASCADE"), nullable=False
    )
    role_code: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class UserGraphSpace(Base):
    """用户与图空间的绑定关系。图空间本体在 NebulaGraph（trs-graph）侧管理，
    本表只记录"我的图空间"；解除绑定仅删除本表行，绝不 DROP 空间。"""

    __tablename__ = "kg_user_graph_space"
    __table_args__ = (
        UniqueConstraint("user_id", "space_name", name="uk_kg_user_graph_space"),
        Index("idx_kg_user_graph_space_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    space_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ManualCorrection(Base):
    __tablename__ = "kg_manual_correction"
    __table_args__ = (
        Index("idx_kg_manual_correction_submitter", "submitter_id", "created_at"),
        Index("idx_kg_manual_correction_status", "status", "updated_at"),
        Index("idx_kg_manual_correction_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW")
    submitter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    submitter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CorrectionReview(Base):
    __tablename__ = "kg_correction_review"
    __table_args__ = (Index("idx_kg_correction_review_correction", "correction_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    correction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kg_manual_correction.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class CorrectionSyncTask(Base):
    __tablename__ = "kg_correction_sync_task"
    __table_args__ = (
        UniqueConstraint("correction_id", name="uk_kg_correction_sync_correction"),
        UniqueConstraint("idempotency_key", name="uk_kg_correction_sync_idempotency"),
        Index("idx_kg_correction_sync_due", "status", "next_retry_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    correction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kg_manual_correction.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    mysql_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    graph_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CorrectionProjection(Base):
    __tablename__ = "kg_correction_projection"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uk_kg_correction_projection_target"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_correction_id: Mapped[str] = mapped_column(String(36), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AdminAuditLog(Base):
    __tablename__ = "kg_admin_audit_log"
    __table_args__ = (
        Index("idx_kg_admin_audit_actor", "actor_id", "created_at"),
        Index("idx_kg_admin_audit_resource", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
