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
    """读控制库组装抽取计划：kind/name/activeProps（过滤 is_deleted）/sources/脚本（S3 下载到临时文件）。"""
    from sqlalchemy.orm import Session as OrmSession

    from db_model.schema_management import GraphSchemaDefinition
    from infra.s3 import get_schema_s3_storage
    from infra.workflow_mysql import get_workflow_engine

    engine = get_workflow_engine()
    with OrmSession(engine) as session:
        definition = session.get(GraphSchemaDefinition, schema_id)
        if definition is None:
            raise ValueError(f"Schema 不存在: {schema_id}")
        kind = definition.kind
        name = definition.name
        label = definition.label
        schema_key = definition.schema_key
        active_props = [p.name for p in definition.properties if not p.is_deleted]
        sources = [
            {
                "id": item.id,
                "datasourceId": item.datasource_id,
                "databaseName": item.database_name,
                "tableName": item.table_name,
                "pkColumn": item.pk_column,
                "timeColumn": item.time_column,
            }
            for item in definition.sources
        ]
        script = definition.script
        bucket = script.bucket if script else None
        object_key = script.object_key if script else None
        function_name = (script.workflow_function_name if script else None) or "workflow"
        timeout_seconds = int(os.getenv("SCHEMA_WORKFLOW_TIMEOUT_SECONDS", "3600"))
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
    }


@activity.defn
async def read_source_batch(request: dict[str, Any]) -> dict[str, Any]:
    """按时间列水位读取一批行：``SELECT * FROM db.table WHERE time > :wm ORDER BY time, pk LIMIT :n``。

    连接参数由 activity 内按 datasourceId 解析（密钥只在 worker 进程内，不进 workflow
    状态）。标识符经白名单校验防注入；时间/主键列参数化绑定。
    返回 ``{rows, maxTime}``——rows 为 JSON 行，maxTime 为本批最大时间列值（推进水位）。
    """
    from sqlalchemy import create_engine, text

    from service.mysql_datasource import get_mysql_settings_by_id

    datasource_id = request["datasourceId"]
    database = _require_identifier(request["database"])
    table = _require_identifier(request["table"])
    time_column = _require_identifier(request["timeColumn"])
    pk_column = _require_identifier(request["pkColumn"])
    watermark = request.get("watermark") or "1970-01-01 00:00:00"
    batch_size = min(max(int(request.get("batchSize", 500)), 1), 5000)

    params = get_mysql_settings_by_id(datasource_id)
    if params is None:
        raise ValueError(f"来源数据源不存在: {datasource_id}")
    user = params["username"]
    password = params["password"]
    host = params["host"]
    port = int(params["port"])
    url = f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}?charset=utf8mb4"
    engine = create_engine(url, pool_pre_ping=True)
    try:
        sql = text(
            f"SELECT * FROM `{database}`.`{table}` "
            f"WHERE `{time_column}` > :wm "
            f"ORDER BY `{time_column}`, `{pk_column}` LIMIT :n"
        )
        with engine.connect() as conn:
            raw_rows = conn.execute(sql, {"wm": watermark, "n": batch_size}).mappings().all()
    finally:
        engine.dispose()

    rows: list[dict[str, Any]] = []
    max_time: str | None = None
    for raw in raw_rows:
        row = {key: _jsonable(value) for key, value in dict(raw).items()}
        rows.append(row)
        candidate = row.get(time_column)
        if candidate is not None and (max_time is None or str(candidate) > max_time):
            max_time = str(candidate)
    return {"rows": rows, "maxTime": max_time}


