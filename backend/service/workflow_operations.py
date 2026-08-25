"""任务中心、人工审核和 Temporal 控制面的业务服务。"""

from __future__ import annotations

import ast
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from service.stage_normalizer import normalize_stages
from service.temporal_runtime import temporal_runtime
from service.workflow_repository import WorkflowRepository, repository


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


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

    def list_executions(self, limit: int = 100) -> dict[str, Any]:
        items = self.repo.list_executions(limit=limit)
        return {"items": items, "total": len(items)}

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self.repo.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        task["batch"] = self.repo.get_batch(task["batchId"])
        task["review"] = self.repo.get_review(task_id)
        return task

    async def query_step_state(self, task: dict[str, Any]) -> dict[str, Any] | None:
        """kg.custom.steps 任务查 Temporal workflow 实时 state（@workflow.query get_steps）。

        非 steps 任务、workflowId 缺失、或 Temporal 查询失败均返回 None，
        让调用方回退到静态 _steps()。
        """
        if task.get("workflowType") != "kg.custom.steps":
            return None
        workflow_id = task.get("workflowId")
        if not workflow_id:
            return None
        try:
            client = await temporal_runtime.client()
            handle = client.get_workflow_handle(workflow_id)
            return await handle.query("get_steps")
        except Exception as exc:
            temporal_runtime._client = None
            task["logs"] = (task.get("logs") or []) + [f"step state 查询失败: {exc}"]
            return None

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
        self,
        definition: dict[str, Any],
        payload: dict[str, Any],
        workflow_id: str | None = None,
        persist_task: bool = False,
    ) -> dict[str, Any]:
        try:
            dispatch = await temporal_runtime.start(definition, payload, workflow_id)
        except Exception as exc:
            if "already started" in str(exc).lower():
                raise ValueError(f"工作流已存在: {workflow_id}") from exc
            temporal_runtime._client = None
            dispatch = {
                "workflowId": workflow_id or f"queued-{definition['id']}-{uuid4().hex[:12]}",
                "runId": None,
                "status": "QUEUED",
                "dispatchMode": "LOCAL_FALLBACK",
                "message": f"Temporal 暂不可用，已保存待下发记录: {exc}",
            }
        execution = temporal_runtime.execution_record(definition["id"], dispatch, payload)
        self.repo.save_execution(execution)
        if persist_task:
            task_id = f"PI-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
            task = {
                "id": task_id,
                "batchId": f"UPD-{datetime.now().strftime('%Y%m%d')}",
                "stage": "图谱构建",
                "kind": "实体",
                "objectId": execution["workflowId"],
                "objectName": definition.get("name", definition["id"]),
                "objectType": "工作流实例",
                "action": "作业执行",
                "sourceTable": "",
                "sourceRecordId": payload.get("since") or "latest-cursor",
                "rule": definition["id"],
                "confidence": "",
                "result": execution["message"],
                "status": "已完成" if execution["status"] == "COMPLETED" else "处理中",
                "taskStatus": "执行中",
                "dataDomain": "综合数据域",
                "processedAt": _now(),
                "reviewType": None,
                "currentStep": "数据接入",
                "steps": WorkflowRepository._steps(None),
                "workflowType": definition["workflowType"],
                "workflowId": execution["workflowId"],
                "runId": execution.get("runId"),
                "input": payload,
                "output": None,
                "logs": [execution["message"]],
            }
            self.repo.save_task(task)
            execution["taskId"] = task_id
            self.repo.save_execution(execution)
        return execution

    async def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        execution = self.repo.get_execution(execution_id)
        if execution is None:
            return None
        # 只在 RUNNING 时向 Temporal 主动 refresh（终态执行不会再变，省 RPC）；
        # 但 _sync_task_from_execution 始终触发，覆盖历史 COMPLETED 但 task 未同步的 case
        if execution.get("status") == "RUNNING":
            try:
                execution = await temporal_runtime.refresh_execution(execution)
            except Exception as exc:
                temporal_runtime._client = None
                execution["message"] = f"状态刷新失败: {exc}"
            self.repo.save_execution(execution)
        self._sync_task_from_execution(execution)
        return execution

    async def retry_task(self, task_id: str, reason: str = "manual retry") -> dict[str, Any]:
        """失败任务重试：调 Temporal ResetWorkflowExecution；新 run_id 回写 execution + task。

        reset 到最近一个 workflow task，event history replay 保证已完成 step 不重跑，
        从失败 step 重新执行。task 必须 workflowType=kg.custom.steps 才有意义
        （其它 workflow 也可以 reset，但语义是"重放整个 workflow"）。
        """
        task = self.repo.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        workflow_id = task.get("workflowId")
        if not workflow_id:
            raise ValueError(f"任务 {task_id} 无 workflowId，无法 reset")
        run_id = task.get("runId")
        try:
            new_run_id = await temporal_runtime.reset_workflow(workflow_id, run_id, reason)
        except Exception as exc:
            temporal_runtime._client = None
            raise RuntimeError(f"Temporal reset 失败: {exc}") from exc
        # 回写 execution 行：新 run_id，状态置 RUNNING，等下次 refresh 同步
        execution = self.repo.get_execution_by_workflow(workflow_id)
        if execution:
            execution["runId"] = new_run_id
            execution["status"] = "RUNNING"
            execution["completedAt"] = None
            execution["message"] = f"任务重试：reset 到新 run_id={new_run_id}"
            self.repo.save_execution(execution)
        # 回写 task 状态：置执行中，新 run_id
        task["runId"] = new_run_id
        task["taskStatus"] = "执行中"
        task["status"] = "处理中"
        task["logs"] = (task.get("logs") or []) + [
            f"任务重试：reset 到新 run_id={new_run_id}，原因：{reason}"
        ]
        self.repo.save_task(task)
        return {"taskId": task_id, "workflowId": workflow_id, "newRunId": new_run_id}

    async def submit_review(
        self,
        task_id: str,
        decision: str,
        modified_result: dict[str, Any] | None = None,
        note: str = "",
        reviewer: str | None = None,
    ) -> dict[str, Any]:
        """人工审核：向 kg.custom.steps workflow 发 submit_review signal。

        workflow 暂停在 PENDING_REVIEW step 时，本方法恢复它：approve 则继续
        （modifiedResult 可覆盖下游输入），reject 则终止。
        鉴权在 backend handler 层做——workflow 信任 signal 来源。
        """
        task = self.repo.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        workflow_type = task.get("workflowType")
        if workflow_type != "kg.custom.steps":
            raise ValueError(f"任务 {task_id} workflowType={workflow_type}，不支持 signal 审核")
        workflow_id = task.get("workflowId")
        if not workflow_id:
            raise ValueError(f"任务 {task_id} 无 workflowId")
        try:
            client = await temporal_runtime.client()
            handle = client.get_workflow_handle(workflow_id)
            await handle.signal(
                "submit_review",
                {
                    "decision": decision,
                    "modifiedResult": modified_result,
                    "note": note,
                    "reviewer": reviewer,
                },
            )
        except Exception as exc:
            temporal_runtime._client = None
            raise RuntimeError(f"signal 提交失败: {exc}") from exc
        task["logs"] = (task.get("logs") or []) + [
            f"人工审核：decision={decision} reviewer={reviewer or 'anonymous'}"
            f" note={note or '(无)'}"
        ]
        self.repo.save_task(task)
        return {"taskId": task_id, "decision": decision, "reviewer": reviewer}

    def _sync_task_from_execution(self, execution: dict[str, Any]) -> None:
        """execution 终态时把状态回写到关联 task；若脚本返回了 stages，额外回写 steps/output。

        状态同步不依赖 stages 存在，否则像 kg.custom.python 这种不返回 stages 的工作流
        会让 task 永远停在「执行中」。stages 既可能是 list(旧形式)也可能是 dict
        (worker 实际形状),用 normalize_stages 统一归一化。
        """
        task_id = execution.get("taskId")
        if not task_id:
            return
        status = execution.get("status")
        if status == "COMPLETED":
            new_task_status = "执行完成"
            new_status = "已完成"
        elif status in {"FAILED", "CANCELED", "TERMINATED", "TIMED_OUT"}:
            new_task_status = "执行出错"
            new_status = "执行出错"
        else:
            # 非终态（RUNNING 等）：不更新 task 状态，避免覆盖正在执行的标记
            return
        task = self.repo.get_task(task_id)
        if task is None:
            return
        already_in_sync = task.get("taskStatus") == new_task_status
        output = execution.get("output")
        normalized_steps = normalize_stages(output)
        if normalized_steps:
            # 用真实 worker stages 覆盖任务创建时塞的静态模板 _steps()
            task["steps"] = normalized_steps
        if isinstance(output, dict):
            # output 是 dict 时一律写到 task 上便于详情页查看
            # (kg.custom.python 的 {status, result, ...} 也走这里)
            task["output"] = output
        if already_in_sync and task.get("status") == new_status:
            # 状态已一致，避免重复 log 累积
            self.repo.save_task(task)
            return
        task["taskStatus"] = new_task_status
        task["status"] = new_status
        if normalized_steps:
            log_msg = f"阶段回写：{len(normalized_steps)} 个 stage，状态={status}"
        elif isinstance(output, dict) and "stages" in output:
            log_msg = f"执行状态同步：{status}（output.stages 类型不支持归一化）"
        else:
            log_msg = f"执行状态同步：{status}（output 无 stages，仅回写状态）"
        task["logs"] = (task.get("logs") or []) + [log_msg]
        self.repo.save_task(task)

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
        task_id = f"PI-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
        task = {
            "id": task_id,
            "batchId": f"UPD-{datetime.now().strftime('%Y%m%d')}",
            "stage": "图谱构建",
            "kind": "实体",
            "objectId": execution["workflowId"],
            "objectName": "立即触发图谱构建",
            "objectType": "工作流实例",
            "action": "增量图谱构建",
            "sourceTable": "按业务域增量",
            "sourceRecordId": request.get("since") or "latest-cursor",
            "rule": "AUTO-GRAPH-BUILD",
            "confidence": "",
            "result": execution["message"],
            "status": "已完成" if execution["status"] == "COMPLETED" else "处理中",
            "taskStatus": "执行中",
            "dataDomain": "综合数据域",
            "processedAt": _now(),
            "reviewType": None,
            "currentStep": "数据接入",
            "steps": WorkflowRepository._steps(None),
            "workflowType": definition["workflowType"],
            "workflowId": execution["workflowId"],
            "runId": execution.get("runId"),
            "input": payload,
            "output": None,
            "logs": [execution["message"]],
        }
        self.repo.save_task(task)
        return {"task": task, "execution": execution}

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
                temporal_runtime._client = None
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
        self.repo.save_definition(definition)
        return definition

    def create_python_definition(
        self,
        filename: str,
        content: bytes,
        function_name: str,
        definition_id: str | None,
        name: str | None,
        timeout_seconds: int | None = None,
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
        backend_dir = Path(__file__).resolve().parents[1]
        directory = Path(
            os.getenv("WORKFLOW_SCRIPT_DIR", str(backend_dir / "var" / "workflow-scripts"))
        )
        directory.mkdir(parents=True, exist_ok=True)
        script_path = directory / f"{safe_id}.py"
        script_path.write_bytes(content)
        timeout = max(int(timeout_seconds), 1) if timeout_seconds else 60
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
            "timeoutSeconds": timeout,
            "steps": [f"python:{function_name}"],
            "createdAt": _now(),
        }
        self.repo.save_definition(definition)
        return definition

    def create_step_pipeline_definition(
        self,
        filename: str,
        content: bytes,
        steps: list[dict[str, Any]],
        definition_id: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        """上传 kg.custom.steps 流水线脚本 + step manifest。

        AST 校验每个 step.functionName 都在脚本里；step id 必须唯一。
        """
        if len(content) > 1024 * 1024:
            raise ValueError("Python 脚本不能超过 1 MiB")
        if not steps:
            raise ValueError("steps manifest 至少 1 步")
        source = content.decode("utf-8")
        tree = ast.parse(source, filename=filename)
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = [s["functionName"] for s in steps if s.get("functionName") not in functions]
        if missing:
            raise ValueError(f"脚本缺少以下 step 函数: {missing}")
        step_ids = [s["id"] for s in steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("steps 中 id 不能重复")
        safe_id = definition_id or re.sub(r"[^a-z0-9_-]", "-", Path(filename).stem.lower()).strip(
            "-"
        )
        safe_id = safe_id or f"steps-{uuid4().hex[:8]}"
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", safe_id):
            raise ValueError("definition_id 只能包含小写字母、数字、下划线和连字符")
        backend_dir = Path(__file__).resolve().parents[1]
        directory = Path(
            os.getenv("WORKFLOW_SCRIPT_DIR", str(backend_dir / "var" / "workflow-scripts"))
        )
        directory.mkdir(parents=True, exist_ok=True)
        script_path = directory / f"{safe_id}.py"
        script_path.write_bytes(content)
        definition = {
            "id": safe_id,
            "name": name or Path(filename).stem,
            "workflowType": "kg.custom.steps",
            "category": "custom",
            "taskQueue": temporal_runtime.task_queue,
            "active": True,
            "sourceKind": "python",
            "scriptPath": str(script_path),
            "steps": steps,
            "createdAt": _now(),
        }
        self.repo.save_definition(definition)
        return definition


workflow_operations_service = WorkflowOperationsService()
