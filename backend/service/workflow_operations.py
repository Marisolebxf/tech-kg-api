"""任务中心、人工审核和 Temporal 控制面的业务服务。"""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from service.temporal_runtime import temporal_runtime
from service.workflow_repository import WorkflowRepository, repository

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _domain_label(domains: list[str]) -> str:
    normalized = [item.strip().removesuffix("域") for item in domains if item.strip()]
    return f"{'、'.join(dict.fromkeys(normalized))}域" if normalized else "综合数据域"


def _task_kind(entities: list[str], relations: list[str]) -> str:
    if entities and relations:
        return "实体与关系"
    if relations:
        return "关系"
    if entities:
        return "实体"
    return "工作流"


class WorkflowOperationsService:
    def __init__(self, repo: WorkflowRepository = repository) -> None:
        self.repo = repo

    def task_overview(self) -> dict[str, Any]:
        tasks = self.repo.list_tasks({})
        batches = self.repo.list_batches()
        latest_batch = batches[0] if batches else None
        latest_tasks = [
            item for item in tasks if not latest_batch or item["batchId"] == latest_batch["id"]
        ]
        counts = {
            status: sum(item["taskStatus"] == status for item in latest_tasks)
            for status in ("执行中", "执行出错", "等待人工审核", "执行完成")
        }
        changes = self.repo.list_source_updates(None, None, None)
        return {
            "summary": [
                {
                    "label": "今日具体任务",
                    "value": str(len(latest_tasks)),
                    "hint": f"数据处理 {sum(i['stage'] == '数据处理' for i in latest_tasks)} · 图谱构建 {sum(i['stage'] == '图谱构建' for i in latest_tasks)}",
                },
                {"label": "执行完成", "value": str(counts["执行完成"]), "hint": ""},
                {"label": "执行出错", "value": str(counts["执行出错"]), "hint": ""},
                {"label": "等待人工审核", "value": str(counts["等待人工审核"]), "hint": ""},
            ],
            "statusCounts": counts,
            "latestBatch": latest_batch,
            "changeSummary": {
                "total": latest_batch["input"] if latest_batch else len(changes),
                "added": 18420,
                "updated": 6408,
                "deleted": 312,
                "detectedAt": "2026-07-14 02:00:00",
                "completedAt": "2026-07-14 02:18:00",
            },
            "updatePolicy": self.repo.get_setting("update_policy"),
            "sourceHealth": self.repo.source_health(),
        }

    def list_tasks(self, **filters: Any) -> dict[str, Any]:
        items = self.repo.list_tasks(filters)
        page = max(int(filters.get("page") or 1), 1)
        page_size = min(max(int(filters.get("page_size") or 50), 1), 200)
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "total": len(items),
            "page": page,
            "pageSize": page_size,
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self.repo.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        task["batch"] = self.repo.get_batch(task["batchId"])
        task["review"] = self.repo.get_review(task_id)
        return task

    def list_reviews(self, **filters: Any) -> dict[str, Any]:
        items = self.repo.list_reviews(filters)
        batches = {item["id"]: item for item in self.repo.list_batches()}
        for item in items:
            batch = batches.get(item["batch"])
            item["dataWindow"] = batch["dataWindow"] if batch else "-"
            score = item.get("score")
            item["confidenceValue"] = (
                score if score and float(score) < 0.9 and item["module"] != "数据处理" else "—"
            )
            item["confidenceLabel"] = "低于阈值" if item["confidenceValue"] != "—" else ""
        page = max(int(filters.get("page") or 1), 1)
        page_size = min(max(int(filters.get("page_size") or 50), 1), 200)
        start = (page - 1) * page_size
        status_counts = {
            status: sum(item["status"] == status for item in items)
            for status in ("待处理", "已完成", "已撤销")
        }
        return {
            "items": items[start : start + page_size],
            "total": len(items),
            "page": page,
            "pageSize": page_size,
            "statusCounts": status_counts,
        }

    def get_review(self, review_id: str) -> dict[str, Any]:
        review = self.repo.get_review(review_id)
        if review is None:
            raise KeyError(review_id)
        review["task"] = self.repo.get_task(review_id)
        review["batchDetail"] = self.repo.get_batch(review["batch"])
        return review

    async def handle_review(self, review_id: str, action: dict[str, Any]) -> dict[str, Any]:
        review = self.get_review(review_id)
        if review["status"] != "待处理":
            raise ValueError("只有待处理任务可以提交处置")
        review.pop("task", None)
        review.pop("batchDetail", None)
        review["decision"] = action["action_id"]
        review["decisionNote"] = action.get("note", "")
        review["modifiedResult"] = action.get("result", {})
        review["handler"] = action.get("handler") or review["handler"]
        review["status"] = "已完成"
        review["completedAt"] = _now()
        review["updatedAt"] = _now()
        review["revision"] = int(review.get("revision", 1)) + 1
        execution = None
        if action.get("rerun"):
            execution = await self.retry_review(
                review_id, action.get("result", {}), save_review=False
            )
            review["retryExecutionId"] = execution["id"]
        self.repo.save_review(review)
        return {"review": review, "execution": execution}

    def modify_review_result(self, review_id: str, request: dict[str, Any]) -> dict[str, Any]:
        review = self.get_review(review_id)
        review.pop("task", None)
        review.pop("batchDetail", None)
        review["modifiedResult"] = request["result"]
        review["decisionNote"] = request.get("note", review.get("decisionNote", ""))
        review["handler"] = request.get("handler") or review["handler"]
        review["updatedAt"] = _now()
        review["revision"] = int(review.get("revision", 1)) + 1
        self.repo.save_review(review)
        return review

    async def retry_review(
        self, review_id: str, payload: dict[str, Any] | None = None, *, save_review: bool = True
    ) -> dict[str, Any]:
        review = self.get_review(review_id)
        definition = self.repo.get_definition("graph-build")
        if definition is None:
            raise RuntimeError("图谱构建工作流定义缺失")
        merged_payload = {
            "reviewId": review_id,
            "batchId": review["batch"],
            "domain": review["domain"],
            **(payload or {}),
        }
        execution = await self.execute_definition(definition, merged_payload)
        if save_review:
            review.pop("task", None)
            review.pop("batchDetail", None)
            review["lastRetryAt"] = _now()
            review["retryExecutionId"] = execution["id"]
            review["updatedAt"] = _now()
            self.repo.save_review(review)
        return execution

    def revoke_review(self, review_id: str, reason: str, handler: str | None) -> dict[str, Any]:
        review = self.get_review(review_id)
        review.pop("task", None)
        review.pop("batchDetail", None)
        review["status"] = "已撤销"
        review["decision"] = "撤销任务"
        review["decisionNote"] = reason
        review["handler"] = handler or review["handler"]
        review["completedAt"] = _now()
        review["updatedAt"] = _now()
        review["revision"] = int(review.get("revision", 1)) + 1
        self.repo.save_review(review)
        return review

    async def execute_definition(
        self, definition: dict[str, Any], payload: dict[str, Any], workflow_id: str | None = None
    ) -> dict[str, Any]:
        if workflow_id and self.repo.get_execution_by_workflow_id(workflow_id):
            raise ValueError(f"Workflow ID 已存在: {workflow_id}")
        try:
            dispatch = await temporal_runtime.start(definition, payload, workflow_id)
        except Exception as exc:
            temporal_runtime.reset_client()
            dispatch = {
                "workflowId": workflow_id or f"queued-{definition['id']}-{uuid4().hex[:12]}",
                "runId": None,
                "status": "QUEUED",
                "dispatchMode": "LOCAL_FALLBACK",
                "message": f"Temporal 暂不可用，已保存待下发记录: {exc}",
            }
        execution = temporal_runtime.execution_record(definition["id"], dispatch, payload)
        execution["statusUrl"] = f"/api/v1/workflow-system/executions/{execution['id']}/status"
        self.repo.save_execution(execution)
        return execution

    async def retry_queued_executions(self, limit: int = 50) -> int:
        """Retry locally queued dispatches and preserve their original execution IDs."""
        dispatched = 0
        for execution in self.repo.list_queued_executions(limit):
            definition = self.repo.get_definition(execution["definitionId"])
            if definition is None:
                execution["message"] = "关联的工作流定义不存在，无法补偿下发"
                execution["retryCount"] = int(execution.get("retryCount", 0)) + 1
                execution["lastRetryAt"] = _now()
                self.repo.save_execution(execution)
                continue
            try:
                dispatch = await temporal_runtime.start(
                    definition, execution["payload"], execution["workflowId"]
                )
            except Exception as exc:
                temporal_runtime.reset_client()
                execution["message"] = f"补偿下发失败: {exc}"
                execution["retryCount"] = int(execution.get("retryCount", 0)) + 1
                execution["lastRetryAt"] = _now()
                self.repo.save_execution(execution)
                continue
            execution.update(
                runId=dispatch.get("runId"),
                status=dispatch["status"],
                dispatchMode="TEMPORAL_RETRY",
                message=dispatch.get("message", "补偿下发成功"),
                lastRetryAt=_now(),
                retryCount=int(execution.get("retryCount", 0)) + 1,
            )
            self.repo.save_execution(execution)
            if task_id := execution.get("taskId"):
                if task := self.repo.get_task(task_id):
                    task["runId"] = execution.get("runId")
                    task["result"] = execution["message"]
                    if execution["message"] not in task["logs"]:
                        task["logs"].append(execution["message"])
                    self.repo.save_task(task)
            dispatched += 1
        return dispatched

    async def run_fallback_dispatcher(self) -> None:
        """Continuously compensate LOCAL_FALLBACK executions in the API process."""
        interval = max(float(os.getenv("WORKFLOW_RETRY_INTERVAL_SECONDS", "30")), 1.0)
        while True:
            try:
                await self.retry_queued_executions()
            except Exception:
                logger.exception("工作流补偿下发器执行失败")
                temporal_runtime.reset_client()
            await asyncio.sleep(interval)

    def _create_task(
        self,
        *,
        definition: dict[str, Any],
        execution: dict[str, Any],
        payload: dict[str, Any],
        domains: list[str],
        entities: list[str],
        relations: list[str],
        object_name: str,
        action: str,
    ) -> dict[str, Any]:
        latest_execution = self.repo.get_execution(execution["id"])
        if latest_execution is not None:
            execution.clear()
            execution.update(latest_execution)
        now = datetime.now()
        task_id = f"PI-{now.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
        batch_id = f"UPD-{now.strftime('%Y%m%d')}"
        kind = _task_kind(entities, relations)
        data_domain = _domain_label(domains)
        task_status = {
            "COMPLETED": "执行完成",
            "FAILED": "执行出错",
            "CANCELED": "执行出错",
            "TERMINATED": "执行出错",
            "TIMED_OUT": "执行出错",
        }.get(execution["status"], "执行中")
        task = {
            "id": task_id,
            "batchId": batch_id,
            "stage": "图谱构建",
            "kind": kind,
            "objectId": execution["workflowId"],
            "objectName": object_name,
            "objectType": "工作流实例",
            "action": action,
            "sourceTable": "按请求参数执行",
            "sourceRecordId": payload.get("since") or "latest-cursor",
            "rule": definition["id"],
            "confidence": "",
            "result": execution["message"],
            "status": {
                "执行完成": "已完成",
                "执行出错": "执行失败",
            }.get(task_status, "处理中"),
            "taskStatus": task_status,
            "dataDomain": data_domain,
            "processedAt": _now(),
            "reviewType": None,
            "currentStep": "数据接入",
            "steps": WorkflowRepository._steps(None),
            "workflowType": definition["workflowType"],
            "workflowId": execution["workflowId"],
            "runId": execution.get("runId"),
            "executionId": execution["id"],
            "statusUrl": execution["statusUrl"],
            "input": payload,
            "output": execution.get("output"),
            "logs": [execution["message"]],
        }
        batch = self.repo.get_batch(batch_id) or {
            "id": batch_id,
            "name": f"{now.strftime('%Y-%m-%d')} API 触发任务",
            "updateDate": now.strftime("%Y-%m-%d"),
            "dataWindow": f"{payload.get('since') or 'latest'}—{_now()}",
            "source": "API 即时触发",
            "trigger": "客户端请求",
            "input": 0,
            "entities": 0,
            "relations": 0,
            "completed": 0,
            "abnormal": 0,
            "progress": 0,
            "status": "执行中",
            "startedAt": _now(),
            "completedAt": None,
        }
        batch["input"] += 1
        batch["entities"] += len(entities)
        batch["relations"] += len(relations)
        self.repo.save_batch(batch)
        self.repo.save_task(task)
        execution["taskId"] = task_id
        self.repo.save_execution(execution)
        self._refresh_batch(batch_id)
        return task

    def _refresh_batch(self, batch_id: str) -> None:
        batch = self._batch_snapshot(batch_id)
        if batch is not None:
            self.repo.save_batch(batch)

    def _batch_snapshot(
        self, batch_id: str, task_override: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        batch = self.repo.get_batch(batch_id)
        if batch is None:
            return None
        tasks = self.repo.list_tasks({"batch_id": batch_id})
        if task_override is not None:
            tasks = [task_override if task["id"] == task_override["id"] else task for task in tasks]
        if not tasks:
            return batch
        completed = sum(task["taskStatus"] == "执行完成" for task in tasks)
        abnormal = sum(task["taskStatus"] == "执行出错" for task in tasks)
        terminal = completed + abnormal
        batch.update(
            completed=completed,
            abnormal=abnormal,
            progress=round(terminal / len(tasks) * 100),
            status="执行出错" if abnormal else ("已完成" if terminal == len(tasks) else "执行中"),
            completedAt=_now() if terminal == len(tasks) else None,
        )
        return batch

    @staticmethod
    def _accepted_result(task: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
        return {
            "taskId": task["id"],
            "executionId": execution["id"],
            "workflowId": execution["workflowId"],
            "statusUrl": execution["statusUrl"],
            "task": task,
            "execution": execution,
        }

    async def trigger_graph_build(self, request: dict[str, Any]) -> dict[str, Any]:
        definition = self.repo.get_definition("graph-build")
        if definition is None:
            raise RuntimeError("图谱构建工作流定义缺失")
        payload = {
            "domains": request.get("domains", []),
            "entities": request.get("entities", []),
            "relations": request.get("relations", []),
            "since": request.get("since"),
            "reason": request.get("reason"),
            **request.get("payload", {}),
        }
        execution = await self.execute_definition(definition, payload)
        task = self._create_task(
            definition=definition,
            execution=execution,
            payload=payload,
            domains=request.get("domains", []),
            entities=request.get("entities", []),
            relations=request.get("relations", []),
            object_name="立即触发图谱构建",
            action="增量图谱构建",
        )
        return self._accepted_result(task, execution)

    async def trigger_schedule(self, schedule_id: str) -> dict[str, Any]:
        schedule = self.repo.get_schedule(schedule_id)
        if schedule is None:
            raise KeyError(schedule_id)
        definition = self.repo.get_definition(schedule["definitionId"])
        if definition is None:
            raise RuntimeError("Schedule 关联的工作流定义不存在")
        payload = {**schedule.get("payload", {}), "scheduleId": schedule_id}
        execution = await self.execute_definition(definition, payload)
        task = self._create_task(
            definition=definition,
            execution=execution,
            payload=payload,
            domains=payload.get("domains", []),
            entities=payload.get("entities", []),
            relations=payload.get("relations", []),
            object_name=f"Schedule {schedule_id} 立即执行",
            action="Schedule 立即触发",
        )
        return self._accepted_result(task, execution)

    async def trigger_schema_execution(
        self,
        *,
        schema: dict[str, Any],
        script: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        definition = self.repo.get_definition("schema-execution")
        if definition is None:
            raise RuntimeError("Schema 脚本执行工作流定义缺失")
        workflow_payload = {
            "schemaId": schema["id"],
            "schemaKey": schema["key"],
            "schemaName": schema["name"],
            "schemaKind": schema["kind"],
            "identityKey": schema.get("identityKey") or "",
            "properties": schema.get("properties") or [],
            "bucket": script["bucket"],
            "objectKey": script["objectKey"],
            "sha256": script["sha256"],
            "functionName": "transform",
            "payload": payload,
        }
        execution = await self.execute_definition(definition, workflow_payload)
        task = self._create_task(
            definition=definition,
            execution=execution,
            payload=workflow_payload,
            domains=[schema["label"]],
            entities=[schema["key"]] if schema["kind"] == "entity" else [],
            relations=[schema["key"]] if schema["kind"] == "relation" else [],
            object_name=f"执行 Schema {schema['name']}",
            action="Schema 脚本转换",
        )
        return self._accepted_result(task, execution)

    def apply_execution_outcome(
        self,
        *,
        workflow_id: str,
        status: str,
        output: Any = None,
        failure: str | None = None,
    ) -> dict[str, Any]:
        """Persist a terminal Worker callback and update its task and batch atomically enough."""
        execution = self.repo.get_execution_by_workflow_id(workflow_id)
        if execution is None:
            raise RuntimeError(f"执行记录尚未创建: {workflow_id}")
        execution.update(
            status=status,
            output=output,
            failure=failure,
            completedAt=_now(),
        )
        task = None
        batch = None
        if task_id := execution.get("taskId"):
            if task := self.repo.get_task(task_id):
                task["taskStatus"] = "执行完成" if status == "COMPLETED" else "执行出错"
                task["status"] = "已完成" if status == "COMPLETED" else "执行失败"
                task["output"] = output
                message = failure or f"Temporal 工作流状态更新为 {status}"
                if message not in task["logs"]:
                    task["logs"].append(message)
                batch = self._batch_snapshot(task["batchId"], task)
        self.repo.save_outcome(execution, task, batch)
        return execution

    async def execution_status(self, execution_id: str) -> dict[str, Any]:
        execution = self.repo.get_execution(execution_id)
        if execution is None:
            raise KeyError(execution_id)
        if execution.get("dispatchMode") == "LOCAL_FALLBACK":
            return {**execution, "live": False}
        try:
            live = await temporal_runtime.describe_execution(
                execution["workflowId"], execution.get("runId")
            )
        except Exception as exc:
            temporal_runtime.reset_client()
            return {**execution, "live": False, "liveError": str(exc)}

        if live["status"] in {"COMPLETED", "FAILED", "CANCELED", "TERMINATED", "TIMED_OUT"}:
            execution = self.apply_execution_outcome(
                workflow_id=execution["workflowId"],
                status=live["status"],
                output=live.get("output"),
                failure=live.get("failure"),
            )
        else:
            execution["status"] = live["status"]
            self.repo.save_execution(execution)
        return {**execution, "live": True}

    async def save_update_policy(self, request: dict[str, Any]) -> dict[str, Any]:
        cron_map = {
            "每天": "0 {hour} * * *",
            "每12小时": "0 */12 * * *",
            "每6小时": "0 */6 * * *",
            "每周": "0 {hour} * * 1",
        }
        hour, minute = request["execution_time"].split(":")
        template = cron_map[request["frequency"]]
        cron = template.format(hour=int(hour))
        if request["frequency"] in {"每天", "每周"}:
            cron = f"{int(minute)} {int(hour)}" + cron[cron.find(" ", cron.find(" ") + 1) :]
        policy = {
            "id": "auto-graph-build",
            "enabled": request["enabled"],
            "frequency": request["frequency"],
            "executionTime": request["execution_time"],
            "timezone": request["timezone"],
            "cron": cron,
            "skipWhenNoChanges": request["skip_when_no_changes"],
            "updatedAt": _now(),
            "nextRunAt": "由 Temporal Schedule 计算",
        }
        definition = self.repo.get_definition("graph-build")
        schedule_record = {
            "id": policy["id"],
            "definitionId": "graph-build",
            "cron": cron,
            "timezone": policy["timezone"],
            "active": policy["enabled"],
            "payload": {"reason": "自动更新策略"},
        }
        if definition:
            try:
                schedule_record = await temporal_runtime.create_schedule(
                    definition, schedule_record
                )
            except Exception as exc:
                temporal_runtime.reset_client()
                schedule_record["dispatchStatus"] = "LOCAL_SAVED"
                schedule_record["message"] = str(exc)
        self.repo.save_schedule(schedule_record)
        self.repo.save_setting("update_policy", policy)
        return {"policy": policy, "schedule": schedule_record}

    def create_definition(self, request: dict[str, Any]) -> dict[str, Any]:
        definition = {
            "id": request["id"],
            "name": request["name"],
            "workflowType": "kg.custom.configurable",
            "category": request["category"],
            "taskQueue": request["task_queue"],
            "active": request["active"],
            "sourceKind": "declarative",
            "steps": request["steps"],
            "createdAt": _now(),
        }
        self.repo.create_definition(definition)
        return definition

    def create_python_definition(
        self,
        filename: str,
        content: bytes,
        function_name: str,
        definition_id: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        if len(content) > 1024 * 1024:
            raise ValueError("Python 脚本不能超过 1 MiB")
        source = content.decode("utf-8")
        tree = ast.parse(source, filename=filename)
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if function_name not in functions:
            raise ValueError(f"脚本必须定义 {function_name}(payload) 函数")
        safe_id = definition_id or re.sub(r"[^a-z0-9_-]", "-", Path(filename).stem.lower()).strip(
            "-"
        )
        safe_id = safe_id or f"python-{uuid4().hex[:8]}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", safe_id):
            raise ValueError("definition_id 只能包含小写字母、数字、下划线和连字符")
        if self.repo.get_definition(safe_id) is not None:
            raise ValueError(f"工作流定义已存在: {safe_id}")
        directory = Path(os.getenv("WORKFLOW_SCRIPT_DIR", "/tmp/tech-kg-workflow-scripts"))
        directory.mkdir(parents=True, exist_ok=True)
        script_path = directory / f"{safe_id}.py"
        script_path.write_bytes(content)
        definition = {
            "id": safe_id,
            "name": name or Path(filename).stem,
            "workflowType": "kg.custom.python",
            "category": "custom",
            "taskQueue": temporal_runtime.task_queue,
            "active": True,
            "sourceKind": "python",
            "functionName": function_name,
            "scriptPath": str(script_path),
            "timeoutSeconds": 60,
            "steps": [f"python:{function_name}"],
            "createdAt": _now(),
        }
        try:
            self.repo.create_definition(definition)
        except Exception:
            script_path.unlink(missing_ok=True)
            raise
        return definition


workflow_operations_service = WorkflowOperationsService()
