"""科技图谱 Temporal 工作流与 Activity 定义。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)

ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


def _resolve_resources(
    payload: dict[str, Any], definition_id: str | None, step_id: str
) -> dict[str, Any]:
    """在 activity 内把触发时选择的 config_id 解析成连接参数 dict（非活对象）。

    密钥只在 worker 进程内、只进 ``KG_SCRIPT_CTX`` env，与 ``.env`` 同信任边界；
    不进 workflow payload（避免在 Temporal UI/搜索历史泄露）。任一资源解析失败
    独立降级为缺该 key（SDK 对应属性返回 None）。
    """
    resources: dict[str, Any] = {}

    mysql_id = payload.get("mysql_datasource_id")
    if mysql_id:
        try:
            from service.mysql_datasource import get_mysql_settings_by_id

            params = get_mysql_settings_by_id(mysql_id)
            if params:
                if payload.get("mysql_database"):
                    params = {**params, "database": payload["mysql_database"]}
                resources["mysql"] = params
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析 MySQL 数据源 %s 失败: %s", mysql_id, exc)

    milvus_id = payload.get("milvus_config_id")
    if milvus_id:
        try:
            from service.milvus_config import get_milvus_settings_by_id

            params = get_milvus_settings_by_id(milvus_id)
            if params:
                if payload.get("milvus_database"):
                    params = {**params, "db_name": payload["milvus_database"]}
                resources["milvus"] = params
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析 Milvus 配置 %s 失败: %s", milvus_id, exc)

    graph_space = payload.get("graph_space")
    if graph_space:
        try:
            from infra.graph_db.config import TRSGraphSettings

            s = TRSGraphSettings.from_env()
            resources["graph"] = {
                "base_url": s.base_url,
                "space": graph_space,
                "api_key": s.api_key,
                "timeout": s.timeout,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析图空间 %s 失败: %s", graph_space, exc)

    llm_id = payload.get("llm_config_id")
    if llm_id:
        try:
            from service.llm_config import get_llm_settings_by_id

            params = get_llm_settings_by_id(llm_id)
            if params:
                resources["llm"] = params
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析 LLM 配置 %s 失败: %s", llm_id, exc)

    emb_id = payload.get("embedding_config_id")
    if emb_id:
        try:
            from service.embedding_config import get_embedding_settings_by_id

            params = get_embedding_settings_by_id(emb_id)
            if params:
                resources["embedding"] = params
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析 embedding 配置 %s 失败: %s", emb_id, exc)

    try:
        from service.script_watermark import read_watermark

        wm = read_watermark(definition_id, step_id)
        if wm:
            resources["watermark"] = wm.get("watermark")
            resources["checkpoint"] = wm.get("checkpoint")
    except Exception as exc:  # noqa: BLE001
        logger.warning("读水位 %s/%s 失败: %s", definition_id, step_id, exc)

    return resources


def _write_watermark(definition_id: str | None, step_id: str, output: Any) -> None:
    """step 成功后写水位。脚本可在返回 dict 里带 ``_watermark``(ISO str)/``_checkpoint`` 覆盖默认 now()。

    失败不阻塞 pipeline——记 warning 继续。
    """
    from datetime import datetime

    from service.script_watermark import write_watermark

    watermark_override = None
    checkpoint = None
    if isinstance(output, dict):
        watermark_override = output.get("_watermark")
        checkpoint = output.get("_checkpoint")
    ts = None
    if watermark_override:
        try:
            ts = datetime.fromisoformat(watermark_override)
        except (ValueError, TypeError):
            ts = None
    write_watermark(definition_id, step_id, watermark=ts, checkpoint=checkpoint)


def _strip_watermark_meta(output: Any) -> Any:
    """从脚本返回里剥离 ``_watermark``/``_checkpoint`` 元字段，避免污染 step 输出展示。"""
    if isinstance(output, dict):
        output.pop("_watermark", None)
        output.pop("_checkpoint", None)
    return output


def _merge_access(stdout_access: Any, sidecar_path: str | None) -> Any:
    """sidecar 重放报告与 stdout 回传报告合并（sidecar 为准）。

    fire-and-forget：任何异常仅告警并降级返回 stdout 报告，绝不阻塞 step。
    """
    try:
        from sdk.access import merge_access_reports, report_from_sidecar

        return merge_access_reports(report_from_sidecar(sidecar_path), stdout_access)
    except Exception as exc:  # noqa: BLE001
        logger.warning("合并 access 溯源报告失败: %s", exc)
        return stdout_access


def _log_failed_access(context: str, sidecar_path: str | None) -> None:
    """失败/超时路径留账：把 sidecar 里的 access 报告打进日志（fire-and-forget）。"""
    try:
        from sdk.access import report_from_sidecar

        report = report_from_sidecar(sidecar_path)
        if report:
            logger.warning(
                "%s；access 溯源留账: %s", context, json.dumps(report, ensure_ascii=False)
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 access sidecar 失败: %s", exc)


def _cleanup_sidecar(sidecar_path: str | None) -> None:
    if not sidecar_path:
        return
    try:
        os.unlink(sidecar_path)
    except OSError:
        pass


@activity.defn
async def execute_kg_step(request: dict[str, Any]) -> dict[str, Any]:
    """Return lightweight bookkeeping results for built-in domain pipeline steps."""
    domain = request.get("domain")
    step = request["step"]
    kind = request.get("kind")
    payload = request.get("payload", {}) or {}
    await asyncio.sleep(float(request.get("delaySeconds", 0)))
    return {
        "step": step,
        "domain": domain,
        "kind": kind,
        "status": "completed",
        "input": payload,
        "output": payload,
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

from kg_sdk import access_report, flush_access_sidecar

path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("uploaded_workflow", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.loads(sys.stdin.read() or "{}")
try:
    result = function(payload)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
except BaseException:
    flush_access_sidecar()
    raise
flush_access_sidecar()
print(json.dumps({"result": result, "_access": access_report()}, ensure_ascii=False))
"""
    # 上传脚本需要 backend 模块（infra/dao/sdk）与凭据（MySQL/TRSGraph）。
    # worker 进程不 import infra，故这里显式加载 backend/.env，并把 backend + backend/sdk
    # 目录加入 PYTHONPATH。KG_SCRIPT_CTX 注入已解析的连接参数 + 水位，单参脚本用
    # `from kg_sdk import current_context` 取 Context。密钥经 env 传递的安全面与
    # MYSQL_PASSWORD 等 sub_env={**os.environ} 一致（见 docs/workflow_operations_api.md）。
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    payload = request.get("payload", {})
    resolved = _resolve_resources(payload, request.get("definitionId"), "_default")
    sdk_dir = backend_dir / "sdk"
    pythonpath = os.pathsep.join(
        filter(None, [str(backend_dir), str(sdk_dir), str(script_path.parent)])
    )
    sidecar = tempfile.NamedTemporaryFile(prefix="kg_access_", suffix=".jsonl", delete=False)
    sidecar_path = sidecar.name
    sidecar.close()
    sub_env = {
        **os.environ,
        "PYTHONPATH": pythonpath,
        "KG_SCRIPT_CTX": json.dumps(resolved, ensure_ascii=False),
        "KG_ACCESS_LOG": sidecar_path,
    }
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
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(payload, ensure_ascii=False).encode()),
                timeout=float(request.get("timeoutSeconds", 60)),
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            _log_failed_access("上传脚本执行超时", sidecar_path)
            raise RuntimeError("上传脚本执行超时") from None
        if process.returncode != 0:
            _log_failed_access(f"上传脚本退出码 {process.returncode}", sidecar_path)
            raise RuntimeError(stderr.decode(errors="replace")[-4000:])
        wrapped = json.loads(stdout.decode() or "null")
        output = (
            wrapped.get("result") if isinstance(wrapped, dict) and "result" in wrapped else wrapped
        )
        stdout_access = wrapped.pop("_access", None) if isinstance(wrapped, dict) else None
        access = _merge_access(stdout_access, sidecar_path)
        _write_watermark(request.get("definitionId"), "_default", output)
        output = _strip_watermark_meta(output)
        if access is not None and isinstance(output, dict):
            output = {**output, "access": access}
        return output
    finally:
        _cleanup_sidecar(sidecar_path)


