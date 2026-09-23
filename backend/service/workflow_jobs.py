"""任务中心"已创建任务"（Job）服务。

一个 Job = 一次性/周期性任务的完整配置（脚本选择 + 资源选择器 + 调度方式）。
每次触发（手动 or Schedule）产生 workflow_executions / tasks 行，execution 带
jobId 关联回 Job，详情页据此列出执行历史。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from service.business_access_control import (
    ensure_space_access,
    rbac_enabled,
)
from service.platform_access import PlatformActor
from service.temporal_runtime import temporal_runtime
from service.workflow_repository import repository

_SELECTOR_KEYS = (
    "llmConfigId",
    "embeddingConfigId",
    "mysqlDatasourceId",
    "mysqlDatabase",
    "milvusConfigId",
    "milvusDatabase",
    "graphSpace",
    "since",
)

# payload 内使用 snake_case（_resolve_resources 读取的键）
_SELECTOR_PAYLOAD_KEYS = {
    "llmConfigId": "llm_config_id",
    "embeddingConfigId": "embedding_config_id",
    "mysqlDatasourceId": "mysql_datasource_id",
    "mysqlDatabase": "mysql_database",
    "milvusConfigId": "milvus_config_id",
    "milvusDatabase": "milvus_database",
    "graphSpace": "graph_space",
    "since": "since",
}


def authorize_workflow_resource(actor, resource, action="read"):
    """Check persisted target spaces, including every schema in a chain.

    Missing scope in legacy records is deliberately administrator-only.
    """
    if not rbac_enabled():
        return
    if actor.business_only:
        raise HTTPException(status_code=403, detail="测试账号仅允许九大业务")
    if actor.is_admin and action == "read":
        return
    if action != "read" and not actor.can_develop:
        raise HTTPException(status_code=403, detail="当前角色无权维护构建任务")
    values = [resource]
    for key in ("payload", "input"):
        if isinstance(resource.get(key), dict):
            values.append(resource[key])
    persistent_record = any(
        key in resource
        for key in ("owner", "taskType", "workflowId", "payload", "input", "actorUserId", "jobId")
    )
    client_ids = {value.get("clientId") for value in values if value.get("clientId")}
    if not actor.is_admin and persistent_record and client_ids != {actor.business_id}:
        raise HTTPException(status_code=403, detail="任务尚未登记本业务归属，请由管理员重新保存")
    spaces = set()
    schema_ids = set()
    for value in values:
        if not actor.is_admin and value.get("clientId") and value["clientId"] != actor.business_id:
            raise HTTPException(status_code=403, detail="无权访问其他业务任务")
        for key in ("graphSpace", "graph_space"):
            if value.get(key):
                spaces.add(value[key])
        if value.get("schemaId"):
            schema_ids.add(value["schemaId"])
        schema_ids.update(value.get("schemaIds") or [])
        for step in value.get("steps") or []:
            if isinstance(step, dict) and step.get("schemaId"):
                schema_ids.add(step["schemaId"])
    if action != "read" and not actor.is_admin:
        from biz.dependencies.resources import ensure_owner_access
        from dao.embedding_config import EmbeddingConfigDAO
        from dao.llm_config import LlmConfigDAO
        from dao.milvus_config import MilvusConfigDAO
        from dao.mysql_datasource import MysqlDatasourceDAO
        from infra.mysql import session_scope

        config_types = (
            ("llmConfigId", "llm_config_id", LlmConfigDAO),
            ("embeddingConfigId", "embedding_config_id", EmbeddingConfigDAO),
            ("mysqlDatasourceId", "mysql_datasource_id", MysqlDatasourceDAO),
            ("milvusConfigId", "milvus_config_id", MilvusConfigDAO),
        )
        with session_scope() as session:
            for value in values:
                for camel, snake, dao_type in config_types:
                    for config_id in {value.get(camel), value.get(snake)} - {None, ""}:
                        row = dao_type(session).get(config_id)
                        if row is None:
                            raise HTTPException(status_code=403, detail="任务配置不存在或不可访问")
                        ensure_owner_access(actor, row.owner or "")
    explicit_spaces = set(spaces)
    if schema_ids:
        from dao.schema_management import SchemaManagementDAO
        from infra.workflow_mysql import workflow_session_scope

        with workflow_session_scope() as session:
            dao = SchemaManagementDAO(session)
            for schema_id in schema_ids:
                row = dao.get(schema_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="任务关联 Schema 不存在")
                if action != "read" and explicit_spaces and explicit_spaces != {row.graph_space}:
                    raise HTTPException(
                        status_code=403,
                        detail="目标空间必须与 Schema 所属空间一致，请选择目标空间的 Schema",
                    )
                spaces.add(row.graph_space)
    if not spaces and not actor.is_admin:
        raise HTTPException(status_code=403, detail="历史任务尚未登记图空间归属")
    for space in spaces:
        ensure_space_access(actor, space, action)


def _job_business(actor, resource):
    """Persist ownership from actual private spaces, never from creator membership."""
    from dao.schema_management import SchemaManagementDAO
    from db_model.business_access import BusinessGraphSpace
    from infra.mysql import session_scope
    from infra.workflow_mysql import workflow_session_scope

    spaces = {resource.get("graphSpace"), resource.get("graph_space")} - {None, ""}
    schema_ids = list(resource.get("schemaIds") or [])
    if resource.get("schemaId"):
        schema_ids.append(resource["schemaId"])
    if schema_ids:
        with workflow_session_scope() as session:
            for schema_id in schema_ids:
                row = SchemaManagementDAO(session).get(schema_id)
                if row:
                    spaces.add(row.graph_space)
    private_clients = set()
    unknown_space = False
    with session_scope() as session:
        for space in spaces:
            row = session.get(BusinessGraphSpace, space)
            if row is None or (not row.is_shared_production and not row.client_id):
                unknown_space = True
            if row and not row.is_shared_production and row.client_id:
                private_clients.add(row.client_id)
    if len(private_clients) > 1:
        raise HTTPException(403, "一个构建任务不能跨多个业务的私有空间")
    if unknown_space:
        return None
    return next(iter(private_clients)) if private_clients else actor.business_id or None


def authorize_background_execution(payload):
    """Re-resolve persisted users; a scheduled payload cannot grant itself a role."""
    if not rbac_enabled():
        return
    from sqlalchemy import select

    from config.auth import AuthSettings
    from db_model.platform_governance import PlatformUser, PlatformUserRole
    from infra.mysql import session_scope
    from service.business_access_control import resolve_membership
    from service.platform_access import ADMIN_ROLE

    user_id = str(payload.get("actorUserId") or "")
    if not user_id:
        raise HTTPException(status_code=403, detail="任务缺少执行身份，请由管理员重新保存任务")
    settings = AuthSettings.from_env()
    with session_scope() as session:
        user = session.get(PlatformUser, user_id)
        if user is None:
            raise HTTPException(status_code=403, detail="任务执行账号不存在")
        local_admin = (
            session.scalar(
                select(PlatformUserRole.id).where(
                    PlatformUserRole.user_id == user_id, PlatformUserRole.role_code == ADMIN_ROLE
                )
            )
            is not None
        )
        actor = PlatformActor(
            user_id=user_id,
            username=user.username or "",
            display_name=user.nickname or user.username or "",
            email=user.email or "",
            is_admin=local_admin or user_id in settings.initial_admin_user_ids,
            business_only=user_id in settings.business_only_user_ids,
        )
    from dataclasses import replace

    client_id, role = resolve_membership(user_id)
    actor = replace(actor, business_id=client_id, business_role=role)
    if not actor.can_develop:
        raise HTTPException(
            403, "执行账号缺少本地开发维护或管理员授权，请管理员核实业务成员及本地角色绑定"
        )
    if not actor.is_admin and payload.get("clientId") != client_id:
        raise HTTPException(status_code=403, detail="任务所属业务已变更，请重新保存任务")
    authorize_workflow_resource(actor, payload, "write")
    return actor


def workflow_resource_visible(actor, resource):
    try:
        authorize_workflow_resource(actor, resource)
        return True
    except HTTPException as exc:
        if exc.status_code not in (403, 404):
            raise
        return False


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


class WorkflowJobError(Exception):
    """Job 操作失败（参数/状态问题），handler 映射 400。"""


class WorkflowJobPermissionError(PermissionError):
    """跨用户访问 Job，handler 映射 403。"""


class WorkflowJobConflictError(WorkflowJobError):
    """任务当前状态不允许该操作（暂停中/执行中），handler 映射 409。"""


# 视为"仍在运行"的状态。QUEUED 是 Temporal 不可用时的本地待下发记录，
# 不会自愈，必须允许重新触发作为恢复手段，故不算运行中。
# CONTINUED_AS_NEW 同理不算：我们的 workflow 从不 continue-as-new，且所有
# 惰性刷新路径只认字面 RUNNING，把它算进运行中会永久 409 且无法自愈。
_NON_TERMINAL_RUNNING = {"RUNNING"}


class WorkflowJobService:
    def __init__(self, repo=repository) -> None:  # noqa: ANN001 — WorkflowRepository
        self.repo = repo

    # ---------- 查询 ----------

    async def list_jobs(
        self,
        actor: PlatformActor,
        name: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
    ) -> list[dict[str, Any]]:
        owner = None if actor.is_admin or rbac_enabled() else actor.user_id
        jobs = self.repo.list_jobs(name=name, status=status, task_type=task_type, owner=owner)
        if rbac_enabled():
            jobs = [job for job in jobs if workflow_resource_visible(actor, job)]
        await self._refresh_running_jobs(jobs)
        return jobs

    async def _refresh_running_jobs(self, jobs: list[dict[str, Any]], limit: int = 10) -> None:
        """列表里 lastExecutionStatus=RUNNING 的 job 惰性向 Temporal 复核（有界）。

        执行完成后只有 get_job_detail 会刷新，列表不刷会永久卡在"运行中"。
        """
        from service.workflow_operations import workflow_operations_service

        checked = 0
        for job in jobs:
            if checked >= limit:
                break
            if job.get("lastExecutionStatus") != "RUNNING" or not job.get("lastExecutionId"):
                continue
            checked += 1
            try:
                refreshed = await workflow_operations_service.get_execution(job["lastExecutionId"])
            except Exception:  # noqa: BLE001
                # Temporal/DB 不可用：继续循环只会每个 job 重建一次连接，直接放弃本次复核
                break
            if refreshed is not None and job["lastExecutionStatus"] != refreshed.get("status"):
                job["lastExecutionStatus"] = refreshed.get("status")
                # 跨 RPC 窗口内并发写（trigger/set_job_state）可能已更新 job；
                # 重新读一份只补 lastExecutionStatus，避免整包旧 payload 回滚并发写入
                current = self.repo.get_job(job["id"])
                if current is not None:
                    current["lastExecutionStatus"] = job["lastExecutionStatus"]
                    self.repo.save_job(current)

    def get_job(self, actor: PlatformActor, job_id: str) -> dict[str, Any]:
        job = self.repo.get_job(job_id)
        if job is None:
            raise WorkflowJobError(f"任务不存在: {job_id}")
        self._ensure_owner(actor, job)
        return job

    async def get_job_detail(self, actor: PlatformActor, job_id: str) -> dict[str, Any]:
        from service.workflow_operations import workflow_operations_service

        job = self.get_job(actor, job_id)
        executions = self.repo.list_executions(limit=200, job_id=job_id)
        if rbac_enabled():
            executions = [item for item in executions if workflow_resource_visible(actor, item)]
        latest = executions[0] if executions else None
        if latest and latest.get("status") == "RUNNING":
            # 惰性刷新最新一条（每 job 最多 1 次 Temporal RPC）
            try:
                refreshed = await workflow_operations_service.get_execution(latest["id"])
                if refreshed is not None:
                    executions[0] = refreshed
                    job["lastExecutionStatus"] = refreshed.get("status")
                    self.repo.save_job(job)
            except Exception:  # noqa: BLE001
                pass
        return {"job": job, "executions": executions}

    # ---------- 创建 / 编辑 / 删除 ----------

    async def create_job(self, actor: PlatformActor, request: dict[str, Any]) -> dict[str, Any]:
        if rbac_enabled():
            request = {**request, "clientId": _job_business(actor, request)}
        authorize_workflow_resource(actor, request, "write")
        task_type = request.get("taskType", "extract")
        if task_type not in {"extract", "chain"}:
            # single/upload 已随 D2 下线：脚本唯一通道是 Schema 管理。chain 为
            # 多 Schema 串行（kg.schema.extract.chain），串联对象同样是 Schema 脚本。
            raise WorkflowJobError("任务类型必须是 extract（数据抽取）或 chain（多脚本串行）")
        name = (request.get("name") or "").strip()
        if not name:
            raise WorkflowJobError("任务名称不能为空")

        job_hex = uuid4().hex[:12]
        if task_type == "extract":
            schema_id = request.get("schemaId")
            if not schema_id:
                raise WorkflowJobError("数据抽取任务必须选择 Schema")
            from service.schema_extraction import (
                build_extract_definition,
                ensure_extract_script_ready,
                persist_extract_definition,
            )

            # 预检：目录已登记脚本+来源，且脚本对象在 S3 真实存在（系统 Schema 的
            # 种子 script 行不传脚本本体，不预检的话要等 worker 重试耗尽才 FAILED）
            try:
                info = ensure_extract_script_ready(schema_id)
            except Exception as exc:
                raise WorkflowJobError(str(exc)) from exc
            definition = persist_extract_definition(build_extract_definition(info))
        else:
            infos = self._load_chain_infos(request.get("schemaIds"))
            from service.schema_extraction import (
                build_extract_chain_definition,
                persist_extract_chain_definition,
            )

            definition = persist_extract_chain_definition(
                build_extract_chain_definition(infos, f"chain-{job_hex}")
            )

        schedule = request.get("schedule") or {"kind": "once"}
        if schedule.get("kind") not in {"once", "cron"}:
            raise WorkflowJobError("调度方式必须是 once / cron")
        if schedule["kind"] == "cron" and not schedule.get("cron"):
            raise WorkflowJobError("周期任务必须提供 cron 表达式")

        job: dict[str, Any] = {
            "id": f"job-{job_hex}",
            "name": name,
            "taskType": task_type,
            "definitionIds": [definition["id"]],
            "definitionId": definition["id"],
            "definitionName": definition.get("name", definition["id"]),
            "schedule": schedule,
            "owner": actor.user_id,
            "executorUserId": actor.user_id,
            "clientId": request.get("clientId") if rbac_enabled() else actor.business_id,
            "status": "启用",
            "createdAt": _now(),
            "updatedAt": _now(),
            "lastRunAt": None,
            "lastExecutionId": None,
            "lastExecutionStatus": None,
        }
        for key in _SELECTOR_KEYS:
            if request.get(key) not in (None, ""):
                job[key] = request[key]
        if task_type == "extract":
            job["schemaId"] = request.get("schemaId")
        else:
            job["schemaIds"] = [step["schemaId"] for step in definition["steps"]]
            job["schemaLabels"] = [step["label"] for step in definition["steps"]]
        if request.get("batchSize"):
            job["batchSize"] = min(max(int(request["batchSize"]), 1), 5000)

        if schedule["kind"] == "cron":
            schedule_id = f"{job['id']}-sched"
            job["scheduleId"] = schedule_id
            await self._create_job_schedule(schedule_id, job, definition)

        self.repo.save_job(job)

        if request.get("runNow"):
            await self.trigger_job(actor, job["id"])
            job = self.repo.get_job(job["id"]) or job
        return job

    async def update_job(
        self, actor: PlatformActor, job_id: str, request: dict[str, Any]
    ) -> dict[str, Any]:
        job = self.get_job(actor, job_id)
        authorize_workflow_resource(actor, job, "write")
        authorize_workflow_resource(actor, {**job, **request}, "write")
        if request.get("name"):
            job["name"] = request["name"].strip()
        for key in _SELECTOR_KEYS:
            if key in request:
                if request[key] in (None, ""):
                    job.pop(key, None)
                else:
                    job[key] = request[key]
        job["updatedAt"] = _now()
        job["executorUserId"] = actor.user_id
        if rbac_enabled() and not job.get("clientId"):
            job["clientId"] = _job_business(actor, job)
        if rbac_enabled() and job.get("taskType") == "extract":
            from service.schema_extraction import (
                build_extract_definition,
                ensure_extract_script_ready,
                persist_extract_definition,
            )

            definition = persist_extract_definition(
                build_extract_definition(ensure_extract_script_ready(job["schemaId"]))
            )
            job["definitionId"] = definition["id"]
            job["definitionIds"] = [definition["id"]]
            job["definitionName"] = definition["name"]

        # chain 任务改步序：同 id 原地重建定义（只影响后续触发）
        if job.get("taskType") == "chain" and request.get("schemaIds") is not None:
            definition = await self._rebuild_chain_definition(job, request["schemaIds"])
            job["schemaIds"] = [step["schemaId"] for step in definition["steps"]]
            job["schemaLabels"] = [step["label"] for step in definition["steps"]]
            job["definitionName"] = definition.get("name", job.get("definitionName"))
            if job["schedule"].get("kind") == "cron" and job.get("scheduleId"):
                await self._create_job_schedule(job["scheduleId"], job, definition)

        new_schedule = request.get("schedule")
        if new_schedule and new_schedule.get("kind") != (job.get("schedule") or {}).get("kind"):
            raise WorkflowJobError("暂不支持切换调度方式，请新建任务")
        if new_schedule and job["schedule"].get("kind") == "cron":
            old_cron = job["schedule"].get("cron")
            if new_schedule.get("cron") and new_schedule["cron"] != old_cron:
                job["schedule"] = {**job["schedule"], "cron": new_schedule["cron"]}
                definition = self.repo.get_definition(job["definitionId"])
                if definition is not None:
                    await self._create_job_schedule(
                        job.get("scheduleId") or f"{job['id']}-sched", job, definition
                    )

        if rbac_enabled() and (job.get("schedule") or {}).get("kind") == "cron":
            definition = self.repo.get_definition(job["definitionId"])
            if definition is not None:
                await self._create_job_schedule(
                    job.get("scheduleId") or f"{job['id']}-sched", job, definition
                )
        self.repo.save_job(job)
        return job

    async def trigger_job(self, actor: PlatformActor, job_id: str) -> dict[str, Any]:
        from service.workflow_operations import workflow_operations_service

        job = self.get_job(actor, job_id)
        authorize_workflow_resource(actor, job, "write")
        if job.get("status") == "暂停":
            raise WorkflowJobConflictError("任务已暂停，请先恢复后再触发")
        if job.get("lastExecutionStatus") in _NON_TERMINAL_RUNNING and job.get("lastExecutionId"):
            # 惰性复核：列表里的 RUNNING 可能是执行完成后的过期状态。
            # 复核失败（DB/Temporal 异常）时退回已存状态判断，不让触发请求 500。
            try:
                latest = await workflow_operations_service.get_execution(job["lastExecutionId"])
                status = (latest or {}).get("status") or job["lastExecutionStatus"]
            except Exception:  # noqa: BLE001
                status = job["lastExecutionStatus"]
            if status in _NON_TERMINAL_RUNNING:
                raise WorkflowJobConflictError("上一次执行仍在进行中，请等待完成后再触发")
        definition = self.repo.get_definition(job["definitionId"])
        if definition is None:
            raise WorkflowJobError(f"任务脚本定义已丢失: {job['definitionId']}")
        if job.get("taskType") == "extract" and job.get("schemaId"):
            # 与 create_job 同款预检：脚本对象缺失（如系统 Schema 种子占位）时
            # 触发即报错，而不是下发后 worker 重试耗尽才 FAILED
            from service.schema_extraction import ensure_extract_script_ready

            try:
                ensure_extract_script_ready(job["schemaId"])
            except Exception as exc:
                raise WorkflowJobError(str(exc)) from exc
        payload = self.selector_payload(job)
        if rbac_enabled():
            payload["actorUserId"] = actor.user_id
            payload["clientId"] = job.get("clientId")
        payload["jobId"] = job["id"]
        payload["jobName"] = job["name"]
        if job.get("taskType") == "chain":
            from service.schema_extraction import CHAIN_WORKFLOW_TYPE

            if definition.get("workflowType") != CHAIN_WORKFLOW_TYPE:
                # 存量旧链任务（kg.custom.chain，D2 已下线通道）定义不可执行
                raise WorkflowJobError(
                    "该任务是旧版多脚本串行任务（旧脚本上传通道已下线），请删除后按 Schema 重新创建"
                )
            payload["schemaIds"] = job.get("schemaIds") or []
            payload["chainDefinitionId"] = job["definitionId"]
            payload["triggerSource"] = "MANUAL"
            if job.get("batchSize"):
                payload["batchSize"] = job["batchSize"]
        elif job.get("taskType") == "extract":
            payload["schemaId"] = job.get("schemaId")
            payload["triggerSource"] = "MANUAL"
            if job.get("batchSize"):
                payload["batchSize"] = job["batchSize"]
        execution = await workflow_operations_service.execute_definition(
            definition, payload, persist_task=True
        )
        self._stamp_latest(job, execution)
        return execution

    async def set_job_state(
        self, actor: PlatformActor, job_id: str, active: bool
    ) -> dict[str, Any]:
        job = self.get_job(actor, job_id)
        authorize_workflow_resource(actor, job, "write")
        if job["schedule"].get("kind") == "cron":
            schedule_id = job.get("scheduleId")
            if schedule_id:
                try:
                    await temporal_runtime.pause_schedule(schedule_id, paused=not active)
                    job["dispatchStatus"] = "TEMPORAL_UPDATED"
                except Exception as exc:  # noqa: BLE001
                    temporal_runtime._client = None
                    job["dispatchStatus"] = "LOCAL_SAVED"
                    job["message"] = str(exc)
        # once 任务无 Schedule：暂停同样生效——给运行中的执行发信号，当前步/环
        # 正常结束后挂起在下一步开始前（恢复信号后从挂起点继续），而非任其跑完
        job["status"] = "启用" if active else "暂停"
        job["updatedAt"] = _now()
        self.repo.save_job(job)
        execution_id = job.get("lastExecutionId")
        if execution_id and job.get("lastExecutionStatus") == "RUNNING":
            execution = self.repo.get_execution(execution_id)
            if execution and execution.get("workflowId"):
                try:
                    await temporal_runtime.signal_workflow(
                        execution["workflowId"],
                        execution.get("runId"),
                        "resume_extraction" if active else "pause_extraction",
                    )
                except Exception:  # noqa: BLE001
                    # 执行刚结束/Temporal 抖动：状态仍翻转成功，信号丢失无害
                    temporal_runtime._client = None
        return job

    async def delete_job(self, actor: PlatformActor, job_id: str) -> bool:
        job = self.get_job(actor, job_id)
        authorize_workflow_resource(actor, job, "write")
        schedule_id = job.get("scheduleId")
        if schedule_id:
            try:
                await temporal_runtime.delete_schedule(schedule_id)
            except Exception:  # noqa: BLE001
                temporal_runtime._client = None
            self.repo.delete_schedule(schedule_id)
        # 运行中的执行一并终止：步间暂停落地后，删除任务留下挂起的 workflow
        # 会永远等不到恢复信号，任务行卡在「执行中」。execution 历史行保留
        # （翻 CANCELED 供详情页展示），仅任务列表入口不可达。
        for execution in self.repo.list_executions(job_id=job_id):
            if execution.get("status") != "RUNNING" or not execution.get("workflowId"):
                continue
            try:
                await temporal_runtime.cancel_workflow(
                    execution["workflowId"], execution.get("runId")
                )
                execution["status"] = "CANCELED"
                execution["message"] = "任务已删除，执行终止"
                self.repo.save_execution(execution)
            except Exception:  # noqa: BLE001
                temporal_runtime._client = None
        return self.repo.delete_job(job_id)

    # ---------- 辅助 ----------

    def _load_chain_infos(self, schema_ids: Any) -> list[dict[str, Any]]:
        """校验 chain 步序列表并逐个加载可抽取 schema（已传脚本 + ≥1 来源 + S3 有脚本本体）。"""
        from service.schema_extraction import ensure_extract_script_ready

        if not isinstance(schema_ids, list) or len(schema_ids) < 2:
            raise WorkflowJobError("多脚本串行任务至少选择 2 个 Schema")
        if len(schema_ids) > 20:
            raise WorkflowJobError("多脚本串行任务最多选择 20 个 Schema")
        if len(set(schema_ids)) != len(schema_ids):
            raise WorkflowJobError("多脚本串行任务不能包含重复 Schema")
        infos: list[dict[str, Any]] = []
        for schema_id in schema_ids:
            try:
                infos.append(ensure_extract_script_ready(schema_id))
            except Exception as exc:
                raise WorkflowJobError(f"Schema {schema_id} 不可抽取: {exc}") from exc
        return infos

    async def _rebuild_chain_definition(
        self, job: dict[str, Any], schema_ids: Any
    ) -> dict[str, Any]:
        """用新的步序在同一定义 id 上原地重建 chain 定义。

        校验/构建/持久化均为同步阻塞操作（DB 读取 + Temporal RPC），
        卸载到线程执行，避免阻塞事件循环（Sonar S7503）。
        """

        def _rebuild() -> dict[str, Any]:
            from service.schema_extraction import (
                build_extract_chain_definition,
                persist_extract_chain_definition,
            )

            infos = self._load_chain_infos(schema_ids)
            return persist_extract_chain_definition(
                build_extract_chain_definition(infos, job["definitionId"])
            )

        return await asyncio.to_thread(_rebuild)

    def selector_payload(self, job: dict[str, Any]) -> dict[str, Any]:
        """job 上的 camelCase 选择器 → workflow payload 的 snake_case 键。"""
        payload: dict[str, Any] = {}
        if rbac_enabled():
            payload["actorUserId"] = job.get("executorUserId") or job.get("owner")
            payload["clientId"] = job.get("clientId")
        for camel, snake in _SELECTOR_PAYLOAD_KEYS.items():
            if job.get(camel) not in (None, ""):
                payload[snake] = job[camel]
        return payload

    async def _create_job_schedule(
        self, schedule_id: str, job: dict[str, Any], definition: dict[str, Any]
    ) -> None:
        schedule_payload = {**self.selector_payload(job), "jobId": job["id"]}
        if job.get("taskType") == "extract":
            # kg.schema.extract 收扁平 payload：schemaId/batchSize 直接并入
            schedule_payload["schemaId"] = job.get("schemaId")
            if job.get("batchSize"):
                schedule_payload["batchSize"] = job["batchSize"]
        elif job.get("taskType") == "chain":
            # chain 同为扁平 payload（sourceKind=extract）：schemaIds/chainDefinitionId 并入
            schedule_payload["schemaIds"] = job.get("schemaIds") or []
            schedule_payload["chainDefinitionId"] = job["definitionId"]
            if job.get("batchSize"):
                schedule_payload["batchSize"] = job["batchSize"]
        if rbac_enabled():
            authorize_background_execution(schedule_payload)
        schedule = {
            "id": schedule_id,
            "cron": job["schedule"]["cron"],
            "timezone": job["schedule"].get("timezone", "Asia/Shanghai"),
            "active": job.get("status", "启用") == "启用",
            "payload": schedule_payload,
            "definitionId": definition["id"],
            "jobId": job["id"],
        }
        try:
            schedule = await temporal_runtime.create_schedule(definition, schedule)
        except Exception as exc:  # noqa: BLE001
            temporal_runtime._client = None
            schedule["dispatchStatus"] = "LOCAL_SAVED"
            schedule["message"] = str(exc)
        self.repo.save_schedule(schedule)

    def _stamp_latest(self, job: dict[str, Any], execution: dict[str, Any]) -> None:
        job["lastRunAt"] = execution.get("startedAt")
        job["lastExecutionId"] = execution.get("id")
        job["lastExecutionStatus"] = execution.get("status")
        job["updatedAt"] = _now()
        self.repo.save_job(job)

    def _ensure_owner(self, actor: PlatformActor, job: dict[str, Any]) -> None:
        if rbac_enabled():
            authorize_workflow_resource(actor, job)
            return
        if actor.is_admin:
            return
        if (job.get("owner") or "") != actor.user_id:
            raise WorkflowJobPermissionError("无权访问他人任务")


workflow_job_service = WorkflowJobService()
