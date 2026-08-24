"""Temporal 客户端、Worker 与 Schedule 适配层。"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleState,
)
from temporalio.service import RPCError
from temporalio.worker import Worker

from service.temporal_workflows import ACTIVITIES, WORKFLOW_CLASSES


class TemporalRuntime:
    def __init__(self) -> None:
        self.address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
        self.namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
        self.task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "tech-kg-workflows")
        self._client: Client | None = None

    async def client(self) -> Client:
        if self._client is None:
            self._client = await Client.connect(self.address, namespace=self.namespace)
        return self._client

    async def health(self) -> dict[str, Any]:
        try:
            client = await self.client()
            healthy = await client.service_client.check_health()
            return {
                "status": "健康" if healthy else "异常",
                "address": self.address,
                "namespace": self.namespace,
                "taskQueue": self.task_queue,
                "message": "Temporal 连接正常" if healthy else "Temporal health check 未通过",
            }
        except Exception as exc:
            self._client = None
            return {
                "status": "不可用",
                "address": self.address,
                "namespace": self.namespace,
                "taskQueue": self.task_queue,
                "message": str(exc),
            }

    async def start(
        self, definition: dict[str, Any], payload: dict[str, Any], workflow_id: str | None = None
    ) -> dict[str, Any]:
        workflow_id = workflow_id or f"{definition['id']}-{uuid4().hex}"
        client = await self.client()
        workflow_payload = payload
        if definition.get("sourceKind") in {"python", "declarative"}:
            workflow_payload = {"definitionId": definition["id"], "payload": payload}
        handle = await client.start_workflow(
            definition["workflowType"],
            workflow_payload,
            id=workflow_id,
            task_queue=definition.get("taskQueue", self.task_queue),
        )
        return {
            "workflowId": workflow_id,
            "runId": getattr(handle, "first_execution_run_id", None),
            "status": "RUNNING",
        }

    async def refresh_execution(self, execution: dict[str, Any]) -> dict[str, Any]:
        if execution.get("dispatchMode") == "LOCAL_FALLBACK":
            return execution
        client = await self.client()
        handle = client.get_workflow_handle(execution["workflowId"], run_id=execution.get("runId"))
        try:
            description = await handle.describe()
        except RPCError as exc:
            # workflow 在当前 Temporal 上不存在（服务迁移/重置/重部署后丢失）。
            # 标记为 TERMINATED 让控制面把它当终态处理，避免 SQLite 卡在 RUNNING。
            if exc.status.value == 5:  # grpc.StatusCode.NOT_FOUND
                return {
                    **execution,
                    "status": "TERMINATED",
                    "completedAt": datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    "message": (
                        f"工作流在 Temporal 已不存在（{exc}）。"
                        "常见原因：Temporal 服务迁移/重置、或工作流在另一实例上运行。"
                    ),
                }
            raise
        status = description.status.name
        refreshed = {**execution, "status": status}
        if status == "RUNNING":
            return refreshed

        refreshed["completedAt"] = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if status == "COMPLETED":
            refreshed["output"] = await handle.result()
            refreshed["message"] = "工作流执行完成"
        else:
            try:
                await handle.result()
            except Exception as exc:
                refreshed["message"] = str(exc)
        return refreshed

    async def create_schedule(
        self, definition: dict[str, Any], schedule: dict[str, Any]
    ) -> dict[str, Any]:
        client = await self.client()
        schedule_id = schedule["id"]
        try:
            await client.get_schedule_handle(schedule_id).delete()
        except Exception:
            pass
        workflow_payload = schedule.get("payload", {})
        if definition.get("sourceKind") in {"python", "declarative"}:
            workflow_payload = {"definitionId": definition["id"], "payload": workflow_payload}
        await client.create_schedule(
            schedule_id,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    definition["workflowType"],
                    workflow_payload,
                    id=f"{schedule_id}-workflow",
                    task_queue=definition.get("taskQueue", self.task_queue),
                ),
                spec=ScheduleSpec(
                    cron_expressions=[schedule["cron"]],
                    time_zone_name=schedule.get("timezone", "Asia/Shanghai"),
                ),
                state=ScheduleState(paused=not schedule.get("active", True)),
            ),
        )
        return {**schedule, "dispatchStatus": "TEMPORAL_CREATED"}

    async def trigger_schedule(self, schedule_id: str) -> None:
        await (await self.client()).get_schedule_handle(schedule_id).trigger()

    async def pause_schedule(self, schedule_id: str, paused: bool) -> None:
        handle = (await self.client()).get_schedule_handle(schedule_id)
        if paused:
            await handle.pause(note="paused by tech-kg-api")
        else:
            await handle.unpause(note="resumed by tech-kg-api")

    async def delete_schedule(self, schedule_id: str) -> None:
        await (await self.client()).get_schedule_handle(schedule_id).delete()

    async def run_worker(self) -> None:
        client = await self.client()
        worker = Worker(
            client,
            task_queue=self.task_queue,
            workflows=WORKFLOW_CLASSES,
            activities=ACTIVITIES,
        )
        await worker.run()

    @staticmethod
    def execution_record(
        definition_id: str, dispatch: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": f"EXEC-{uuid4().hex[:16].upper()}",
            "definitionId": definition_id,
            "workflowId": dispatch["workflowId"],
            "runId": dispatch.get("runId"),
            "status": dispatch["status"],
            "startedAt": datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "completedAt": None,
            "payload": payload,
            "dispatchMode": dispatch.get("dispatchMode", "TEMPORAL"),
            "message": dispatch.get("message", "工作流已下发"),
        }


temporal_runtime = TemporalRuntime()
