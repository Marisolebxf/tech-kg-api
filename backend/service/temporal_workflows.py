"""科技图谱 Temporal 工作流与 Activity 定义。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from temporalio import activity, workflow
from temporalio.common import RetryPolicy


@activity.defn
async def execute_kg_step(request: dict[str, Any]) -> dict[str, Any]:
    """领域步骤执行入口；project 域真实调用 ETL，其它域保持轻量完成桩。"""
    domain = request.get("domain")
    step = request["step"]
    kind = request.get("kind")
    payload = request.get("payload", {}) or {}
    if domain == "project":
        return await asyncio.to_thread(_run_project_step, step, payload)
    await asyncio.sleep(float(request.get("delaySeconds", 0)))
    return {
        "step": step,
        "domain": domain,
        "kind": kind,
        "status": "completed",
        "input": payload,
        "output": payload,
    }


def _run_project_step(step: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Map Temporal pipeline steps onto project ETL stages.

    真实写入集中在 ``persist``（完整流水线），避免 align/persist 重复跑。
    """
    from script.workflows.project_ingest_workflow import workflow as project_pipeline

    limit = payload.get("limit")
    limit_int = int(limit) if limit is not None else 50
    dry_run = bool(payload.get("dry_run", False))
    common = {
        "project_id": payload.get("project_id"),
        "id_prefix": payload.get("id_prefix"),
        "limit": limit_int,
        "ingest_batch": payload.get("ingest_batch"),
        "dry_run": dry_run,
    }

    if step == "persist":
        output = project_pipeline(payload)
        return {"step": step, "domain": "project", "status": "completed", "output": output}

    # 前置步骤仅记账；ETL 在 persist 一次跑完（schema→load→align→cleanup）
    return {
        "step": step,
        "domain": "project",
        "status": "deferred_to_persist",
        "output": common,
    }


@activity.defn
async def load_workflow_definition(definition_id: str) -> dict[str, Any]:
    # 延迟导入避免 Workflow sandbox 在模块加载阶段访问 SQLite。
    from service.workflow_repository import repository

    definition = repository.get_definition(definition_id)
    if definition is None:
        raise ValueError(f"工作流定义不存在: {definition_id}")
    return definition


@activity.defn
async def execute_python_script(request: dict[str, Any]) -> dict[str, Any]:
    """在隔离子进程中调用上传脚本的 workflow(payload) 函数。"""
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    function_name = request.get("functionName", "workflow")
    runner = """
import asyncio
import importlib.util
import inspect
import json
import sys

path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("uploaded_workflow", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.loads(sys.stdin.read() or "{}")
result = function(payload)
if inspect.isawaitable(result):
    result = asyncio.run(result)
print(json.dumps(result, ensure_ascii=False))
"""
    # 上传脚本需要 backend 模块（infra/dao/script）与凭据（MySQL/TRSGraph）。
    # worker 进程不 import infra，故这里显式加载 backend/.env，并把 backend 目录加入 PYTHONPATH。
    # 平台已声明上传脚本具备服务器进程权限（见 docs/workflow_operations_api.md），透传 env 不降低安全面。
    # BACKEND_DIR 在 activity 内计算（workflow sandbox 禁止模块顶层 Path.resolve）。
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    pythonpath = os.pathsep.join(filter(None, [str(backend_dir), str(script_path.parent)]))
    sub_env = {**os.environ, "PYTHONPATH": pythonpath}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        runner,
        str(script_path),
        function_name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sub_env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(
                json.dumps(request.get("payload", {}), ensure_ascii=False).encode()
            ),
            timeout=float(request.get("timeoutSeconds", 60)),
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("上传脚本执行超时") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    return json.loads(stdout.decode() or "null")


def _retry_policy(config: dict[str, Any]) -> RetryPolicy:
    """把 manifest 的 retryPolicy 配置翻译成 Temporal RetryPolicy。

    maximumAttempts 默认 1（不重试）——stateful 步骤如 persist 由 manifest 显式声明。
    """
    return RetryPolicy(
        maximum_attempts=max(int(config.get("maximumAttempts", 1)), 1),
        initial_interval=timedelta(seconds=int(config.get("initialIntervalSeconds", 1))),
        maximum_interval=timedelta(seconds=int(config.get("maximumIntervalSeconds", 100))),
        non_retryable_error_types=config.get("nonRetryableErrorTypes") or None,
    )