@activity.defn
async def register_scheduled_execution(request: dict[str, Any]) -> dict[str, Any]:
    """周期 Schedule 触发的运行落 workflow_executions + tasks（幂等：runId 已存在则跳过）。

    Schedule 直发 workflow 不经过 API，历史只在 Temporal；此 activity 让每次触发
    都在 MySQL 留 execution/task 行，任务详情页由此列出周期执行记录。
    """
    from service.temporal_runtime import temporal_runtime
    from service.workflow_operations import WorkflowOperationsService
    from service.workflow_repository import repository

    definition = repository.get_definition(request["definitionId"])
    if definition is None:
        return {"ok": False, "reason": "definition-missing"}
    run_id = request.get("runId")
    if run_id and repository.get_execution_by_run(run_id) is not None:
        return {"ok": True, "deduped": True}
    dispatch = {
        "workflowId": request["workflowId"],
        "runId": run_id,
        "status": "RUNNING",
        "dispatchMode": "TEMPORAL_SCHEDULE",
        "message": "周期任务自动触发",
    }
    execution = temporal_runtime.execution_record(
        request["definitionId"], dispatch, request.get("payload", {})
    )
    execution["scheduleId"] = request["scheduleId"]
    execution["jobId"] = (request.get("payload") or {}).get("jobId")
    repository.save_execution(execution)
    task = WorkflowOperationsService.create_task_for_execution(
        definition, execution, request.get("payload", {})
    )
    repository.save_task(task)
    execution["taskId"] = task["id"]
    repository.save_execution(execution)
    _stamp_job_latest(execution)
    return {"ok": True, "executionId": execution["id"], "taskId": task["id"]}


