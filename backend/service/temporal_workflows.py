"""科技图谱 Temporal 工作流与 Activity 定义。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

logger = logging.getLogger(__name__)

# 单批行 JSON 序列化字节预算。两个 4MB 限制都要过：单条 activity 结果/输入
# 的 gRPC 上限，以及 workflow task 完成时**聚合多个在飞批次结果**的事务上限
# （max_inflight=3 + 队列积压，实测 3MB/批时事务 4.29MB 超限）→ 收紧到 512KB
_MAX_BATCH_ROWS_BYTES = 512 * 1024

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


# 单参入口 runner：调 workflow(payload)
_SINGLE_ARG_RUNNER = """
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

# 双参入口 runner：读 {"payload":..., "ctx":...} 一份 JSON，调 fn(payload, ctx)
_DUAL_ARG_RUNNER = """
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


async def _spawn_script(
    script_path: Path,
    function_name: str,
    stdin_data: bytes,
    ctx: dict[str, Any],
    timeout: float,
    runner: str,
    context_label: str,
) -> tuple[dict[str, Any], str]:
    """共享的脚本子进程启动逻辑（execute_python_script / execute_pipeline_step / 平台喂数抽取共用）。

    在隔离子进程中以 ``runner`` 调 ``script_path`` 的 ``function_name``；``ctx``
    经 ``KG_SCRIPT_CTX`` env 注入（单参脚本用 kg_sdk.current_context 取）。
    返回 ``(解析后的 stdout 包装 dict, sidecar 路径)``——调用方负责合并 access
    报告并在 finally 里 ``_cleanup_sidecar``。超时/非零退出抛 RuntimeError。
    """
    # 上传脚本需要 backend 模块（infra/dao/sdk）与凭据（MySQL/TRSGraph）。
    # worker 进程不 import infra，故这里显式加载 backend/.env，并把 backend + backend/sdk
    # 目录加入 PYTHONPATH。密钥经 env 传递的安全面与 MYSQL_PASSWORD 等
    # sub_env={**os.environ} 一致（见 docs/workflow_operations_api.md）。
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
    try:
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin_data), timeout=timeout
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            _log_failed_access(f"{context_label} 执行超时", sidecar_path)
            raise RuntimeError(f"{context_label} 执行超时") from None
        if process.returncode != 0:
            _log_failed_access(f"{context_label} 退出码 {process.returncode}", sidecar_path)
            raise RuntimeError(stderr.decode(errors="replace")[-4000:])
        wrapped = json.loads(stdout.decode() or "null")
        return wrapped, sidecar_path
    finally:
        pass  # sidecar 清理由调用方在合并 access 报告后进行


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
    payload = request.get("payload", {})
    resolved = _resolve_resources(payload, request.get("definitionId"), "_default")
    sidecar_path: str | None = None
    try:
        wrapped, sidecar_path = await _spawn_script(
            script_path,
            function_name,
            json.dumps(payload, ensure_ascii=False).encode(),
            resolved,
            float(request.get("timeoutSeconds", 60)),
            _SINGLE_ARG_RUNNER,
            "上传脚本",
        )
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
        "triggerSource": "SCHEDULE",
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
    sidecar_path: str | None = None
    try:
        wrapped, sidecar_path = await _spawn_script(
            script_path,
            function_name,
            json.dumps({"payload": payload, "ctx": ctx}, ensure_ascii=False).encode(),
            ctx,
            float(request.get("timeoutSeconds", 600)),
            _DUAL_ARG_RUNNER,
            f"step {request['stepId']}",
        )
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
                    template_id=str(item.get("templateId") or "T_DIRECT"),
                    workflow_type=(
                        "kg.schema.extract"
                        if str(item.get("templateId") or "T_DIRECT") != "T_DIRECT"
                        else None
                    ),
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


# ---------------------------------------------------------------------------
# Schema 平台喂数抽取（kg.schema.extract）
# ---------------------------------------------------------------------------

_MYSQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def _require_identifier(name: str) -> str:
    if not _MYSQL_IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"非法 MySQL 标识符: {name}")
    return name


def _jsonable(value: Any) -> Any:
    """把 MySQL 行值转成 JSON 可序列化形式（datetime→ISO、Decimal→float、bytes→str）。"""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, timedelta):
        return str(value)
    return value


@activity.defn
async def load_schema_extract_plan(schema_id: str) -> dict[str, Any]:
    """读控制库组装抽取计划：kind/name/activeProps（目录属性全集）/sources/脚本（S3 下载到临时文件）。"""
    from sqlalchemy.orm import Session as OrmSession

    from db_model.schema_management import GraphSchemaDefinition
    from infra.s3 import get_schema_s3_storage
    from infra.workflow_mysql import get_workflow_engine

    engine = get_workflow_engine()
    with OrmSession(engine) as session:
        definition = session.get(GraphSchemaDefinition, schema_id)
        if definition is None or definition.is_deleted:
            raise ValueError(f"Schema 不存在: {schema_id}")
        kind = definition.kind
        name = definition.name
        label = definition.label
        schema_key = definition.schema_key
        active_props = [p.name for p in definition.properties]
        sources = [
            {
                "id": item.id,
                "datasourceId": item.datasource_id,
                "databaseName": item.database_name,
                "tableName": item.table_name or "",
                "pkColumn": item.pk_column,
                "timeColumn": item.time_column or "",
                "querySql": getattr(item, "query_sql", None),
            }
            for item in definition.sources
        ]
        script = definition.script
        bucket = script.bucket if script else None
        object_key = script.object_key if script else None
        function_name = (script.workflow_function_name if script else None) or "transform"
        timeout_seconds = int(os.getenv("SCHEMA_WORKFLOW_TIMEOUT_SECONDS", "3600"))
        max_inflight = max(1, int(os.getenv("SCHEMA_EXTRACT_MAX_INFLIGHT", "3")))
        failure_case_cap = max(0, int(os.getenv("SCHEMA_EXTRACT_FAILURE_CASE_CAP", "2000")))
        index_timeout_seconds = max(
            60, int(os.getenv("SCHEMA_EXTRACT_INDEX_TIMEOUT_SECONDS", "1800"))
        )
    if bucket is None or object_key is None:
        raise ValueError(f"Schema 未上传脚本: {schema_id}")
    if not sources:
        raise ValueError(f"Schema 未绑定来源表: {schema_id}")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    storage = get_schema_s3_storage()
    body = None
    try:
        body = storage.get_object(bucket, object_key)
        data = body.read()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"下载 Schema 脚本失败: {exc}") from exc
    finally:
        if body is not None:
            try:
                body.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭脚本流失败: %s", schema_id)
    script_file = tempfile.NamedTemporaryFile(
        prefix=f"kg_schema_extract_{schema_key}_", suffix=".py", delete=False
    )
    script_file.write(data)
    script_file.close()
    return {
        "schemaId": schema_id,
        "schemaKey": schema_key,
        "kind": kind,
        "name": name,
        "label": label,
        "activeProps": active_props,
        "sources": sources,
        "scriptPath": script_file.name,
        "functionName": function_name,
        "timeoutSeconds": timeout_seconds,
        "maxInflight": max_inflight,
        "failureCaseCap": failure_case_cap,
        "indexTimeoutSeconds": index_timeout_seconds,
    }


def _validate_query_sql(query_sql: str) -> str:
    """校验来源绑定上的自定义查询为只读单条 SELECT/WITH。"""
    stripped = (query_sql or "").strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("querySql 不能为空")
    if ";" in stripped:
        raise ValueError("querySql 不允许包含多语句（;）")
    if not stripped.upper().startswith(("SELECT", "WITH")):
        raise ValueError("querySql 必须以 SELECT/WITH 开头（只读）")
    if re.search(r"\bINTO\b", stripped, re.IGNORECASE):
        raise ValueError("querySql 不允许包含 INTO（只读）")
    return stripped


def build_source_batch_sql(
    *,
    database: str,
    table: str | None,
    time_column: str | None,
    pk_column: str,
    query_sql: str | None = None,
    cursor_kind: str = "watermark",
    record_ids: list[Any] | None = None,
) -> str:
    """构造来源批次 SQL（纯函数，便于单测）。

    - 基表：``query_sql`` 存在时包成子查询（须暴露与 time/pk 同名的列），
      否则 ``{database}.{table}`` 全表；
    - watermark 模式（time_column 非空）：``WHERE time > :wm ORDER BY time, pk LIMIT :n``；
    - keyset 模式（time_column 为空）：``WHERE pk > :cursor ORDER BY pk LIMIT :n``（游标存 checkpoint）；
    - offset 模式（普通表，主键不保证唯一）：``[WHERE time > :wm] ORDER BY pk LIMIT :n OFFSET :offset``
      ——与旧脚本 LIMIT/OFFSET 同语义，增量靠时间列过滤 + 结束后一次性推水位；
    - ids 模式（重跑）：``WHERE pk IN (:id_0, ...)``（无 LIMIT，调用方按 500 分块）。
    """
    if query_sql:
        base = f"SELECT * FROM ({_validate_query_sql(query_sql)}) AS src"
    else:
        db = _require_identifier(database)
        tbl = _require_identifier(table or "")
        base = f"SELECT * FROM `{db}`.`{tbl}`"
    if cursor_kind == "ids":
        if not record_ids:
            raise ValueError("ids 模式必须提供 recordIds")
        placeholders = ", ".join(f":id_{i}" for i in range(len(record_ids)))
        return f"{base} WHERE `{pk_column}` IN ({placeholders})"
    if cursor_kind == "keyset":
        return f"{base} WHERE `{pk_column}` > :cursor ORDER BY `{pk_column}` LIMIT :n"
    if cursor_kind == "offset":
        where = f" WHERE `{time_column}` > :wm" if time_column else ""
        return f"{base}{where} ORDER BY `{pk_column}` LIMIT :n OFFSET :offset"
    if not time_column:
        raise ValueError("watermark 模式必须提供 timeColumn")
    return f"{base} WHERE `{time_column}` > :wm ORDER BY `{time_column}`, `{pk_column}` LIMIT :n"


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


_UNKNOWN_COLUMN_RE = re.compile(r"unknown column [`'\"]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _unknown_column_name(exc: Exception) -> str | None:
    """从图库报错解析 unknown column 列名（Nebula: ``Unknown column 'X' in schema``）。"""
    match = _UNKNOWN_COLUMN_RE.search(str(exc))
    return match.group(1) if match else None


@activity.defn
async def read_source_batch(request: dict[str, Any]) -> dict[str, Any]:
    """按来源绑定读一批行（连接参数由 activity 内按 datasourceId 解析，密钥不进 workflow 状态）。

    三种模式：
    - 水位模式（timeColumn 非空）：``WHERE time > :wm ORDER BY time, pk LIMIT :n``，返回 maxTime；
    - keyset 模式（timeColumn 为空）：``WHERE pk > :cursor ORDER BY pk LIMIT :n``，返回 maxPk；
    - recordIds 模式（重跑）：``WHERE pk IN (...)``，activity 内按 500 分块聚合，无水位。

    ``querySql`` 存在时以之为基础包子查询。首批未显式带游标且提供 definitionId/stepId
    时，activity 自行读持久化水位/keyset 游标（workflow 线程禁 DB 访问）。
    返回 ``{rows, recordIds, maxTime, maxPk}``。
    """
    from sqlalchemy import create_engine, text

    from service.mysql_datasource import get_mysql_settings_by_id
    from service.script_watermark import read_watermark

    datasource_id = request["datasourceId"]
    database = request.get("database") or ""
    table = request.get("table") or ""
    time_column = (request.get("timeColumn") or "").strip()
    pk_column = _require_identifier(request["pkColumn"])
    query_sql = request.get("querySql") or None
    batch_size = min(max(int(request.get("batchSize", 500)), 1), 5000)
    record_ids = request.get("recordIds")

    params = get_mysql_settings_by_id(datasource_id)
    if params is None:
        raise ValueError(f"来源数据源不存在: {datasource_id}")

    pagination = str(request.get("pagination") or "")
    if record_ids is not None:
        cursor_kind = "ids"
    elif pagination == "offset" or (not query_sql and pagination != "cursor"):
        cursor_kind = "offset"  # 普通表默认 offset（主键不保证唯一）
    elif time_column:
        cursor_kind = "watermark"
    else:
        cursor_kind = "keyset"

    binds: dict[str, Any] = {}
    if cursor_kind == "ids":
        pass  # 每块单独构造 binds
    elif cursor_kind == "offset":
        binds = {"n": batch_size, "offset": int(request.get("offset") or 0)}
        if time_column:
            watermark = request.get("watermark")
            if watermark is None and not request.get("chained"):
                wm_row = read_watermark(request.get("definitionId"), request.get("stepId") or "")
                watermark = (wm_row or {}).get("watermark") or "1970-01-01 00:00:00"
            if watermark is not None:
                binds["wm"] = str(watermark)
    elif cursor_kind == "watermark":
        watermark = request.get("watermark")
        if watermark is None:
            wm_row = read_watermark(request.get("definitionId"), request.get("stepId") or "")
            watermark = (wm_row or {}).get("watermark") or "1970-01-01 00:00:00"
        binds = {"wm": str(watermark), "n": batch_size}
    else:
        cursor = request.get("cursor")
        if cursor is None:
            wm_row = read_watermark(request.get("definitionId"), request.get("stepId") or "")
            cursor = ((wm_row or {}).get("checkpoint") or {}).get("pkCursor") or ""
        binds = {"cursor": str(cursor), "n": batch_size}

    sqls: list[tuple[str, dict[str, Any]]] = []
    if cursor_kind == "ids":
        for chunk in _chunked([str(i) for i in record_ids], 500):
            sql = build_source_batch_sql(
                database=database,
                table=table,
                time_column=time_column or None,
                pk_column=pk_column,
                query_sql=query_sql,
                cursor_kind="ids",
                record_ids=chunk,
            )
            sqls.append((sql, {f"id_{i}": v for i, v in enumerate(chunk)}))
    else:
        sql = build_source_batch_sql(
            database=database,
            table=table,
            time_column=time_column or None,
            pk_column=pk_column,
            query_sql=query_sql,
            cursor_kind=cursor_kind,
        )
        sqls.append((sql, binds))

    user = params["username"]
    password = params["password"]
    host = params["host"]
    port = int(params["port"])
    url = f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}?charset=utf8mb4"

    # Temporal 单条 activity 结果/输入受 gRPC 4MB 限制：大文本行（专利摘要等）
    # 一批 500 行轻易超限，activity 完成报 ResourceExhausted 无限重试。这里对
    # 游标/offset 模式自适应折半 LIMIT 直到序列化结果 ≤ 预算；未取的尾部行由
    # 下一批重读（游标按实际返回行推进），语义不丢数据。
    effective_batch = batch_size

    def _fetch(n: int) -> list[dict[str, Any]]:
        scaled_binds = {**binds, "n": n}
        scaled_sqls = [(sqls[0][0], scaled_binds)] if cursor_kind != "ids" else sqls
        fetched: list[dict[str, Any]] = []
        for sql, sql_binds in scaled_sqls:
            with engine.connect() as conn:
                for raw in conn.execute(text(sql), sql_binds).mappings().all():
                    fetched.append({k: _jsonable(v) for k, v in dict(raw).items()})
        return fetched

    engine = create_engine(url, pool_pre_ping=True)
    try:
        rows: list[dict[str, Any]] = []
        if cursor_kind == "ids":
            for sql, sql_binds in sqls:
                with engine.connect() as conn:
                    for raw in conn.execute(text(sql), sql_binds).mappings().all():
                        rows.append({k: _jsonable(v) for k, v in dict(raw).items()})
        else:
            n = batch_size
            while True:
                rows = _fetch(n)
                effective_batch = n
                if n <= 1:
                    break
                if len(json.dumps(rows, ensure_ascii=False, default=str).encode()) <= _MAX_BATCH_ROWS_BYTES:
                    break
                n = max(1, n // 2)
    finally:
        engine.dispose()

    max_time: str | None = None
    max_pk: str | None = None
    for row in rows:
        pk_value = row.get(pk_column)
        if pk_value is not None:
            max_pk = str(_jsonable(pk_value))
        if time_column:
            candidate = row.get(time_column)
            if candidate is not None and (max_time is None or str(candidate) > max_time):
                max_time = str(candidate)
    return {
        "rows": rows,
        "recordIds": [str(r.get(pk_column)) for r in rows if r.get(pk_column) is not None],
        "maxTime": max_time,
        "maxPk": max_pk,
        "effectiveBatchSize": effective_batch,
        # offset 模式回传本批生效的增量水位（时间列过滤起点），reader 链式透传
        **({"watermark": binds.get("wm")} if cursor_kind == "offset" else {}),
    }


@activity.defn
async def execute_transform(request: dict[str, Any]) -> dict[str, Any]:
    """把批次行交给脚本转换：payload["rows"] = 行 JSON，调脚本入口（默认 transform）。

    脚本只做转换，返回 ``{"entities": [{id, props}]}`` / ``{"edges": [{fromId, toId, props}]}``；
    可选 ``failures: [{recordId, error}]``（逐行解析失败 → 平台记 T_EXTRACT_FAIL 审核重跑）
    与 ``pendingReview: [...]``（低置信/消歧候选 → 审核队列，item 可带 templateId=T_LINK）。
    ctx 注入触发时选择的 mysql/graph/llm/embedding（未显式选 mysql 时回退来源绑定数据源，
    脚本内 resolver 可用 ``current_context().mysql.engine`` 加载查找表）。
    脚本的 ``_watermark``/``_checkpoint`` 元字段被忽略（水位由平台管理）。
    """
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    function_name = request.get("functionName", "transform")
    rows = request.get("rows") or []
    source = request.get("source") or {}
    kind = request.get("kind", "entity")
    payload = {
        "rows": rows,
        "source_table": f"{source.get('databaseName')}.{source.get('tableName')}",
        "kind": kind,
        "source": source,
    }
    resolved = _resolve_resources(
        request.get("selectors") or {},
        request.get("definitionId"),
        request.get("stepId") or "_default",
    )
    if "mysql" not in resolved and source.get("datasourceId"):
        try:
            from service.mysql_datasource import get_mysql_settings_by_id

            src_params = get_mysql_settings_by_id(source["datasourceId"])
            if src_params:
                resolved["mysql"] = {
                    **src_params,
                    "database": source.get("databaseName") or src_params.get("database"),
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析来源数据源 %s 失败: %s", source["datasourceId"], exc)
    resolved["source"] = {k: v for k, v in source.items() if k != "datasourceId"}
    sidecar_path: str | None = None
    try:
        wrapped, sidecar_path = await _spawn_script(
            script_path,
            function_name,
            json.dumps(payload, ensure_ascii=False).encode(),
            resolved,
            float(request.get("timeoutSeconds", 600)),
            _SINGLE_ARG_RUNNER,
            "平台喂数转换脚本",
        )
        output = (
            wrapped.get("result") if isinstance(wrapped, dict) and "result" in wrapped else wrapped
        )
        stdout_access = wrapped.pop("_access", None) if isinstance(wrapped, dict) else None
        access = _merge_access(stdout_access, sidecar_path)
        if access is not None and isinstance(output, dict):
            output = {**output, "access": access}
        # 忽略脚本的 _watermark/_checkpoint（平台按批次游标管理水位）
        output = _strip_watermark_meta(output)
        pending = output.pop("pendingReview", []) if isinstance(output, dict) else []
        if pending:
            _enqueue_pending_review(
                {**request, "stepId": request.get("stepId") or "extract"}, pending, 1
            )
        return output if isinstance(output, dict) else {}
    finally:
        _cleanup_sidecar(sidecar_path)


@activity.defn
async def write_records(request: dict[str, Any]) -> dict[str, Any]:
    """把转换结果写图：实体 nGQL INSERT VERTEX / 关系 merge_edge。

    实体走 nGQL ``INSERT VERTEX``（vid=记录 id，列级 upsert 幂等）——REST
    ``/nodes/merge`` 会把 id/name/vid 当身份键从属性剥离，而 Schema DDL 把
    id/name 建成 NOT NULL 列，merge 永远缺列。只写 activeProps 内的属性，
    Schema 注入的 NOT NULL 溯源列（create_time/update_time/source_table）
    缺省时由平台补默认值（脚本只管业务字段）。``graph.space`` 指定目标图空间。

    写图自愈：写图遇 ``GraphRequestError`` 且报错为 unknown column 时，从该条
    props 中剔除对应列重试（兜住「运行任务检查通过 → 任务恰好启动 → 属性被删」
    的时序窗口及一切计划快照与图库 schema 的错位）；无法定位列名则原样抛出。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from infra.graph_db.exceptions import GraphRequestError

    kind = request["kind"]
    name = request["name"]
    active_props = set(request.get("activeProps") or [])
    records = request.get("records") or []
    graph = request.get("graph") or {}
    source_table = str(request.get("sourceTable") or "")

    settings = TRSGraphSettings.from_env()
    space = graph.get("space")
    if space:
        settings.space = space
    client = TRSGraphClient(settings)

    def ngql_value(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(str(value), ensure_ascii=False)

    try:
        client.connect()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 列类型感知序列化：注册 schema 的业务列大量声明 string，而脚本输出的
        # 数值（计数/金额）是 int/float——数字字面量写 string 列会被 Nebula 拒绝
        # （"data type does not meet the requirements"）。DESCRIBE 一次拿列类型，
        # string 列一律转字符串，int/double 列保持数字字面量。
        column_types: dict[str, str] = {}
        not_null_cols: set[str] = set()
        try:
            described = client.execute_read(f"DESCRIBE {'TAG' if kind == 'entity' else 'EDGE'} `{name}`")
            for row in described.records or []:
                col = str(row.get("Field"))
                column_types[col] = str(row.get("Type")).lower()
                if str(row.get("Null")).upper() == "NO":
                    not_null_cols.add(col)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DESCRIBE %s %s 失败，按值类型写图: %s", kind, name, exc)

        def ngql_value_typed(value: Any, col: str | None) -> str:
            col_type = column_types.get(col or "", "") if col else ""
            if value is None:
                return "NULL"
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)) and not col_type.startswith("string"):
                return str(value)
            if isinstance(value, (int, float)):
                return json.dumps(str(value), ensure_ascii=False)
            return json.dumps(str(value), ensure_ascii=False)

        def filtered(props: dict[str, Any] | None) -> dict[str, Any]:
            if not props:
                return {}
            merged = dict(props)
            # Schema 注入的 NOT NULL 溯源列缺省时补默认值（脚本只管业务字段；
            # 其余溯源列可空，不强填以免类型不匹配）
            for key, default in (
                ("source_table", source_table or "platform"),
                ("create_time", now_str),
                ("update_time", now_str),
            ):
                if not active_props or key in active_props:
                    merged.setdefault(key, default)
            if not active_props:
                return merged
            result = {key: value for key, value in merged.items() if key in active_props}
            # 脚本没输出的 NOT NULL 列补类型适配的空值——缺列整条 INSERT 会被
            # Nebula 拒绝（"not null field doesn't have a default value"）
            for col in not_null_cols:
                if col in active_props and col not in result:
                    default = "" if column_types.get(col, "string").startswith("string") else "0"
                    result[col] = default
            return result

        def write_with_self_heal(record: dict[str, Any], props: dict[str, Any]) -> None:
            while True:
                try:
                    if kind == "entity":
                        cols = ", ".join(f"`{key}`" for key in props)
                        values = ", ".join(
                            ngql_value_typed(value, key) for key, value in props.items()
                        )
                        vid = json.dumps(str(record["id"]), ensure_ascii=False)
                        client.execute_write(
                            f"INSERT VERTEX `{name}`({cols}) VALUES {vid}:({values})"
                        )
                    else:
                        # 关系也走 nGQL INSERT EDGE（列级 upsert，同实体结论）：
                        # REST /edges/merge 要求 identityProps 非空（平台语义里
                        # 边以 from/to/rank 定位），空 identity 会被 400 拒绝
                        ecols = ", ".join(f"`{key}`" for key in props)
                        evalues = ", ".join(
                            ngql_value_typed(value, key) for key, value in props.items()
                        )
                        src = json.dumps(str(record["fromId"]), ensure_ascii=False)
                        dst = json.dumps(str(record["toId"]), ensure_ascii=False)
                        client.execute_write(
                            f"INSERT EDGE `{name}`({ecols}) VALUES {src}->{dst}:({evalues})"
                        )
                    return
                except GraphRequestError as exc:
                    bad_column = _unknown_column_name(exc)
                    if props and bad_column and bad_column in props and len(props) > 1:
                        logger.warning(
                            "写图遇未知列 %s，剔除后重试（%s %s）",
                            bad_column,
                            name,
                            record.get("id") or record.get("fromId"),
                        )
                        props.pop(bad_column)
                        continue
                    raise

        written = 0
        for record in records:
            props = filtered(record.get("props"))
            if kind == "entity" and not props:
                continue
            write_with_self_heal(record, props)
            written += 1
        return {"written": written}
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            logger.exception("关闭图客户端失败")