@activity.defn
async def execute_pipeline_step(request: dict[str, Any]) -> dict[str, Any]:
    """运行 manifest 中某个 step 的用户函数 fn(payload, ctx)。

    与 execute_python_script 的区别：runner 读 {"payload":..., "ctx":...} 一份 JSON，
    调用 fn(payload, ctx) 双参签名；ctx 含 prevOutputs/stepId/attempt/executionId 等。
    状态不写 DB——workflow state 是真相，UI 走 @workflow.query。
    """
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    function_name = request["functionName"]
    attempt = activity.info().attempt
    ctx = {
        "stepId": request["stepId"],
        "attempt": attempt,
        "prevOutputs": request.get("prevOutputs", {}),
        "executionId": request.get("executionId"),
        "taskId": request.get("taskId"),
        "definitionId": request.get("definitionId"),
    }
    runner = """
import asyncio
import importlib.util
import inspect
import json
import sys

path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("uploaded_step_module", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
data = json.loads(sys.stdin.read() or "{}")
payload = data.get("payload", {})
ctx = data.get("ctx", {})
result = function(payload, ctx)
if inspect.isawaitable(result):
    result = asyncio.run(result)
print(json.dumps(result, ensure_ascii=False))
"""
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    pythonpath = os.pathsep.join(filter(None, [str(backend_dir), str(script_path.parent)]))
    sub_env = {**os.environ, "PYTHONPATH": pythonpath}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        runner,
        str(script_path),
        function_name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sub_env,
    )
    stdin_data = json.dumps(
        {"payload": request.get("payload", {}), "ctx": ctx}, ensure_ascii=False
    ).encode()
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(stdin_data),
            timeout=float(request.get("timeoutSeconds", 600)),
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"step {request['stepId']} 执行超时") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    output = json.loads(stdout.decode() or "null")
    # post-process pendingReview: 入 ReviewCase 队列，pipeline 不暂停
    pending = output.pop("pendingReview", []) if isinstance(output, dict) else []
    if pending:
        _enqueue_pending_review(request, pending, attempt)
    return {"step": request["stepId"], "status": "COMPLETED", "output": output, "attempt": attempt}


def _enqueue_pending_review(request: dict[str, Any], pending: list[Any], attempt: int) -> None:
    """把 step 返回的 pendingReview 项写入 ReviewCase 队列（T_DIRECT 模板）。

    入队失败不阻塞 pipeline——记 warning，继续；dedupe_key 保证幂等。
    """
    import logging

    info = activity.info()
    workflow_id = info.workflow_id
    workflow_run_id = info.workflow_run_id
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(workflow_id) or {}
    except Exception as exc:
        logging.getLogger("workflow.kg.custom.steps").warning(
            "lookup execution for workflow %s failed: %s", workflow_id, exc
        )
        execution = {}
    task_id = execution.get("taskId") or f"PI-kgstep-{workflow_id[:12]}"
    execution_id = execution.get("id")
    try:
        from service.manual_review_production import manual_review_service

        for item in pending:
            if not isinstance(item, dict):
                continue
            try:
                manual_review_service.create_direct_case(
                    task_id=task_id,
                    execution_id=execution_id,
                    step_id=request["stepId"],
                    kind=item.get("kind", "entity"),
                    candidate=item.get("candidate", {}),
                    object_id=item.get("objectId"),
                    object_name=item.get("objectName"),
                    node_label=item.get("nodeLabel"),
                    edge_type=item.get("edgeType"),
                    from_id=item.get("fromId"),
                    to_id=item.get("toId"),
                    reason=item.get("reason", ""),
                    confidence=item.get("confidence"),
                    evidence=item.get("evidence", []),
                    workflow_id=workflow_id,
                    workflow_run_id=workflow_run_id,
                    domain=item.get("domain", "graph"),
                )
            except Exception as exc:
                logging.getLogger("workflow.kg.custom.steps").warning(
                    "create_direct_case failed step=%s obj=%s reason=%s",
                    request["stepId"],
                    item.get("objectId"),
                    exc,
                )
    except Exception as exc:
        logging.getLogger("workflow.kg.custom.steps").warning(
            "enqueue pending review unavailable (service load failed): %s", exc
        )


async def _run_domain_pipeline(request: dict[str, Any], kind: str, domain: str) -> dict[str, Any]:
    results = []
    for step in ("load_increment", "normalize", "extract", "align", "validate", "persist"):
        results.append(
            await workflow.execute_activity(
                execute_kg_step,
                {
                    "step": step,
                    "kind": kind,
                    "domain": domain,
                    "payload": request,
                },
                start_to_close_timeout=timedelta(minutes=10),
            )
        )
    return {"kind": kind, "domain": domain, "status": "completed", "steps": results}


@workflow.defn(name="kg.entity.paper")
class PaperEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "paper")


@workflow.defn(name="kg.entity.scholar")
class ScholarEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "scholar")


@workflow.defn(name="kg.entity.patent")
class PatentEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "patent")


@workflow.defn(name="kg.entity.organization")
class OrganizationEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "organization")


@workflow.defn(name="kg.entity.project")
class ProjectEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "project")


@workflow.defn(name="kg.relation.authorship")
class AuthorshipRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "authorship")


@workflow.defn(name="kg.relation.employment")
class EmploymentRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "employment")


@workflow.defn(name="kg.relation.citation")
class CitationRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "citation")


@workflow.defn(name="kg.relation.cooperation")
class CooperationRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "cooperation")


