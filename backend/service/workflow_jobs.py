"""任务中心"已创建任务"（Job）服务。

一个 Job = 一次性/周期性任务的完整配置（脚本选择 + 资源选择器 + 调度方式）。
每次触发（手动 or Schedule）产生 workflow_executions / tasks 行，execution 带
jobId 关联回 Job，详情页据此列出执行历史。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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
        owner = None if actor.is_admin else actor.user_id
        jobs = self.repo.list_jobs(name=name, status=status, task_type=task_type, owner=owner)
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
        from service.workflow_operations import workflow_operations_service

        task_type = request.get("taskType", "single")
        if task_type not in {"single", "chain", "upload", "extract"}:
            raise WorkflowJobError("任务类型必须是 single / chain / upload")
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
                load_extract_schema,
                persist_extract_definition,
            )

            try:
                info = load_extract_schema(schema_id)
            except Exception as exc:
                raise WorkflowJobError(str(exc)) from exc
            definition = persist_extract_definition(build_extract_definition(info))
        elif task_type == "chain":
            definition_ids = request.get("definitionIds") or []
            if len(definition_ids) < 2:
                raise WorkflowJobError("多脚本串行任务至少选择 2 个脚本")
            definition = workflow_operations_service.create_chain_definition(
                name, definition_ids, definition_id=f"chain-{job_hex}"
            )
        else:
            definition_id = request.get("definitionId")
            if not definition_id:
                raise WorkflowJobError("请选择脚本")
            definition = self.repo.get_definition(definition_id)
            if definition is None:
                raise WorkflowJobError(f"工作流定义不存在: {definition_id}")
            if task_type == "single" and definition.get("sourceKind") != "python":
                raise WorkflowJobError(f"任务脚本必须是 python 脚本定义: {definition_id}")

        schedule = request.get("schedule") or {"kind": "once"}
        if schedule.get("kind") not in {"once", "cron"}:
            raise WorkflowJobError("调度方式必须是 once / cron")
        if schedule["kind"] == "cron" and not schedule.get("cron"):
            raise WorkflowJobError("周期任务必须提供 cron 表达式")

        job: dict[str, Any] = {
            "id": f"job-{job_hex}",
            "name": name,
            "taskType": task_type,
            "definitionIds": request.get("definitionIds") or [definition["id"]],
            "definitionId": definition["id"],
            "definitionName": definition.get("name", definition["id"]),
            "schedule": schedule,
            "owner": actor.user_id,
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
            job["schemaId"] = schema_id
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
        from service.workflow_operations import workflow_operations_service

        job = self.get_job(actor, job_id)
        new_ids = request.get("definitionIds")
        if job["taskType"] == "chain" and new_ids and new_ids != job.get("definitionIds"):
            if len(new_ids) < 2:
                raise WorkflowJobError("多脚本串行任务至少选择 2 个脚本")
            definition = workflow_operations_service.create_chain_definition(
                request.get("name") or job["name"],
                new_ids,
                definition_id=job["definitionId"],  # 确定性 id，覆盖原链定义
            )
            job["definitionIds"] = new_ids
            job["definitionName"] = definition.get("name", definition["id"])
        if request.get("name"):
            job["name"] = request["name"].strip()
        for key in _SELECTOR_KEYS:
            if key in request:
                if request[key] in (None, ""):
                    job.pop(key, None)
                else:
                    job[key] = request[key]
        job["updatedAt"] = _now()

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

        self.repo.save_job(job)
        return job

    async def trigger_job(self, actor: PlatformActor, job_id: str) -> dict[str, Any]:
        from service.workflow_operations import workflow_operations_service

        job = self.get_job(actor, job_id)
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
        payload = self.selector_payload(job)
        payload["jobId"] = job["id"]
        payload["jobName"] = job["name"]
        if job.get("taskType") == "extract":
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
        # once 任务无 Schedule：暂停只是拒绝后续手动触发，正在运行的执行自然跑完
        job["status"] = "启用" if active else "暂停"
        job["updatedAt"] = _now()
        self.repo.save_job(job)
        return job

    async def delete_job(self, actor: PlatformActor, job_id: str) -> bool:
        job = self.get_job(actor, job_id)
        schedule_id = job.get("scheduleId")
        if schedule_id:
            try:
                await temporal_runtime.delete_schedule(schedule_id)
            except Exception:  # noqa: BLE001
                temporal_runtime._client = None
            self.repo.delete_schedule(schedule_id)
        # execution 历史保留（jobId 悬空无害），详情页删除后从任务列表入口不可达
        return self.repo.delete_job(job_id)

    # ---------- 辅助 ----------

    def selector_payload(self, job: dict[str, Any]) -> dict[str, Any]:
        """job 上的 camelCase 选择器 → workflow payload 的 snake_case 键。"""
        payload: dict[str, Any] = {}
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
        if actor.is_admin:
            return
        if (job.get("owner") or "") != actor.user_id:
            raise WorkflowJobPermissionError("无权访问他人任务")


workflow_job_service = WorkflowJobService()