def _stamp_job_latest(execution: dict[str, Any]) -> None:
    """best-effort 回写 job 的最近执行信息；job 缺失不影响运行。"""
    job_id = execution.get("jobId")
    if not job_id:
        return
    try:
        from service.workflow_repository import repository as _repo

        job = _repo.get_job(job_id)
        if job is None:
            return
        job["lastRunAt"] = execution.get("startedAt")
        job["lastExecutionId"] = execution["id"]
        job["lastExecutionStatus"] = execution.get("status")
        _repo.save_job(job)
    except Exception:  # noqa: BLE001
        pass


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
    payload = request.get("payload", {})
    # 在 worker 内解析 config_id → 连接参数 + 读水位，合并进 ctx（两参脚本直接用 ctx.mysql 等）。
    resolved = _resolve_resources(payload, request.get("definitionId"), request["stepId"])
    ctx.update(resolved)
    runner = """
import asyncio
import importlib.util
import inspect
import json
import sys

from kg_sdk import Context, access_report, flush_access_sidecar

path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("uploaded_step_module", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
data = json.loads(sys.stdin.read() or "{}")
payload = data.get("payload", {})
ctx = Context(data.get("ctx", {}))
try:
    result = function(payload, ctx)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
except BaseException:
    flush_access_sidecar()
    raise
flush_access_sidecar()
print(json.dumps({"result": result, "_access": access_report()}, ensure_ascii=False))
"""
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    sdk_dir = backend_dir / "sdk"
    pythonpath = os.pathsep.join(
        filter(None, [str(backend_dir), str(sdk_dir), str(script_path.parent)])
    )
    sidecar = tempfile.NamedTemporaryFile(prefix="kg_access_", suffix=".jsonl", delete=False)
    sidecar_path = sidecar.name
    sidecar.close()
    sub_env = {
        **os.environ,
        "PYTHONPATH": pythonpath,
        "KG_SCRIPT_CTX": json.dumps(ctx, ensure_ascii=False),
        "KG_ACCESS_LOG": sidecar_path,
    }
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
    stdin_data = json.dumps({"payload": payload, "ctx": ctx}, ensure_ascii=False).encode()
    try:
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin_data),
                timeout=float(request.get("timeoutSeconds", 600)),
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            _log_failed_access(f"step {request['stepId']} 执行超时", sidecar_path)
            raise RuntimeError(f"step {request['stepId']} 执行超时") from None
        if process.returncode != 0:
            _log_failed_access(
                f"step {request['stepId']} 退出码 {process.returncode}", sidecar_path
            )
            raise RuntimeError(stderr.decode(errors="replace")[-4000:])
        wrapped = json.loads(stdout.decode() or "null")
        output = (
            wrapped.get("result") if isinstance(wrapped, dict) and "result" in wrapped else wrapped
        )
        stdout_access = wrapped.pop("_access", None) if isinstance(wrapped, dict) else None
        access = _merge_access(stdout_access, sidecar_path)
        _write_watermark(request.get("definitionId"), request["stepId"], output)
        output = _strip_watermark_meta(output)
        # post-process pendingReview: 入 ReviewCase 队列，pipeline 不暂停
        pending = output.pop("pendingReview", []) if isinstance(output, dict) else []
        if pending:
            _enqueue_pending_review(request, pending, attempt)
        return {
            "step": request["stepId"],
            "status": "COMPLETED",
            "output": output,
            "attempt": attempt,
            "access": access,
        }
    finally:
        _cleanup_sidecar(sidecar_path)


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
                    source_record=item.get("sourceRecord"),
                    source_table=item.get("sourceTable"),
                    source_record_id=item.get("sourceRecordId"),
                    llm_input=item.get("llmInput"),
                    llm_output=item.get("llmOutput"),
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
                retry_policy=ACTIVITY_RETRY_POLICY,
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


async def _register_scheduled_run(request: dict[str, Any]) -> None:
    """payload 带 _scheduleId 时（周期 Schedule 触发），先落 execution/task 行。"""
    schedule_id = (request.get("payload") or {}).get("_scheduleId")
    if not schedule_id:
        return
    info = workflow.info()
    await workflow.execute_activity(
        register_scheduled_execution,
        {
            "definitionId": request["definitionId"],
            "scheduleId": schedule_id,
            "workflowId": info.workflow_id,
            "runId": info.run_id,
            "payload": request.get("payload", {}),
        },
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=ACTIVITY_RETRY_POLICY,
    )