@workflow.defn(name="kg.graph.build")
class GraphBuildWorkflow:
    """总工作流；按请求为每类实体和关系启动各自的子工作流。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        entities = request.get("entities") or [
            "paper",
            "scholar",
            "patent",
            "organization",
            "project",
        ]
        relations = request.get("relations") or [
            "authorship",
            "employment",
            "citation",
            "cooperation",
        ]
        child_types = [
            *(f"kg.entity.{item}" for item in entities),
            *(f"kg.relation.{item}" for item in relations),
        ]
        results = []
        for index, workflow_type in enumerate(child_types):
            results.append(
                await workflow.execute_child_workflow(
                    workflow_type,
                    request,
                    id=f"{workflow.info().workflow_id}-{index}-{workflow_type.rsplit('.', 1)[-1]}",
                )
            )
        return {"status": "completed", "children": results}


@workflow.defn(name="kg.custom.configurable")
class ConfigurableWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        results = []
        for step in definition.get("steps", []):
            step_name = step if isinstance(step, str) else step.get("id") or step.get("name")
            results.append(
                await workflow.execute_activity(
                    execute_kg_step,
                    {
                        "step": step_name,
                        "kind": "custom",
                        "domain": definition["id"],
                        "payload": request.get("payload", {}),
                    },
                    start_to_close_timeout=timedelta(minutes=10),
                )
            )
        return {"definitionId": definition["id"], "status": "completed", "steps": results}


@workflow.defn(name="kg.custom.python")
class PythonScriptWorkflow:
    """上传脚本工作流包装器，脚本函数在 Activity 子进程中运行以保证 Workflow 可重放。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> Any:
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        timeout_seconds = max(int(definition.get("timeoutSeconds", 60)), 1)
        return await workflow.execute_activity(
            execute_python_script,
            {
                "scriptPath": definition["scriptPath"],
                "functionName": definition.get("functionName", "workflow"),
                "payload": request.get("payload", {}),
                "timeoutSeconds": timeout_seconds,
            },
            start_to_close_timeout=timedelta(seconds=timeout_seconds + 30),
        )


@workflow.defn(name="kg.custom.steps")
class StepPipelineWorkflow:
    """多步实体构建流水线：每步一个 Activity，带独立 retry/timeout。

    审核是 post-hoc：step 返回的 pendingReview 字段被 activity 抽出写入 ReviewCase
    队列（T_DIRECT 模板），pipeline 不暂停、跑到底。审核者异步处理队列，
    accept 时直接写图，reject 时丢弃——与 workflow 完全解耦。
    失败重试用 ResetWorkflowExecution 回放，已完成步靠 event history replay 不重跑。
    状态放 workflow state：UI 用 get_steps query 读。
    """

    def __init__(self) -> None:
        self._steps: dict[str, dict[str, Any]] = {}
        self._current_step: str | None = None

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        prev_outputs: dict[str, Any] = {}
        for step in definition.get("steps", []):
            self._current_step = step["id"]
            try:
                result = await workflow.execute_activity(
                    execute_pipeline_step,
                    {
                        "taskId": request.get("taskId"),
                        "executionId": request.get("executionId"),
                        "definitionId": request["definitionId"],
                        "stepId": step["id"],
                        "functionName": step["functionName"],
                        "scriptPath": definition["scriptPath"],
                        "payload": request.get("payload", {}),
                        "prevOutputs": prev_outputs,
                        "timeoutSeconds": step.get("timeoutSeconds", 600),
                    },
                    start_to_close_timeout=timedelta(seconds=step.get("timeoutSeconds", 600) + 30),
                    retry_policy=_retry_policy(step.get("retryPolicy", {})),
                )
                self._steps[step["id"]] = {
                    "status": "COMPLETED",
                    "output": result["output"],
                    "attempt": result["attempt"],
                }
                prev_outputs[step["id"]] = result["output"]
            except Exception as exc:
                # Activity 重试耗尽后 workflow 失败；用户走 reset 回放重试。
                # FAILED 状态写入 self._steps 让 query 在 reset 之前仍可读到失败原因。
                self._steps[step["id"]] = {"status": "FAILED", "error": str(exc)}
                raise
        return {"status": "completed", "steps": self._steps}

    @workflow.query
    def get_steps(self) -> dict[str, Any]:
        return {"current": self._current_step, "steps": self._steps}


WORKFLOW_CLASSES = [
    PaperEntityWorkflow,
    ScholarEntityWorkflow,
    PatentEntityWorkflow,
    OrganizationEntityWorkflow,
    ProjectEntityWorkflow,
    AuthorshipRelationWorkflow,
    EmploymentRelationWorkflow,
    CitationRelationWorkflow,
    CooperationRelationWorkflow,
    GraphBuildWorkflow,
    ConfigurableWorkflow,
    PythonScriptWorkflow,
    StepPipelineWorkflow,
]

ACTIVITIES = [
    execute_kg_step,
    load_workflow_definition,
    execute_python_script,
    execute_pipeline_step,
]
