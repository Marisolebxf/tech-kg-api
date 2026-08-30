"""控制面 ORM 模型（temporal-mysql 的 techkg_control 库）。

跟 db_model/*（业务库 gkx_element）解耦——独立的 Base、独立的 engine，
schema 迁移互不影响。表结构与原 SQLite 实现等价，仅做方言翻译：
- TEXT PRIMARY KEY → VARCHAR(255) PRIMARY KEY
- TEXT (JSON) → LONGTEXT（MySQL TEXT 仅 64KB，原 SQLite TEXT 无上限）
- INTEGER PRIMARY KEY AUTOINCREMENT → INTEGER PRIMARY KEY AUTO_INCREMENT
- workflow_type 不带 UNIQUE（kg.custom.python 多定义共享同一 workflow_type）
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkflowBatch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    update_date: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowTask(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowReview(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowSourceUpdate(Base):
    __tablename__ = "source_updates"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detected_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    # workflow_type 不带 UNIQUE：kg.custom.python 多个定义共享同一 workflow_type
    # （原 SQLite 实现的 _remove_workflow_type_unique_constraint 即为移除此约束）
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowSchedule(Base):
    __tablename__ = "workflow_schedules"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    active: Mapped[str] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


class WorkflowJob(Base):
    """任务中心里的"已创建任务"（一次性 / 周期性）。

    payload 为全量 JSON 记录（camelCase），列字段仅用于过滤。
    """

    __tablename__ = "workflow_jobs"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    definition_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    schedule_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(LONGTEXT, nullable=False)


__all__ = [
    "Base",
    "WorkflowBatch",
    "WorkflowDefinition",
    "WorkflowExecution",
    "WorkflowJob",
    "WorkflowReview",
    "WorkflowSchedule",
    "WorkflowSetting",
    "WorkflowSourceUpdate",
    "WorkflowTask",
]