@activity.defn
async def execute_transform(request: dict[str, Any]) -> dict[str, Any]:
    """把批次行交给脚本转换：payload["rows"] = 行 JSON，调 workflow(payload)。

    脚本返回 ``{"entities": [{id, props}]}`` 或 ``{"edges": [{fromId, toId, props}]}``；
    脚本的 ``_watermark``/``_checkpoint`` 元字段被忽略（水位由平台管理）。
    """
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    function_name = request.get("functionName", "workflow")
    rows = request.get("rows") or []
    source = request.get("source") or {}
    kind = request.get("kind", "entity")
    payload = {
        "rows": rows,
        "source_table": f"{source.get('databaseName')}.{source.get('tableName')}",
        "kind": kind,
        "source": source,
    }
    sidecar_path: str | None = None
    try:
        wrapped, sidecar_path = await _spawn_script(
            script_path,
            function_name,
            json.dumps(payload, ensure_ascii=False).encode(),
            {},
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
        # 忽略脚本的 _watermark/_checkpoint（平台按批次 maxTime 管理水位）
        output = _strip_watermark_meta(output)
        return output if isinstance(output, dict) else {}
    finally:
        _cleanup_sidecar(sidecar_path)


@activity.defn
async def write_records(request: dict[str, Any]) -> dict[str, Any]:
    """把转换结果 merge 写图：实体 merge_node / 关系 merge_edge。

    只写 activeProps 内的属性——已删属性「插空」即省略键（图库列不动）。
    ``graph.space`` 指定目标图空间（默认 TRS_GRAPH_SPACE）。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    kind = request["kind"]
    name = request["name"]
    active_props = set(request.get("activeProps") or [])
    records = request.get("records") or []
    graph = request.get("graph") or {}

    settings = TRSGraphSettings.from_env()
    space = graph.get("space")
    if space:
        settings.space = space
    client = TRSGraphClient(settings)
    try:
        client.connect()

        def filtered(props: dict[str, Any] | None) -> dict[str, Any]:
            if not props:
                return {}
            if not active_props:
                return dict(props)
            return {key: value for key, value in props.items() if key in active_props}

        written = 0
        if kind == "entity":
            for record in records:
                client.merge_node([name], {"id": record["id"]}, filtered(record.get("props")))
                written += 1
        else:
            for record in records:
                client.merge_edge(
                    record["fromId"], record["toId"], name, {}, filtered(record.get("props"))
                )
                written += 1
        return {"written": written}
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            logger.exception("关闭图客户端失败")


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


@workflow.defn(name="kg.schema.extract")
class SchemaExtractWorkflow:
    """Schema 平台喂数抽取：读源表批次 → 脚本转换 → merge 写图 → 推水位。

    各来源表 ``asyncio.gather`` 并行（仅 await activity，deterministic 安全）；
    单来源内批次串行（读→转→写→推水位），直到本批行数 < batchSize。
    水位键 ``schema-extract-{key}`` + step ``source:{绑定行 id}``——按绑定独立推进。
    """

    def __init__(self) -> None:
        self._sources: dict[str, dict[str, Any]] = {}
        self._current_source: str | None = None

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        schema_id = request["schemaId"]
        graph_space = request.get("graphSpace")
        batch_size = int(request.get("batchSize", 500))
        graph = {"space": graph_space} if graph_space else {}
        plan = await workflow.execute_activity(
            load_schema_extract_plan,
            schema_id,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        timeout_seconds = max(int(plan.get("timeoutSeconds", 3600)), 60)
        definition_id = f"schema-extract-{plan['schemaKey']}"

        async def extract_source(source: dict[str, Any]) -> dict[str, Any]:
            source_id = source["id"]
            step_id = f"source:{source_id}"
            self._current_source = step_id
            self._sources[step_id] = {
                "status": "RUNNING",
                "table": f"{source['databaseName']}.{source['tableName']}",
                "batches": 0,
                "rows": 0,
                "written": 0,
            }
            try:
                from service.script_watermark import read_watermark

                watermark = None
                wm_row = read_watermark(definition_id, step_id)
                if wm_row:
                    watermark = wm_row.get("watermark")
            except Exception as exc:  # noqa: BLE001
                logger.warning("读水位失败 %s/%s: %s", definition_id, step_id, exc)
                watermark = None

            total_rows = 0
            total_written = 0
            batches = 0
            while True:
                batch = await workflow.execute_activity(
                    read_source_batch,
                    {
                        "datasourceId": source["datasourceId"],
                        "database": source["databaseName"],
                        "table": source["tableName"],
                        "timeColumn": source["timeColumn"],
                        "pkColumn": source["pkColumn"],
                        "watermark": watermark,
                        "batchSize": batch_size,
                    },
                    start_to_close_timeout=timedelta(seconds=300),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
                rows = batch.get("rows") or []
                max_time = batch.get("maxTime")
                if not rows:
                    break
                batches += 1
                total_rows += len(rows)
                transformed = await workflow.execute_activity(
                    execute_transform,
                    {
                        "scriptPath": plan["scriptPath"],
                        "functionName": plan["functionName"],
                        "rows": rows,
                        "source": source,
                        "kind": plan["kind"],
                        "timeoutSeconds": timeout_seconds,
                    },
                    start_to_close_timeout=timedelta(seconds=timeout_seconds + 60),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
                records = transformed.get("entities") or transformed.get("edges") or []
                if records:
                    write_result = await workflow.execute_activity(
                        write_records,
                        {
                            "kind": plan["kind"],
                            "name": plan["name"],
                            "activeProps": plan["activeProps"],
                            "records": records,
                            "graph": graph,
                        },
                        start_to_close_timeout=timedelta(seconds=600),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                    )
                    total_written += int(write_result.get("written", 0))
                self._sources[step_id] = {
                    **self._sources[step_id],
                    "batches": batches,
                    "rows": total_rows,
                    "written": total_written,
                }
                if max_time and max_time != watermark:
                    await workflow.execute_activity(
                        advance_schema_extract_watermark,
                        {
                            "definitionId": definition_id,
                            "stepId": step_id,
                            "watermark": max_time,
                        },
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                    )
                    watermark = max_time
                if len(rows) < batch_size:
                    break
            self._sources[step_id] = {
                **self._sources[step_id],
                "status": "COMPLETED",
                "watermark": watermark,
            }
            return {
                "source": step_id,
                "table": f"{source['databaseName']}.{source['tableName']}",
                "batches": batches,
                "rows": total_rows,
                "written": total_written,
                "watermark": watermark,
            }

        results = await asyncio.gather(*(extract_source(source) for source in plan["sources"]))
        return {"status": "completed", "schemaId": schema_id, "sources": list(results)}

    @workflow.query
    def get_progress(self) -> dict[str, Any]:
        return {"current": self._current_source, "sources": self._sources}


@activity.defn
async def advance_schema_extract_watermark(request: dict[str, Any]) -> dict[str, Any]:
    """批次成功写图后推进该来源绑定的水位（step_id = source:{绑定行 id}，按绑定独立）。"""
    from service.script_watermark import write_watermark

    watermark = request.get("watermark")
    parsed = None
    if watermark:
        try:
            parsed = datetime.fromisoformat(str(watermark).replace(" ", "T"))
        except ValueError:
            parsed = None
    write_watermark(request.get("definitionId"), request["stepId"], watermark=parsed)
    return {"ok": True, "watermark": watermark}


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
]
