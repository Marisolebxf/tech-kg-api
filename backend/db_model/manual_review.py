"""Production manual-review persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db_model.base import Base


class ReviewCase(Base):
    __tablename__ = "manual_review_case"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uk_manual_review_case_dedupe"),
        Index("ix_review_queue", "status", "risk_level", "domain", "created_at"),
        Index("ix_review_assignee", "assignee_id", "status"),
        Index("ix_review_graph_space", "graph_space"),
        # 队列按 category（template_id 集合）+ status 过滤再按时间排序/计数：
        # 无 template_id 索引时跨空间查询全表扫描（50 万行实测 count+分页约 3s）
        Index("ix_review_template", "template_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_space: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    source_task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(128))
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 抽取消歧用 "source:{绑定行uuid}" 形式的 step id（44 字符），32 放不下会
    # 让 T_LINK case 创建整条失败
    pipeline_step_id: Mapped[str] = mapped_column(String(128), nullable=False)
    object_id: Mapped[str] = mapped_column(String(256), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_name: Mapped[str] = mapped_column(String(500), nullable=False)
    error_type: Mapped[str] = mapped_column(String(128), nullable=False)
    error_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    template_id: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(128))
    assignee_name: Mapped[str | None] = mapped_column(String(128))
    submitted_by: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sla_claim_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sla_resolve_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    source_table: Mapped[str | None] = mapped_column(String(256))
    source_record_id: Mapped[str | None] = mapped_column(String(256))
    rule_version: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(128))
    workflow_type: Mapped[str | None] = mapped_column(String(128))
    workflow_id: Mapped[str | None] = mapped_column(String(256))
    workflow_run_id: Mapped[str | None] = mapped_column(String(256))
    task_queue: Mapped[str | None] = mapped_column(String(128))
    resume_token: Mapped[str | None] = mapped_column(String(1000))
    exception_code: Mapped[str | None] = mapped_column(String(128))
    isolation_scope: Mapped[str] = mapped_column(String(16), default="OBJECT", nullable=False)
    template_payload_version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    input_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    # 来源账本计数（gray-gate-v2）：不同来源总数 / 未存 evidence 的截断来源数。
    # 逻辑计数由 manual_review_case_source 行数维护（追加事务内 UPDATE），
    # 不进快照不进 dedupe 哈希（快照哈希稳定性契约）。
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_truncated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewCaseSource(Base):
    """T_LINK 案来源行（gray-gate-v2）：一笔源事件对一案的幂等追加账本。

    唯一键 ``(case_id, execution_id, source_record_id)``——同一执行的同一源
    记录重放（activity 重试/失败重跑）命中唯一键冲突整体回滚、不加计；
    ``execution_id`` 只作来源行审计字段，不进逻辑 ingress identity 键。
    ``evidence`` 只存字段名与布尔（≤2KB，零业务值）；前 32 个来源带 evidence，
    之后的行仍插入（truncated=true 语义靠 evidence 为空 + 计数表达），明细行
    如实无界（rows_per_case p99 监控 + 1024 行 advisory 告警转人工）。
    """

    __tablename__ = "manual_review_case_source"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "execution_id", "source_record_id", name="uk_review_case_source"
        ),
        Index("ix_review_case_source_case", "case_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # '' 代替 NULL（唯一键含 NULL 不去重）；无执行上下文（单测直调）也是 ''
    execution_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_binding_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_event_version: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewVerdictApplication(Base):
    """T_LINK 裁决应用标记（gray-gate-v2）：priorVerdict.applyStatus 的耐久落点。

    四态：``NOT_REQUIRED``（reject 等无需图写，可安全重放）/ ``APPLIED``
    （图写确认，可幂等重放）/ ``FAILED``（图写失败，失败关闭人工重应用）/
    ``UNKNOWN``（两段提交的意图标记初值——崩溃窗口收敛态；存量旧案缺整行
    也按 UNKNOWN 对待，不得从 RESOLVED/APPROVED 猜测）。两段提交边界：
    Tx1 决议+意图标记（reject 直接 NOT_REQUIRED）→ 图写 → Tx2 改 APPLIED/FAILED。
    ``canonical_vid``=merge 目标；``reserved_vid``=create 预留 vid——重放
    rewrite_to_canonical 只读本表（查无抛 MERGE_CANONICAL_MISSING）。
    """

    __tablename__ = "manual_review_verdict_application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    decision_id: Mapped[int | None] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    apply_status: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_vid: Mapped[str | None] = mapped_column(String(256))
    reserved_vid: Mapped[str | None] = mapped_column(String(256))
    error_code: Mapped[str | None] = mapped_column(String(64))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewDraft(Base):
    __tablename__ = "manual_review_draft"
    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewDecision(Base):
    __tablename__ = "manual_review_decision"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class ReviewEvidence(Base):
    __tablename__ = "manual_review_evidence"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    trust_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewAuditLog(Base):
    __tablename__ = "manual_review_audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
