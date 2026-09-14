"""任务中心与工作流定义的控制面仓库（temporal-mysql 的 techkg_control 库）。

原 SQLite 实现已迁至 SQLAlchemy ORM + MySQL（详见 service/workflow_models.py、
infra/workflow_mysql.py）。legacy 人工审核链（reviews 表）与 demo seed 数据
（_seed/_seed_tasks/_seed_reviews、WORKFLOW_DEMO_DATA_ENABLED、source_health
静态假数据）已于 2026-09-14 清理；生产审核走 service/manual_review_production.py。

ORM 模型不带 workflow_type UNIQUE 约束（kg.custom.python 多定义共享同一
workflow_type，原 SQLite 实现的 _remove_workflow_type_unique_constraint 即为
移除此约束，新 schema 直接不建）。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select

from infra.workflow_mysql import workflow_mysql_client, workflow_session_scope
from service.workflow_models import (
    Base,
    WorkflowBatch,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowJob,
    WorkflowSchedule,
    WorkflowSetting,
    WorkflowSourceUpdate,
    WorkflowTask,
)

SCHEMA_MAPPING_LABEL = "Schema 映射"


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class WorkflowRepository:
    """使用 SQLAlchemy ORM + MySQL 保存控制面数据，避免页面状态随进程重启丢失。"""

    def __init__(self, engine: Engine | None = None) -> None:
        # engine 仅用于测试注入；默认用全局 workflow_mysql_client.engine
        self._explicit_engine = engine
        self._initialize()

    @property
    def _engine(self) -> Engine:
        if self._explicit_engine is not None:
            return self._explicit_engine
        return workflow_mysql_client.engine

    def _initialize(self) -> None:
        # CREATE DATABASE IF NOT EXISTS 在 workflow_mysql_client.engine 首次访问时已做；
        # 这里只建表 + 注册 builtin 工作流定义。
        Base.metadata.create_all(self._engine)
        self._migrate_job_columns()
        self._migrate_schema_space_column()
        self._ensure_builtin_definitions()

    def _migrate_job_columns(self) -> None:
        """无迁移框架：对已有 workflow_executions 表幂等补 job_id 列（仅 MySQL 方言）。"""
        from sqlalchemy import inspect, text

        inspector = inspect(self._engine)
        if "workflow_executions" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("workflow_executions")}
        if "job_id" in columns:
            return
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE workflow_executions "
                    "ADD COLUMN job_id VARCHAR(255) NULL, "
                    "ADD INDEX ix_workflow_executions_job_id (job_id)"
                )
            )

    def _migrate_schema_space_column(self) -> None:
        """幂等为 kg_schema_definition 补 graph_space 列并把唯一键升级为 (col, space) 复合。

        存量行回填为当前环境的 TRS_GRAPH_SPACE；仅 MySQL 方言（SQLite 测试库走 create_all）。
        """
        from sqlalchemy import inspect, text

        inspector = inspect(self._engine)
        if "kg_schema_definition" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("kg_schema_definition")}
        if "graph_space" in columns:
            return
        default_space = os.getenv("TRS_GRAPH_SPACE", "techkg")
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE kg_schema_definition "
                    "ADD COLUMN graph_space VARCHAR(64) NOT NULL DEFAULT :space, "
                    "ADD INDEX idx_kg_schema_definition_space (graph_space), "
                    "DROP INDEX uk_kg_schema_definition_key, "
                    "ADD UNIQUE KEY uk_kg_schema_definition_key (schema_key, graph_space), "
                    "DROP INDEX uk_kg_schema_definition_name, "
                    "ADD UNIQUE KEY uk_kg_schema_definition_name (name, graph_space)"
                ),
                {"space": default_space},
            )

    def _ensure_builtin_definitions(self) -> None:
        """Idempotently insert built-in workflow definitions missing from older DBs.

        9 个域工作流 + graph-build 总工作流原由 demo seed 顺带注册；seed 删除后
        注册职责并到这里（graph-build 是 /task-center/trigger 与自动建图策略的
        执行目标，不是演示数据）。
        """
        builtins = [
            ("entity-paper", "kg.entity.paper", "entity", "论文实体工作流"),
            ("entity-scholar", "kg.entity.scholar", "entity", "人才实体工作流"),
            ("entity-patent", "kg.entity.patent", "entity", "专利实体工作流"),
            ("entity-organization", "kg.entity.organization", "entity", "机构实体工作流"),
            ("entity-project", "kg.entity.project", "entity", "国内外项目实体工作流"),
            ("relation-authorship", "kg.relation.authorship", "relation", "论文作者关系工作流"),
            ("relation-employment", "kg.relation.employment", "relation", "人才任职关系工作流"),
            ("relation-citation", "kg.relation.citation", "relation", "论文引用关系工作流"),
            ("relation-cooperation", "kg.relation.cooperation", "relation", "合作关系工作流"),
            ("graph-build", "kg.graph.build", "graph", "图谱构建总工作流"),
        ]
        with workflow_session_scope() as session:
            for definition_id, workflow_type, category, name in builtins:
                exists = session.scalar(
                    select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
                )
                if exists:
                    continue
                payload = {
                    "id": definition_id,
                    "name": name,
                    "workflowType": workflow_type,
                    "category": category,
                    "taskQueue": os.getenv("TEMPORAL_TASK_QUEUE", "tech-kg-workflows"),
                    "active": True,
                    "sourceKind": "builtin",
                    "steps": ["读取增量", "标准化", "抽取/对齐", "质量校验", "图谱写入"],
                    "createdAt": _now(),
                }
                session.add(
                    WorkflowDefinition(
                        id=definition_id,
                        workflow_type=workflow_type,
                        category=category,
                        active=1,
                        payload=_json(payload),
                    )
                )

    @staticmethod
    def _steps(blocking: str | None = None) -> list[dict[str, Any]]:
        # 兜底模板:任务刚创建(还未执行)时填的静态 7 步,字段都是编造的演示值
        # (count="1 个处理对象"、duration="6秒" 等)。
        # 终态后 _sync_task_from_execution 会用 normalize_stages(output)
        # 拿真实 worker stages 覆盖 task["steps"]。
        # TODO: 移除——等 seed 数据 / 新建任务流程能产出真实步骤模板后删掉。
        raw = [
            ("source", "数据接入", "数据处理", "读取业务域增量数据"),
            ("normalize", "清洗标准化", "数据处理", "执行字段、枚举和字典标准化"),
            ("schema", SCHEMA_MAPPING_LABEL, "图谱构建", "映射实体、关系与属性 Schema"),
            ("extract", "实体关系抽取", "图谱构建", "运行领域专属实体/关系工作流"),
            ("align", "实体对齐消歧", "图谱构建", "候选实体与存量图谱召回、消歧与合并"),
            ("validate", "质量校验", "图谱构建", "执行置信度、证据与唯一性校验"),
            ("persist", "图谱入库", "图谱构建", "幂等写入实体、关系和属性"),
        ]
        result = []
        blocked = False
        for step_id, name, phase, description in raw:
            if blocked:
                status = "待执行"
            elif step_id == blocking:
                status = "需人工处理"
                blocked = True
            else:
                status = "成功"
            result.append(
                {
                    "id": step_id,
                    "name": name,
                    "phase": phase,
                    "description": description,
                    "status": status,
                    "count": "1 个处理对象",
                    "abnormal": "1" if status == "需人工处理" else "0",
                    "duration": "未完成" if status != "成功" else "6秒",
                }
            )
        return result

    def list_batches(self) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            rows = session.scalars(
                select(WorkflowBatch).order_by(WorkflowBatch.update_date.desc())
            ).all()
            return [json.loads(row.payload) for row in rows]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowBatch).where(WorkflowBatch.id == batch_id))
            return json.loads(row.payload) if row else None

    def list_tasks(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowTask).order_by(WorkflowTask.processed_at.desc())
            mapping = {
                "stage": WorkflowTask.stage,
                "task_status": WorkflowTask.task_status,
                "domain": WorkflowTask.domain,
                "kind": WorkflowTask.kind,
                "batch_id": WorkflowTask.batch_id,
            }
            for key, column in mapping.items():
                value = filters.get(key)
                if value:
                    stmt = stmt.where(column == value)
            if filters.get("start_time"):
                stmt = stmt.where(WorkflowTask.processed_at >= filters["start_time"])
            if filters.get("end_time"):
                stmt = stmt.where(WorkflowTask.processed_at <= filters["end_time"])
            rows = session.scalars(stmt).all()
            items = [json.loads(row.payload) for row in rows]
        keyword = filters.get("keyword")
        if keyword:
            items = [item for item in items if keyword.lower() in _json(item).lower()]
        return items

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowTask).where(WorkflowTask.id == task_id))
            return json.loads(row.payload) if row else None

    def save_task(self, task: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowTask(
                    id=task["id"],
                    batch_id=task["batchId"],
                    stage=task["stage"],
                    task_status=task["taskStatus"],
                    domain=task["dataDomain"],
                    kind=task["kind"],
                    processed_at=task["processedAt"],
                    payload=_json(task),
                )
            )

    def list_source_updates(
        self, domain: str | None, since: str | None, until: str | None
    ) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowSourceUpdate).order_by(WorkflowSourceUpdate.detected_at.desc())
            if domain:
                stmt = stmt.where(WorkflowSourceUpdate.domain == domain)
            if since:
                stmt = stmt.where(WorkflowSourceUpdate.detected_at >= since)
            if until:
                stmt = stmt.where(WorkflowSourceUpdate.detected_at <= until)
            rows = session.scalars(stmt).all()
            return [json.loads(row.payload) for row in rows]

    def get_setting(self, key: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowSetting).where(WorkflowSetting.key == key))
            return json.loads(row.payload) if row else None

    def save_setting(self, key: str, payload: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(WorkflowSetting(key=key, payload=_json(payload)))

    def list_definitions(self, category: str | None = None) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowDefinition).order_by(
                WorkflowDefinition.category, WorkflowDefinition.id
            )
            if category:
                stmt = stmt.where(WorkflowDefinition.category == category)
            rows = session.scalars(stmt).all()
            return [json.loads(row.payload) for row in rows]

    def get_definition(self, definition_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
            )
            return json.loads(row.payload) if row else None

    def save_definition(self, definition: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowDefinition(
                    id=definition["id"],
                    workflow_type=definition["workflowType"],
                    category=definition["category"],
                    active=int(definition.get("active", True)),
                    payload=_json(definition),
                )
            )

    def save_execution(self, execution: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowExecution(
                    id=execution["id"],
                    definition_id=execution["definitionId"],
                    workflow_id=execution["workflowId"],
                    run_id=execution.get("runId"),
                    status=execution["status"],
                    started_at=execution["startedAt"],
                    job_id=execution.get("jobId"),
                    payload=_json(execution),
                )
            )

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
            )
            return json.loads(row.payload) if row else None

    def get_execution_by_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """按 workflowId 查 execution 行；retry reset 后用来回写新 runId。"""
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowExecution).where(WorkflowExecution.workflow_id == workflow_id)
            )
            return json.loads(row.payload) if row else None

    def get_execution_by_run(self, run_id: str) -> dict[str, Any] | None:
        """按 runId 查 execution 行（周期任务落库幂等判断）。"""
        with workflow_session_scope() as session:
            row = session.scalar(
                select(WorkflowExecution).where(WorkflowExecution.run_id == run_id)
            )
            return json.loads(row.payload) if row else None

    def list_executions(
        self,
        limit: int = 100,
        definition_id: str | None = None,
        schedule_id: str | None = None,
        job_id: str | None = None,
        trigger_source: str | None = None,
    ) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc())
            if definition_id:
                stmt = stmt.where(WorkflowExecution.definition_id == definition_id)
            if job_id:
                stmt = stmt.where(WorkflowExecution.job_id == job_id)
            # scheduleId/triggerSource 只存 payload JSON 里，取较多行后内存过滤；
            # 非 RERUN 执行超过 500 条时较旧的匹配会被截断（当前量小可接受）
            scan_limit = limit if not (schedule_id or trigger_source) else 500
            rows = session.scalars(stmt.limit(scan_limit)).all()
            items = [json.loads(row.payload) for row in rows]
            if schedule_id:
                items = [item for item in items if item.get("scheduleId") == schedule_id]
            if trigger_source:
                items = [item for item in items if item.get("triggerSource") == trigger_source]
            return items[:limit]

    def save_job(self, job: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowJob(
                    id=job["id"],
                    name=job["name"],
                    task_type=job["taskType"],
                    definition_id=job["definitionId"],
                    owner=job.get("owner", ""),
                    status=job.get("status", "启用"),
                    schedule_kind=(job.get("schedule") or {}).get("kind", "once"),
                    cron=(job.get("schedule") or {}).get("cron"),
                    created_at=job["createdAt"],
                    payload=_json(job),
                )
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowJob).where(WorkflowJob.id == job_id))
            return json.loads(row.payload) if row else None

    def list_jobs(
        self,
        name: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            stmt = select(WorkflowJob).order_by(WorkflowJob.created_at.desc())
            if name:
                stmt = stmt.where(WorkflowJob.name.like(f"%{name}%"))
            if status:
                stmt = stmt.where(WorkflowJob.status == status)
            if task_type:
                stmt = stmt.where(WorkflowJob.task_type == task_type)
            if owner:
                stmt = stmt.where(WorkflowJob.owner == owner)
            rows = session.scalars(stmt).all()
            return [json.loads(row.payload) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowJob).where(WorkflowJob.id == job_id))
            if row is None:
                return False
            session.delete(row)
            return True

    def save_schedule(self, schedule: dict[str, Any]) -> None:
        with workflow_session_scope() as session:
            session.merge(
                WorkflowSchedule(
                    id=schedule["id"],
                    definition_id=schedule["definitionId"],
                    active=int(schedule.get("active", True)),
                    payload=_json(schedule),
                )
            )

    def list_schedules(self) -> list[dict[str, Any]]:
        with workflow_session_scope() as session:
            rows = session.scalars(select(WorkflowSchedule).order_by(WorkflowSchedule.id)).all()
            return [json.loads(row.payload) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowSchedule).where(WorkflowSchedule.id == schedule_id))
            return json.loads(row.payload) if row else None

    def delete_schedule(self, schedule_id: str) -> bool:
        with workflow_session_scope() as session:
            row = session.scalar(select(WorkflowSchedule).where(WorkflowSchedule.id == schedule_id))
            if row is None:
                return False
            session.delete(row)
            return True

    def reset_for_tests(self) -> None:
        # 原 SQLite 实现是删 db 文件 + 重建；MySQL 下用 DROP+CREATE 全部表
        # （比 TRUNCATE 干净，避免自增列残留 + 兼容 schema 变更）
        url = self._engine.url
        if url.get_backend_name() != "sqlite" and os.getenv("WORKFLOW_RESET_ALLOW_REAL") != "1":
            raise RuntimeError(
                "reset_for_tests 会 DROP 共享库的全部控制面表（含 schema 目录），"
                "只允许临时 SQLite 引擎；确需重置真实库请设 WORKFLOW_RESET_ALLOW_REAL=1"
            )
        Base.metadata.drop_all(self._engine)
        Base.metadata.create_all(self._engine)
        self._initialize()


repository = WorkflowRepository()