@activity.defn
async def detect_extract_collisions(request: dict[str, Any]) -> dict[str, Any]:
    """消歧 v1——同名冲突检测：对本批写入实体按显示名（props.name）查图库同名节点。

    同名不同 vid（含批内互相重名）→ T_LINK「实体对齐裁决」case，人工决定 merge；
    不阻塞写图。入队失败仅告警。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    name_tag = request["name"]
    records = request.get("records") or []
    graph = request.get("graph") or {}
    schema_key = request.get("schemaKey")

    by_name: dict[str, list[str]] = {}
    for record in records:
        props = record.get("props") or {}
        display = str(props.get("name") or "").strip()
        if not display:
            continue
        by_name.setdefault(display, []).append(str(record.get("id")))
    if not by_name:
        return {"collisions": 0}

    settings = TRSGraphSettings.from_env()
    if graph.get("space"):
        settings.space = graph["space"]
    client = TRSGraphClient(settings)
    existing: dict[str, list[str]] = {}
    try:
        client.connect()
        names = list(by_name)
        name_list = ",".join(json.dumps(n, ensure_ascii=False) for n in names)
        ngql = (
            f"MATCH (v:`{name_tag}`) WHERE v.name IN [{name_list}] "
            f"RETURN id(v) AS vid, v.name AS nm LIMIT 200"
        )
        result = client.execute_read(ngql)
        for rec in result.records or []:
            nm = str(rec.get("nm") or "")
            vid = str(rec.get("vid") or "")
            if nm and vid:
                existing.setdefault(nm, []).append(vid)
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            logger.exception("关闭图客户端失败")

    info = activity.info()
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(info.workflow_id) or {}
    except Exception:  # noqa: BLE001
        execution = {}
    task_id = execution.get("taskId") or f"PI-extract-{info.workflow_id[:12]}"
    execution_id = execution.get("id")

    from service.manual_review_production import manual_review_service

    collisions = 0
    for display, new_ids in by_name.items():
        existing_vids = [v for v in existing.get(display, []) if v not in new_ids]
        internal_dup = len(set(new_ids)) > 1
        if not existing_vids and not internal_dup:
            continue
        collisions += 1
        try:
            manual_review_service.create_direct_case(
                task_id=task_id,
                execution_id=execution_id,
                step_id=request.get("stepId") or "align",
                kind="entity",
                candidate={
                    "name": display,
                    "newIds": sorted(set(new_ids)),
                    "existingCandidates": [{"vid": v, "name": display} for v in existing_vids],
                    "schemaKey": schema_key,
                },
                object_id=sorted(set(new_ids))[0],
                object_name=display,
                node_label=name_tag,
                reason="同名实体冲突（不同 id），需人工对齐裁决",
                workflow_id=info.workflow_id,
                workflow_run_id=info.workflow_run_id,
                template_id="T_LINK",
                workflow_type="kg.schema.extract",
                exception_code="KG_EXTRACT_NAME_COLLISION",
                resume_token=f"extract-link:{execution_id}:{display}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("同名冲突 case 创建失败 name=%s: %s", display, exc)
    return {"collisions": collisions}


@activity.defn
async def record_extract_failures(request: dict[str, Any]) -> dict[str, Any]:
    """把逐行抽取失败落成 T_EXTRACT_FAIL 审核case（前端人工审核页展示、点击重跑）。"""
    info = activity.info()
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(info.workflow_id) or {}
    except Exception:  # noqa: BLE001
        execution = {}
    task_id = execution.get("taskId") or f"PI-extract-{info.workflow_id[:12]}"
    execution_id = execution.get("id")
    kind = request.get("kind", "entity")
    name = request.get("name")
    schema_id = request.get("schemaId")
    schema_key = request.get("schemaKey")
    job_id = request.get("jobId")

    from service.manual_review_production import manual_review_service

    recorded = 0
    for item in request.get("failures") or []:
        if not isinstance(item, dict):
            continue
        record_id = str(item.get("recordId") or "")
        if not record_id:
            continue
        source_table = item.get("sourceTable") or ""
        error = str(item.get("error") or "")[:1000]
        try:
            manual_review_service.create_direct_case(
                task_id=task_id,
                execution_id=execution_id,
                step_id="extract",
                kind=kind,
                candidate={"recordId": record_id, "error": error, "schemaKey": schema_key},
                object_id=record_id,
                object_name=f"{source_table}#{record_id}" if source_table else record_id,
                node_label=(name if kind == "entity" else None),
                edge_type=(name if kind != "entity" else None),
                reason=f"记录解析失败: {error}",
                workflow_id=info.workflow_id,
                workflow_run_id=info.workflow_run_id,
                source_table=source_table or None,
                source_record_id=record_id,
                service_actor="kg.schema.extract",
                template_id="T_EXTRACT_FAIL",
                workflow_type="kg.schema.extract",
                exception_code="KG_EXTRACT_RECORD_FAILED",
                resume_token=f"extract-fail:{execution_id}:{record_id}",
                extra_snapshot={
                    "schemaId": schema_id,
                    "schemaKey": schema_key,
                    "sourceBindingId": str(item.get("sourceBindingId") or ""),
                    "jobId": job_id,
                    "attempt": 1,
                },
            )
            recorded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("抽取失败 case 创建失败 record=%s: %s", record_id, exc)
    return {"recorded": recorded}


@activity.defn
async def resolve_failure_cases(request: dict[str, Any]) -> dict[str, Any]:
    """重跑执行结束后回写 T_EXTRACT_FAIL case：成功→RESOLVED；仍失败→新 case（attempt+1）。"""
    info = activity.info()
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(info.workflow_id) or {}
    except Exception:  # noqa: BLE001
        execution = {}
    task_id = execution.get("taskId") or f"PI-extract-{info.workflow_id[:12]}"

    from service.manual_review_production import manual_review_service

    result = manual_review_service.resolve_extract_rerun(
        rerun_case_ids=request.get("rerunCaseIds") or [],
        failed_records=request.get("failures") or [],
        rerun_execution_id=execution.get("id"),
        task_id=task_id,
        kind=request.get("kind", "entity"),
        name=request.get("name"),
    )
    return result


@activity.defn
async def build_entity_index(request: dict[str, Any]) -> dict[str, Any]:
    """重建实体 Milvus 混合检索索引（kg_entity 集合）：图 → embedding+BM25 → Milvus。

    reindex 为同步重操作（含全局单飞锁），放线程池执行；并发冲突由 activity 重试兜底。
    """
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    from infra.workflow_mysql import get_workflow_engine
    from service.entity_search import EntitySearchService

    space = request.get("space")
    entity_types = request.get("entityTypes") or []

    def _run() -> dict[str, Any]:
        # BM25 状态表（kg_entity_search_state）在控制库：与 handler 的
        # get_workflow_session 同源，走默认业务库会报 Table doesn't exist
        from sqlalchemy.orm import Session as OrmSession

        with OrmSession(get_workflow_engine()) as session:
            return EntitySearchService(session).reindex(space=space, entity_types=entity_types)

    result = await asyncio.to_thread(_run)
    return {"reindexed": result}


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
            retry_policy=ACTIVITY_RETRY_POLICY,
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

    每个脚本在 ``_steps[definitionId].activities`` 里记录其 activity steps：
    - 普通脚本（kg.custom.python）整体一个 execute_python_script activity；
    - steps 型脚本（kg.custom.steps，带 step manifest）按 manifest 逐步走
      execute_pipeline_step activity（修复 steps 型脚本进链后找不到 workflow()
      入口直接失败的问题）。任务详情页每个脚本一个 step，抽屉展开 activity steps。
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
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        prev_outputs: dict[str, Any] = {}
        for step in chain.get("steps", []):
            step_id = step["definitionId"]
            self._current_step = step_id
            step_definition = await workflow.execute_activity(
                load_workflow_definition,
                step_id,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
            step_payload = {
                **(request.get("payload", {}) or {}),
                "_prevOutputs": prev_outputs,
            }
            activities: dict[str, dict[str, Any]] = {}
            # RUNNING 先落 state：get_steps 查询可见脚本执行中，activities 原地更新
            self._steps[step_id] = {
                "status": "RUNNING",
                "name": step.get("name") or step_id,
                "input": step_payload,
                "activities": activities,
            }
            try:
                if step_definition.get("workflowType") == "kg.custom.steps" and step_definition.get(
                    "steps"
                ):
                    # steps 型脚本：manifest 每个函数一个 activity，脚本内 prevOutputs 链式传递
                    script_prev: dict[str, Any] = {}
                    for manifest_step in step_definition["steps"]:
                        manifest_step_id = manifest_step["id"]
                        try:
                            result = await workflow.execute_activity(
                                execute_pipeline_step,
                                {
                                    "taskId": request.get("taskId"),
                                    "executionId": request.get("executionId"),
                                    "definitionId": step_id,
                                    "stepId": manifest_step_id,
                                    "functionName": manifest_step["functionName"],
                                    "scriptPath": step_definition["scriptPath"],
                                    "payload": step_payload,
                                    "prevOutputs": script_prev,
                                    "timeoutSeconds": manifest_step.get("timeoutSeconds", 600),
                                },
                                start_to_close_timeout=timedelta(
                                    seconds=manifest_step.get("timeoutSeconds", 600) + 30
                                ),
                                retry_policy=_retry_policy(manifest_step.get("retryPolicy", {})),
                            )
                            activities[manifest_step_id] = {
                                "status": "COMPLETED",
                                "name": manifest_step.get("name") or manifest_step_id,
                                "input": step_payload,
                                "output": result["output"],
                                "attempt": result["attempt"],
                                "access": result.get("access"),
                            }
                            script_prev[manifest_step_id] = result["output"]
                        except Exception as exc:
                            activities[manifest_step_id] = {
                                "status": "FAILED",
                                "name": manifest_step.get("name") or manifest_step_id,
                                "input": step_payload,
                                "error": str(exc),
                            }
                            raise
                    output = script_prev
                else:
                    timeout_seconds = max(int(step_definition.get("timeoutSeconds", 60)), 1)
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
                    activities["execute"] = {
                        "status": "COMPLETED",
                        "name": "脚本执行",
                        "input": step_payload,
                        "output": output,
                    }
                self._steps[step_id] = {
                    "status": "COMPLETED",
                    "name": step.get("name") or step_id,
                    "input": step_payload,
                    "output": output,
                    "activities": activities,
                }
                prev_outputs[step_id] = output
            except Exception as exc:
                self._steps[step_id] = {
                    "status": "FAILED",
                    "name": step.get("name") or step_id,
                    "input": step_payload,
                    "error": str(exc),
                    "activities": activities,
                }
                raise
        return {"status": "completed", "steps": self._steps}

    @workflow.query
    def get_steps(self) -> dict[str, Any]:
        return {"current": self._current_step, "steps": self._steps}


_EXTRACT_SELECTOR_KEYS = (
    "mysql_datasource_id",
    "mysql_database",
    "milvus_config_id",
    "milvus_database",
    "graph_space",
    "llm_config_id",
    "embedding_config_id",
    "since",
)


@workflow.defn(name="kg.schema.extract")
class SchemaExtractWorkflow:
    """Schema 平台喂数抽取：分批读源表 → 脚本转换（只出 JSON）→ 平台写图/消歧/索引。

    - 来源间 ``asyncio.gather`` 并行；来源内 1 reader（串行读推进游标）+ N worker
      （转换→写图→冲突检测）经 ``asyncio.Queue(maxsize=N)`` 背压并发——十万级数据
      也不会一次进内存/一次跑完。
    - 游标（水位或 pk keyset）在该来源**全部批次成功后**一次性推进——并发处理下
      逐批推进会留洞；批次 activity 重试耗尽 → workflow FAILED，游标停在上一轮，
      下轮从断点续读（merge 写图幂等）。
    - 逐行失败由脚本捕获经 ``failures`` 返回（正常模式 → T_EXTRACT_FAIL 审核 case）；
      重跑模式（``recordIdsBySource``）批次失败不炸 workflow——整批记为失败记录，
      结束时 ``resolve_failure_cases`` 必调（case 不滞留 RERUNING）。
    - 结尾：实体构建 Milvus 索引（``buildIndex`` 默认实体开启）+ 同名冲突检测入
      T_LINK 人工对齐队列（消歧）。
    """

    def __init__(self) -> None:
        self._sources: dict[str, dict[str, Any]] = {}
        self._slots: dict[str, dict[int, dict[str, Any]]] = {}
        self._current_source: str | None = None

    async def _report_script_run(self, schema_id: str, *, ok: bool, error: str | None) -> None:
        """收尾回写脚本健康信号（best-effort，失败不影响主流程状态）。"""
        try:
            await workflow.execute_activity(
                record_schema_script_run,
                {
                    "schemaId": schema_id,
                    "status": "ok" if ok else "failed",
                    "error": error,
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
        except ActivityError:
            workflow.logger.warning("回写脚本运行状态失败: %s", schema_id)

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        schema_id = request["schemaId"]
        try:
            result = await self._extract(request)
        except Exception as exc:
            await self._report_script_run(schema_id, ok=False, error=str(exc)[:1000])
            raise
        await self._report_script_run(schema_id, ok=True, error=None)
        return result

    async def _extract(self, request: dict[str, Any]) -> dict[str, Any]:
        schema_id = request["schemaId"]
        graph_space = request.get("graphSpace") or request.get("graph_space")
        batch_size = min(max(int(request.get("batchSize", 500)), 1), 5000)
        graph = {"space": graph_space} if graph_space else {}
        plan = await workflow.execute_activity(
            load_schema_extract_plan,
            schema_id,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        timeout_seconds = max(int(plan.get("timeoutSeconds", 3600)), 60)
        kind = plan.get("kind", "entity")
        definition_id = f"schema-extract-{plan['schemaKey']}"

        # 周期 Schedule 触发：request 是扁平 shape（非 {definitionId, payload}），
        # 直接调注册 activity 落 execution/task 行（幂等）。
        schedule_id = request.get("_scheduleId")
        if schedule_id:
            info = workflow.info()
            await workflow.execute_activity(
                register_scheduled_execution,
                {
                    "definitionId": definition_id,
                    "scheduleId": schedule_id,
                    "workflowId": info.workflow_id,
                    "runId": info.run_id,
                    "payload": request,
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )

        rerun_ids: dict[str, list[Any]] = request.get("recordIdsBySource") or {}
        rerun_case_ids: list[str] = request.get("rerunCaseIds") or []
        rerun_mode = bool(rerun_ids)
        max_inflight = max(1, min(int(plan.get("maxInflight", 3)), 8))
        failure_cap = int(plan.get("failureCaseCap", 2000))
        detect_collisions = request.get("detectCollisions", True)
        selectors = {
            key: request[key] for key in _EXTRACT_SELECTOR_KEYS if request.get(key) is not None
        }

        async def extract_source(source: dict[str, Any]) -> dict[str, Any]:
            source_id = source["id"]
            step_id = f"source:{source_id}"
            table_label = (
                f"{source.get('databaseName')}.{source.get('tableName')}"
                if source.get("tableName")
                else "自定义查询"
            )
            self._current_source = step_id
            self._sources[step_id] = {
                "status": "RUNNING",
                "table": table_label,
                "batches": 0,
                "rows": 0,
                "written": 0,
                "failed": 0,
            }
            self._slots[step_id] = {}

            if rerun_mode and not (rerun_ids.get(source_id) or []):
                self._sources[step_id] = {**self._sources[step_id], "status": "COMPLETED"}
                return {
                    "source": step_id,
                    "table": table_label,
                    "batches": 0,
                    "rows": 0,
                    "written": 0,
                    "failed": 0,
                    "failures": [],
                    "watermark": None,
                    "pkCursor": None,
                }

            queue: asyncio.Queue = asyncio.Queue(maxsize=max_inflight)
            slots: dict[int, dict[str, Any]] = self._slots[step_id]
            pk_column = source["pkColumn"]

            async def reader() -> dict[str, Any]:
                read_base = {
                    "datasourceId": source["datasourceId"],
                    "database": source.get("databaseName") or "",
                    "table": source.get("tableName") or "",
                    "timeColumn": source.get("timeColumn") or "",
                    "pkColumn": pk_column,
                    "querySql": source.get("querySql"),
                    "batchSize": batch_size,
                    "definitionId": definition_id,
                    "stepId": step_id,
                }
                if rerun_mode:
                    read_base["recordIds"] = rerun_ids.get(source_id)
                    try:
                        batch = await workflow.execute_activity(
                            read_source_batch,
                            read_base,
                            start_to_close_timeout=timedelta(seconds=600),
                            retry_policy=ACTIVITY_RETRY_POLICY,
                        )
                    except ActivityError:
                        # 读源失败也是重跑失败：整批 id 记为失败，case 由 resolve 关闭并重建
                        return {
                            "batches": 0,
                            "readError": "读取来源记录失败",
                            "watermark": None,
                            "pkCursor": None,
                        }
                    await queue.put((0, batch))
                    return {"batches": 1, "watermark": None, "pkCursor": None}
                plain_table = not source.get("querySql")
                cursor: dict[str, Any] = {}
                offset = 0
                idx = 0
                final: dict[str, Any] = {}
                final_wm: str | None = None
                while True:
                    batch = await workflow.execute_activity(
                        read_source_batch,
                        {**read_base, **cursor},
                        start_to_close_timeout=timedelta(seconds=600),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                    )
                    rows = batch.get("rows") or []
                    if not rows:
                        break
                    await queue.put((idx, batch))
                    idx += 1
                    if batch.get("maxTime") and (final_wm is None or batch["maxTime"] > final_wm):
                        final_wm = batch["maxTime"]
                    if plain_table:
                        # 普通表 offset 分页（主键不保证唯一）；增量水位链式透传
                        offset += len(rows)
                        cursor = {"offset": offset, "chained": True}
                        if batch.get("watermark") is not None:
                            cursor["watermark"] = batch["watermark"]
                    else:
                        final = {"watermark": batch.get("maxTime"), "pkCursor": batch.get("maxPk")}
                        # 游标列全 NULL 时无法增量分页，读完一批即止（防死循环）
                        if final["watermark"] is None and final["pkCursor"] is None:
                            break
                        cursor = {k: v for k, v in final.items() if v is not None}
                    # 大文本行时 activity 会折半 LIMIT（结果 ≤ 4MB gRPC 上限）：
                    # 终止判断用本批实际请求量，防早停丢尾批
                    effective = int(batch.get("effectiveBatchSize") or batch_size)
                    if len(rows) < effective:
                        break
                if plain_table:
                    return {"batches": idx, "watermark": final_wm, "pkCursor": None}
                return {"batches": idx, **final}

            async def worker() -> list[dict[str, Any]]:
                failures: list[dict[str, Any]] = []
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    idx, batch = item
                    rows = batch.get("rows") or []
                    for start in range(0, len(rows), batch_size):
                        chunk = rows[start : start + batch_size]
                        chunk_ids = [str(r.get(pk_column)) for r in chunk]
                        written = 0
                        batch_failures: list[dict[str, Any]] = []
                        try:
                            transformed = await workflow.execute_activity(
                                execute_transform,
                                {
                                    "scriptPath": plan["scriptPath"],
                                    "functionName": plan["functionName"],
                                    "rows": chunk,
                                    "source": source,
                                    "kind": kind,
                                    "timeoutSeconds": timeout_seconds,
                                    "selectors": selectors,
                                    "definitionId": definition_id,
                                    "stepId": step_id,
                                },
                                start_to_close_timeout=timedelta(seconds=timeout_seconds + 60),
                                retry_policy=ACTIVITY_RETRY_POLICY,
                            )
                            records = transformed.get("entities") or transformed.get("edges") or []
                            if records:
                                write_result = await workflow.execute_activity(
                                    write_records,
                                    {
                                        "kind": kind,
                                        "name": plan["name"],
                                        "activeProps": plan["activeProps"],
                                        "records": records,
                                        "graph": graph,
                                        "sourceTable": table_label,
                                    },
                                    start_to_close_timeout=timedelta(seconds=600),
                                    retry_policy=ACTIVITY_RETRY_POLICY,
                                )
                                written = int(write_result.get("written", 0))
                            if kind == "entity" and records and detect_collisions:
                                await workflow.execute_activity(
                                    detect_extract_collisions,
                                    {
                                        "name": plan["name"],
                                        "records": records,
                                        "graph": graph,
                                        "schemaKey": plan["schemaKey"],
                                        "stepId": step_id,
                                    },
                                    start_to_close_timeout=timedelta(seconds=120),
                                    retry_policy=ACTIVITY_RETRY_POLICY,
                                )
                            batch_failures = [
                                {
                                    "sourceBindingId": source_id,
                                    "sourceTable": table_label,
                                    "recordId": str(f.get("recordId") or ""),
                                    "error": str(f.get("error") or ""),
                                }
                                for f in (transformed.get("failures") or [])
                                if isinstance(f, dict) and f.get("recordId") is not None
                            ]
                        except ActivityError:
                            if not rerun_mode:
                                raise
                            batch_failures = [
                                {
                                    "sourceBindingId": source_id,
                                    "sourceTable": table_label,
                                    "recordId": rid,
                                    "error": "批次执行失败（脚本或写图异常，整批记录待重跑）",
                                }
                                for rid in chunk_ids
                            ]
                        failures.extend(batch_failures)
                        prev = slots.get(idx) or {"rows": 0, "written": 0, "failed": 0}
                        slots[idx] = {
                            "rows": prev["rows"] + len(chunk),
                            "written": prev["written"] + written,
                            "failed": prev["failed"] + len(batch_failures),
                        }
                return failures

            async def guarded_reader() -> dict[str, Any]:
                # reader 正常结束后给每个 worker 发哨兵；reader 异常时也补发，
                # 让 worker 能收尾退出（异常仍向外传播使 workflow FAILED）。
                try:
                    return await reader()
                finally:
                    for _ in range(max_inflight):
                        await queue.put(None)

            outcomes = await asyncio.gather(
                guarded_reader(), *(worker() for _ in range(max_inflight))
            )
            read_summary = outcomes[0]
            source_failures = [f for out in outcomes[1:] for f in out]
            if rerun_mode and read_summary.get("readError"):
                source_failures.extend(
                    {
                        "sourceBindingId": source_id,
                        "sourceTable": table_label,
                        "recordId": str(rid),
                        "error": str(read_summary["readError"]),
                    }
                    for rid in (rerun_ids.get(source_id) or [])
                )
            total_rows = sum(s["rows"] for s in slots.values())
            total_written = sum(s["written"] for s in slots.values())

            # 游标一次性推进（全部批次成功才到这里；失败路径 gather 直接抛出）
            if not rerun_mode and read_summary.get("batches"):
                advance_req: dict[str, Any] = {
                    "definitionId": definition_id,
                    "stepId": step_id,
                }
                if read_summary.get("watermark") is not None:
                    advance_req["watermark"] = read_summary["watermark"]
                if read_summary.get("pkCursor") is not None:
                    advance_req["checkpoint"] = {"pkCursor": str(read_summary["pkCursor"])}
                if "watermark" in advance_req or "checkpoint" in advance_req:
                    await workflow.execute_activity(
                        advance_schema_extract_watermark,
                        advance_req,
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                    )

            self._sources[step_id] = {
                **self._sources[step_id],
                "status": "COMPLETED",
                "batches": read_summary.get("batches", 0),
                "rows": total_rows,
                "written": total_written,
                "failed": len(source_failures),
            }
            return {
                "source": step_id,
                "table": table_label,
                "batches": read_summary.get("batches", 0),
                "rows": total_rows,
                "written": total_written,
                "failed": len(source_failures),
                "failures": source_failures,
                "watermark": read_summary.get("watermark"),
                "pkCursor": read_summary.get("pkCursor"),
            }

        results = await asyncio.gather(*(extract_source(source) for source in plan["sources"]))
        all_failures = [f for r in results for f in (r.get("failures") or [])]
        truncated = len(all_failures) > failure_cap
        capped = all_failures[:failure_cap]
        index_summary: Any = None
        if rerun_mode:
            # 重跑：resolve 必调且拿全量失败键（未截断），仍失败记录由服务端重建 case
            await workflow.execute_activity(
                resolve_failure_cases,
                {
                    "rerunCaseIds": rerun_case_ids,
                    "rerunOfExecutionId": request.get("rerunOfExecutionId"),
                    "failures": all_failures,
                    "schemaId": schema_id,
                    "schemaKey": plan["schemaKey"],
                    "kind": kind,
                    "name": plan["name"],
                },
                start_to_close_timeout=timedelta(seconds=300),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
        else:
            do_index = request.get("buildIndex")
            if do_index is None:
                do_index = kind == "entity"
            if do_index and kind == "entity":
                # 索引是后置增强（embedding/Milvus 依赖外部服务），失败降级不拖垮抽取
                try:
                    index_result = await workflow.execute_activity(
                        build_entity_index,
                        {"space": graph_space, "entityTypes": [plan["name"]]},
                        start_to_close_timeout=timedelta(
                            seconds=int(plan.get("indexTimeoutSeconds", 1800))
                        ),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                    )
                    index_summary = (index_result or {}).get("reindexed")
                except ActivityError as exc:
                    index_summary = {"degraded": True, "error": str(exc)[:300]}
            if capped:
                await workflow.execute_activity(
                    record_extract_failures,
                    {
                        "failures": capped,
                        "schemaId": schema_id,
                        "schemaKey": plan["schemaKey"],
                        "kind": kind,
                        "name": plan["name"],
                        "jobId": request.get("jobId"),
                    },
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )

        return {
            "status": "completed",
            "schemaId": schema_id,
            "schemaKey": plan["schemaKey"],
            "kind": kind,
            "triggerSource": request.get("triggerSource", "MANUAL"),
            "sources": [{k: v for k, v in r.items() if k != "failures"} for r in results],
            "failures": {
                "count": len(all_failures),
                "recorded": len(capped),
                "truncated": truncated,
            },
            "rerun": (
                {"ofExecutionId": request.get("rerunOfExecutionId"), "caseIds": rerun_case_ids}
                if rerun_mode
                else None
            ),
            "index": index_summary,
        }

    @workflow.query
    def get_progress(self) -> dict[str, Any]:
        return {
            "current": self._current_source,
            "sources": self._sources,
            "slots": self._slots,
        }


@activity.defn
async def advance_schema_extract_watermark(request: dict[str, Any]) -> dict[str, Any]:
    """来源全部批次成功后一次性推进游标（step_id = source:{绑定行 id}，按绑定独立）。

    水位模式写 watermark（ISO 时间）；keyset 模式把 pk 游标写进 checkpoint.pkCursor
    （watermark 列是 DATETIME，非时间游标存 checkpoint）。
    """
    from service.script_watermark import write_watermark

    watermark = request.get("watermark")
    parsed = None
    if watermark:
        try:
            parsed = datetime.fromisoformat(str(watermark).replace(" ", "T"))
        except ValueError:
            parsed = None
    write_watermark(
        request.get("definitionId"),
        request["stepId"],
        watermark=parsed,
        checkpoint=request.get("checkpoint"),
    )
    return {"ok": True, "watermark": watermark, "checkpoint": request.get("checkpoint")}


@activity.defn
async def record_schema_script_run(request: dict[str, Any]) -> dict[str, Any]:
    """抽取工作流收尾回写脚本健康信号：``last_run_status`` = ok/failed + ``last_run_error``。

    与 staleness（captured_revision 版本号比较，事前可知）是两个独立维度：
    这里只反映"上次跑起来成没成"。schema 已删/脚本行不存在时静默跳过。
    """
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import Session as OrmSession

    from db_model.schema_management import GraphSchemaScript
    from infra.workflow_mysql import get_workflow_engine

    schema_id = request["schemaId"]
    status = "ok" if request.get("status") == "ok" else "failed"
    error = (str(request.get("error") or "").strip())[:1024] or None
    with OrmSession(get_workflow_engine()) as session:
        row = session.scalar(
            sa_select(GraphSchemaScript).where(GraphSchemaScript.schema_id == schema_id)
        )
        if row is None:
            return {"ok": False, "reason": "script-missing"}
        row.last_run_status = status
        row.last_run_error = error if status == "failed" else None
        session.commit()
    return {"ok": True, "status": status}


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
    SchemaExtractWorkflow,
]

ACTIVITIES = [
    execute_kg_step,
    load_workflow_definition,
    execute_python_script,
    execute_pipeline_step,
    register_scheduled_execution,
    load_schema_extract_plan,
    read_source_batch,
    execute_transform,
    write_records,
    advance_schema_extract_watermark,
    record_schema_script_run,
    detect_extract_collisions,
    record_extract_failures,
    resolve_failure_cases,
    build_entity_index,
]