@workflow.defn(name="kg.custom.configurable")
class ConfigurableWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        await _register_scheduled_run(request)
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
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
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
            )
        return {"definitionId": definition["id"], "status": "completed", "steps": results}


@workflow.defn(name="kg.custom.python")
class PythonScriptWorkflow:
    """上传脚本工作流包装器，脚本函数在 Activity 子进程中运行以保证 Workflow 可重放。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> Any:
        await _register_scheduled_run(request)
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        timeout_seconds = max(int(definition.get("timeoutSeconds", 60)), 1)
        return await workflow.execute_activity(
            execute_python_script,
            {
                "scriptPath": definition["scriptPath"],
                "functionName": definition.get("functionName", "workflow"),
                "payload": request.get("payload", {}),
                "definitionId": request.get("definitionId"),
                "timeoutSeconds": timeout_seconds,
            },
            start_to_close_timeout=timedelta(seconds=timeout_seconds + 30),
            retry_policy=ACTIVITY_RETRY_POLICY,
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
        await _register_scheduled_run(request)
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        prev_outputs: dict[str, Any] = {}
        for step in definition.get("steps", []):
            self._current_step = step["id"]
            step_payload = dict(request.get("payload", {}) or {})
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
                        "payload": step_payload,
                        "prevOutputs": prev_outputs,
                        "timeoutSeconds": step.get("timeoutSeconds", 600),
                    },
                    start_to_close_timeout=timedelta(seconds=step.get("timeoutSeconds", 600) + 30),
                    retry_policy=_retry_policy(step.get("retryPolicy", {})),
                )
                self._steps[step["id"]] = {
                    "status": "COMPLETED",
                    "input": step_payload,
                    "output": result["output"],
                    "attempt": result["attempt"],
                    "access": result.get("access"),
                }
                prev_outputs[step["id"]] = result["output"]
            except Exception as exc:
                # Activity 重试耗尽后 workflow 失败；用户走 reset 回放重试。
                # FAILED 状态写入 self._steps 让 query 在 reset 之前仍可读到失败原因。
                self._steps[step["id"]] = {
                    "status": "FAILED",
                    "input": step_payload,
                    "error": str(exc),
                }
                raise
        return {"status": "completed", "steps": self._steps}

    @workflow.query
    def get_steps(self) -> dict[str, Any]:
        return {"current": self._current_step, "steps": self._steps}


@workflow.defn(name="kg.custom.chain")
class ChainWorkflow:
    """多脚本串行链：按 definition.steps 顺序逐个执行已注册的 python 定义。

    与 kg.custom.steps 的区别：steps 要求单文件内多函数；chain 的每一步是一个
    独立上传的 python 定义（如单实体/单关系抽取脚本），上一步输出经
    payload["_prevOutputs"] 传给下一步（脚本可忽略）。状态走 get_steps query。
    """

    def __init__(self) -> None:
        self._steps: dict[str, dict[str, Any]] = {}
        self._current_step: str | None = None

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        await _register_scheduled_run(request)
        chain = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        prev_outputs: dict[str, Any] = {}
        for step in chain.get("steps", []):
            step_id = step["definitionId"]
            self._current_step = step_id
            step_definition = await workflow.execute_activity(
                load_workflow_definition,
                step_id,
                start_to_close_timeout=timedelta(seconds=30),
            )
            step_payload = {
                **(request.get("payload", {}) or {}),
                "_prevOutputs": prev_outputs,
            }
            timeout_seconds = max(int(step_definition.get("timeoutSeconds", 60)), 1)
            try:
                output = await workflow.execute_activity(
                    execute_python_script,
                    {
                        "scriptPath": step_definition["scriptPath"],
                        "functionName": step_definition.get("functionName", "workflow"),
                        "payload": step_payload,
                        "definitionId": step_id,
                        "timeoutSeconds": timeout_seconds,
                    },
                    start_to_close_timeout=timedelta(seconds=timeout_seconds + 30),
                    retry_policy=_retry_policy(step.get("retryPolicy", {})),
                )
                self._steps[step_id] = {
                    "status": "COMPLETED",
                    "name": step.get("name") or step_id,
                    "input": step_payload,
                    "output": output,
                }
                prev_outputs[step_id] = output
            except Exception as exc:
                self._steps[step_id] = {
                    "status": "FAILED",
                    "name": step.get("name") or step_id,
                    "input": step_payload,
                    "error": str(exc),
                }
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
    ChainWorkflow,
]

ACTIVITIES = [
    execute_kg_step,
    load_workflow_definition,
    execute_python_script,
    execute_pipeline_step,
    register_scheduled_execution,
]
