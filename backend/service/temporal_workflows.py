"""科技图谱 Temporal 工作流与 Activity 定义。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

from service.script_steps import extract_declared_steps

logger = logging.getLogger(__name__)

# 单批行 JSON 序列化字节预算。两个 4MB 限制都要过：单条 activity 结果/输入
# 的 gRPC 上限，以及 workflow task 完成时**聚合多个在飞批次结果**的事务上限
# （max_inflight=3 + 队列积压，实测 3MB/批时事务 4.29MB 超限）→ 收紧到 512KB
_MAX_BATCH_ROWS_BYTES = 512 * 1024

# 多步链（脚本顶层 STEPS 声明）的步间透传预算（第 N>1 步 request 的 input 单值 /
# prevOutputs 单值上限）。步输出既要作为 activity 返回值过 gRPC 上限，又要随批间
# 并发聚合进 workflow 事件历史，故与批行预算同量级；超限值截断为 _truncated 标记
# （stats 小则保留）——脚本应避免在步间传递超大数据，需要重负载时直接读源表。
_MAX_STEP_CHAIN_BYTES = 512 * 1024
_MAX_PREV_OUTPUT_BYTES = 128 * 1024
# 步输出中「额外键」（entities/edges/failures/pendingReview 之外的中转数据）的
# 序列化预算：超限在 activity 返回前截断为标记，防巨型中间输出先炸 activity 完成事件。
_MAX_STEP_EXTRA_BYTES = 256 * 1024

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


def _strip_watermark_meta(output: Any) -> Any:
    """从脚本返回里剥离 ``_watermark``/``_checkpoint`` 元字段，避免污染 step 输出展示。"""
    if isinstance(output, dict):
        output.pop("_watermark", None)
        output.pop("_checkpoint", None)
    return output


def _json_size(value: Any) -> int:
    """值的 JSON 序列化字节数（不可序列化时返回 0，交由上游正常失败）。"""
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode())
    except (TypeError, ValueError):
        return 0


def _shrink_chain_value(value: Any, *, budget: int, label: str) -> Any:
    """步间透传大小防护：超预算的步输出截断为 ``_truncated`` 标记（stats 小则保留）。

    纯函数（仅依赖入参），workflow 内调用重放安全。被截断时记 warning 便于排查
    「下游步拿不到完整上一步输出」的问题。
    """
    size = _json_size(value)
    if size <= budget:
        return value
    marker: dict[str, Any] = {"_truncated": True, "_originalBytes": size}
    stats = value.get("stats") if isinstance(value, dict) else None
    if isinstance(stats, dict) and _json_size(stats) <= 4096:
        marker["stats"] = stats
    logger.warning("%s 序列化后 %d 字节超预算 %d，步间透传已截断为标记", label, size, budget)
    return marker


def _truncate_step_extras(output: dict[str, Any]) -> dict[str, Any]:
    """步输出的额外键（中转数据）超预算时截断，保住平台契约键与 stats。

    多步链里中间步可能返回大体积中转数据：它既要作为本 activity 的返回值过
    gRPC 上限，又要作为下一步 input 透传，故在返回前就把额外键压到预算内；
    ``entities``/``edges``/``failures`` 是平台契约键（写图/审核要用），不截断。
    """
    extras = {k: v for k, v in output.items() if k not in ("entities", "edges", "failures")}
    size = _json_size(extras)
    if size <= _MAX_STEP_EXTRA_BYTES:
        return output
    truncated = {k: v for k, v in output.items() if k in ("entities", "edges", "failures")}
    stats = extras.get("stats")
    if isinstance(stats, dict) and _json_size(stats) <= 4096:
        truncated["stats"] = stats
    truncated["_stepExtras"] = {"_truncated": True, "_originalBytes": size}
    logger.warning(
        "步输出额外键合计 %d 字节超预算 %d，已截断（保留 entities/edges/failures 与 stats）",
        size,
        _MAX_STEP_EXTRA_BYTES,
    )
    return truncated


# ---------------------------------------------------------------------------
# 抽取载荷 S3 中转（claim-check）共用的纯函数 / activity 内 IO 助手。
# 纯函数部分可被 workflow 代码直接调用（只依赖入参，重放安全）。
# ---------------------------------------------------------------------------


def _source_table_label(source: dict[str, Any]) -> str:
    """来源绑定的展示标签（与 workflow 内 table_label 逐字一致）。"""
    if source.get("tableName"):
        return f"{source.get('databaseName')}.{source.get('tableName')}"
    return "自定义查询"


def _shape_step_failures(
    raw_failures: Any, *, source_binding_id: Any, table_label: str
) -> list[dict[str, Any]]:
    """脚本 ``failures`` 整形为平台失败记录（无 recordId 的条目丢弃，error 不截断）。"""
    return [
        {
            "sourceBindingId": source_binding_id,
            "sourceTable": table_label,
            "recordId": str(f.get("recordId") or ""),
            "error": str(f.get("error") or ""),
        }
        for f in (raw_failures or [])
        if isinstance(f, dict) and f.get("recordId") is not None
    ]


def _failure_entries_count(entries: list[dict[str, Any]]) -> int:
    """失败条目计数：内联 dict 每条 1；S3 中转 ref 按其 count。"""
    return sum(int(e.get("count") or 0) if "failuresKey" in e else 1 for e in entries)


def _iter_batch_chunks(
    batch: dict[str, Any], batch_size: int, pk_column: str
) -> Iterator[dict[str, Any]]:
    """批内 chunk 统一化（纯函数，workflow 内重放安全）。

    - S3 中转形状（read 返回 ``chunks`` 元数据）：逐 chunk 透传 key/行数/记录 id；
    - 内联旧形状（在飞 run 重放 / 未开 flag）：按 batch_size 切 rows，与历史行为一致。
    """
    if "chunks" in batch:
        for position, meta in enumerate(batch["chunks"] or []):
            yield {
                "index": position,
                "rowCount": int(meta.get("rowCount") or 0),
                "recordIds": meta.get("recordIds") or [],
                "rowsKey": meta.get("key"),
            }
        return
    rows = batch.get("rows") or []
    for start in range(0, len(rows), batch_size):
        chunk_rows = rows[start : start + batch_size]
        yield {
            "index": start // batch_size,
            "rowCount": len(chunk_rows),
            "recordIds": [str(r.get(pk_column)) for r in chunk_rows],
            "rows": chunk_rows,
        }


def _split_rows_for_upload(
    rows: list[dict[str, Any]], batch_size: int, budget: int
) -> list[list[dict[str, Any]]]:
    """载荷上传分组：先按 batch_size 分组，超预算组递归折半（单行超预算原样上传）。"""
    groups: list[list[dict[str, Any]]] = []

    def emit(group: list[dict[str, Any]]) -> None:
        if len(group) <= 1 or _json_size(group) <= budget:
            groups.append(group)
            return
        mid = len(group) // 2
        emit(group[:mid])
        emit(group[mid:])

    for start in range(0, len(rows), batch_size):
        emit(rows[start : start + batch_size])
    return groups


def _activity_info_safe() -> Any:
    """activity 上下文；单测直调（无 activity 上下文）时给 local- 占位。"""
    from types import SimpleNamespace

    try:
        return activity.info()
    except RuntimeError:
        return SimpleNamespace(workflow_id=f"local-{uuid4().hex}", workflow_run_id=None, attempt=1)


async def _load_records_from_key(records_key: str) -> list[Any]:
    """recordsKey 下载：全量输出对象（dict）取 entities/edges；消歧产物（list）直用。"""
    from service.extract_payload_store import load_extract_payload_json

    data = await asyncio.to_thread(load_extract_payload_json, records_key)
    if isinstance(data, dict):
        return data.get("entities") or data.get("edges") or []
    return data if isinstance(data, list) else []


async def _expand_failure_items(request: dict[str, Any]) -> list[dict[str, Any]]:
    """失败条目展开：内联清单 + failureRefs 逐个下载（IO 在 activity 内，失败交重试）。"""
    items = [f for f in (request.get("failures") or []) if isinstance(f, dict)]
    refs = request.get("failureRefs") or []
    if not refs:
        return items
    from service.extract_payload_store import load_extract_payload_json

    for ref in refs:
        key = (ref or {}).get("failuresKey")
        if not key:
            continue
        data = await asyncio.to_thread(load_extract_payload_json, key)
        if isinstance(data, list):
            items.extend(f for f in data if isinstance(f, dict))
    return items


async def _transform_result_via_s3(
    request: dict[str, Any], output: Any, access: Any
) -> dict[str, Any]:
    """S3 中转下的 execute_transform 返回形状：全量输出与失败清单归档，历史只进元数据。

    ``output`` 为脚本原始输出（pendingReview 已弹出、水位元字段已剥离、access 未混入
    ——access 属平台观测数据，保持内联返回的现行为）。
    """
    from service.extract_payload_store import put_extract_payload_json

    output_dict = output if isinstance(output, dict) else {}
    records = output_dict.get("entities") or output_dict.get("edges") or []
    source = request.get("source") or {}
    step_key_id = request.get("ctxStepId") or request.get("stepId") or "_default"
    batch_idx = int(request.get("batchIdx") or 0)
    chunk_tag = f"{int(request.get('chunkIdx') or 0):02d}"
    out_key = await asyncio.to_thread(
        put_extract_payload_json, step_key_id, batch_idx, f"out-{chunk_tag}", output
    )
    shaped = _shape_step_failures(
        output_dict.get("failures"),
        source_binding_id=source.get("id"),
        table_label=_source_table_label(source),
    )
    result: dict[str, Any] = {
        "outKey": out_key,
        "hasRecords": bool(records),
        "entityCount": len(output_dict.get("entities") or []),
        "edgeCount": len(output_dict.get("edges") or []),
        "failureCount": len(shaped),
    }
    if shaped:
        result["failuresKey"] = await asyncio.to_thread(
            put_extract_payload_json, step_key_id, batch_idx, f"failures-{chunk_tag}", shaped
        )
    stats = output_dict.get("stats")
    if isinstance(stats, dict) and _json_size(stats) <= 4096:
        result["stats"] = stats
    if access is not None:
        result["access"] = access
    return result


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


def _write_private_tempfile(*, prefix: str, suffix: str, data: bytes | None = None) -> str:
    """Create a private temporary file outside the event-loop thread."""
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as handle:
        if data is not None:
            handle.write(data)
        return handle.name


async def _spawn_script(
    script_path: Path,
    function_name: str,
    stdin_data: bytes,
    ctx: dict[str, Any],
    timeout: float,
    runner: str,
    context_label: str,
) -> tuple[dict[str, Any], str]:
    """共享的脚本子进程启动逻辑（平台喂数抽取 execute_transform 共用）。

    在隔离子进程中以 ``runner`` 调 ``script_path`` 的 ``function_name``；``ctx``
    经 ``KG_SCRIPT_CTX`` env 注入（单参脚本用 kg_sdk.current_context 取）。
    返回 ``(解析后的 stdout 包装 dict, sidecar 路径)``——调用方负责合并 access
    报告并在 finally 里 ``_cleanup_sidecar``。超时/非零退出抛 RuntimeError。
    """
    # 上传脚本需要 backend 模块（infra/dao/sdk）与凭据（MySQL/TRSGraph）。
    # worker 进程不 import infra，故这里显式加载 backend/.env，并把 backend + backend/sdk
    # 目录加入 PYTHONPATH。密钥经 env 传递的安全面与 MYSQL_PASSWORD 等
    # sub_env={**os.environ} 一致。
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    sdk_dir = backend_dir / "sdk"
    pythonpath = os.pathsep.join(
        filter(None, [str(backend_dir), str(sdk_dir), str(script_path.parent)])
    )
    sidecar_path = await asyncio.to_thread(
        _write_private_tempfile, prefix="kg_access_", suffix=".jsonl"
    )
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
async def load_workflow_definition(definition_id: str) -> dict[str, Any]:
    # 延迟导入避免 Workflow sandbox 在模块加载阶段访问 SQLite。
    from service.workflow_repository import repository

    definition = repository.get_definition(definition_id)
    if definition is None:
        raise ValueError(f"工作流定义不存在: {definition_id}")
    return definition


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


def _pending_graph_client(space: str | None) -> Any:
    """为 pendingReview 挂实体消歧建图客户端（space 缺省走环境默认空间）。

    独立成模块级函数便于单测 monkeypatch（不真连图）。调用方负责 close。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    settings = TRSGraphSettings.from_env()
    if space:
        settings.space = space
    client = TRSGraphClient(settings)
    client.connect()
    return client


def _enqueue_entity_pending_item(
    item: dict[str, Any],
    *,
    step_id: str,
    client: Any,
    space: str | None,
    task_id: str,
    execution_id: str | None,
    workflow_id: str,
    workflow_run_id: str | None,
    job_id: str | None = None,
) -> None:
    """单个挂起实体项 → 图库同名召回 + 评分 → T_LINK case（强制灰区人裁）。

    与 ``resolve_entity_batch`` 灰区分支同构（_incoming/existingCandidates/
    _pendingRelations），前端与 _apply_link_verdict 直接复用；但**不走 decide 的
    auto-merge**——挂起实体的边端点悬在未决 vid 上，自动并入已有实体会让边永远
    挂在无人裁决的 vid 上（park_or_rewrite 只认 case.object_id），必须由人裁
    merge/create 改写端点后补写。``objectId`` 必须是脚本按归一名生成的确定性
    vid（同名字段归并到同一 case），dedupe_key 即按它稳定。
    """
    from service import entity_disambiguation as ed
    from service.entity_disambiguation import GRAY_LOW, MERGE_THRESHOLD, TOP_K
    from service.manual_review_production import manual_review_service

    candidate = item.get("candidate") or {}
    display = str(item.get("objectName") or candidate.get("name") or "").strip()
    vid = str(item.get("objectId") or "").strip()
    node_label = str(item.get("nodeLabel") or "").strip()
    if not (display and vid and node_label):
        raise ValueError("pendingReview 实体项缺 objectName/objectId/nodeLabel")
    incoming_props = dict(candidate.get("props") or {})
    incoming_props.setdefault("name", display)
    scored: list[dict[str, Any]] = []
    for cand in ed.recall_same_name(client, node_label, [display]).get(display, []):
        if cand["vid"] == vid:
            continue
        score, detail = ed.score_candidate(display, incoming_props, cand["name"], cand.get("props"))
        scored.append(
            {"vid": cand["vid"], "name": cand["name"], "score": round(score, 3), **detail}
        )
    top = sorted(scored, key=lambda x: x["score"], reverse=True)[:TOP_K]
    reason = (
        f"脚本挂起改道消歧：{item.get('reason') or '歧义实体待人工确认'}；同名候选 {len(scored)} 个"
    )
    if top:
        reason += f"，最高得分 {top[0]['score']:.2f}"
    manual_review_service.create_direct_case(
        task_id=task_id,
        execution_id=execution_id,
        step_id=step_id,
        kind="entity",
        candidate={
            "name": display,
            "newIds": [vid],
            "existingCandidates": [
                {"vid": c["vid"], "name": c["name"], "score": c["score"]} for c in top
            ],
            "_incoming": {
                "vid": vid,
                "props": incoming_props,
                "sourceTable": item.get("sourceTable") or "",
            },
            "_pendingRelations": [],
            "_graphSpace": space,
            "_resolution": {
                "policyVersion": "script-pending-gray-v1",
                "scriptReason": item.get("reason"),
                "thresholds": {"merge": MERGE_THRESHOLD, "grayLow": GRAY_LOW},
            },
        },
        object_id=vid,
        object_name=display,
        node_label=node_label,
        reason=reason,
        confidence=item.get("confidence"),
        evidence=item.get("evidence") or [],
        workflow_id=workflow_id,
        workflow_run_id=workflow_run_id,
        domain=item.get("domain", "graph"),
        source_record=item.get("sourceRecord"),
        source_table=item.get("sourceTable"),
        source_record_id=item.get("sourceRecordId"),
        llm_input=item.get("llmInput"),
        llm_output=item.get("llmOutput"),
        # 来源记录跳任务详情（同 lizhou_fix 64f815c 的观测契约）：jobId 进
        # input_snapshot，前端 T_LINK case 的「来源记录」列据此跳图谱构建任务
        extra_snapshot={"jobId": job_id},
        template_id="T_LINK",
        workflow_type="kg.schema.extract",
        exception_code="KG_ENTITY_DISAMBIGUATION_GRAY",
        resume_token=f"extract-resolve:{execution_id}:{vid}",
    )


def _enqueue_pending_review(request: dict[str, Any], pending: list[Any], attempt: int) -> None:
    """把 step 返回的 pendingReview 项写入审核队列（挂实体改道写前消歧）。

    - 实体项（kind=entity）：图库同名召回 + 评分 → **T_LINK** case，强制人工
      裁决（挂起实体的边端点悬在未决 vid 上，自动并入会让边无人改写——见
      _enqueue_entity_pending_item）。平台的两个分岔保持不变：失败重跑 / 进
      消歧；不再产生新 T_DIRECT。
    - 关系项：已废弃（歧义即端点实体歧义，脚本改挂实体后不再产生），丢弃并
      告警。

    入队失败不阻塞 pipeline——记 warning，继续；dedupe_key 保证幂等（重跑时
    create_direct_case 按已存 dedupe_key 跳过）。
    """
    import logging

    log = logging.getLogger("workflow.kg.custom.steps")
    try:
        info = activity.info()
        workflow_id = info.workflow_id
        workflow_run_id = info.workflow_run_id
    except RuntimeError:
        # 单测直调（无 activity 上下文）
        workflow_id = "test-workflow"
        workflow_run_id = None
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(workflow_id) or {}
    except Exception as exc:
        log.warning("lookup execution for workflow %s failed: %s", workflow_id, exc)
        execution = {}
    task_id = execution.get("taskId") or f"PI-kgstep-{workflow_id[:12]}"
    execution_id = execution.get("id")
    space = (request.get("selectors") or {}).get("graph_space") or None
    step_id = str(request.get("stepId") or "extract")
    client = None
    try:
        for item in pending:
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or "entity") != "entity":
                log.warning(
                    "pendingReview 关系项已废弃（歧义改挂实体，走 T_LINK），丢弃: "
                    "step=%s obj=%s reason=%s",
                    step_id,
                    item.get("objectId"),
                    item.get("reason"),
                )
                continue
            try:
                if client is None:
                    client = _pending_graph_client(space)
                _enqueue_entity_pending_item(
                    item,
                    step_id=step_id,
                    client=client,
                    space=space,
                    task_id=task_id,
                    execution_id=execution_id,
                    workflow_id=workflow_id,
                    workflow_run_id=workflow_run_id,
                    job_id=execution.get("jobId"),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "pendingReview 实体项建 T_LINK 失败 step=%s obj=%s reason=%s",
                    step_id,
                    item.get("objectId"),
                    exc,
                )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                log.exception("关闭消歧改道图客户端失败")


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
    # run 专属脚本副本：把本次 run 用的脚本字节钉进 run 级 key（run 期间不可变）。
    # worker 中途崩溃换 worker 接手时，execute_transform 凭 runKey + sha256 重新
    # 物化，版本由校验保证一致；schema 上传新版本删除旧对象也不影响在飞 run。
    try:
        workflow_id = activity.info().workflow_id
    except RuntimeError:
        workflow_id = f"local-{uuid4().hex}"  # 单测直调无 activity 上下文
    run_key = f"runs/{workflow_id}/script.py"
    try:
        storage.put_bytes(run_key, data, "text/x-python")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"创建 run 脚本副本失败: {exc}") from exc
    script_sha256 = hashlib.sha256(data).hexdigest()
    script_path = await asyncio.to_thread(
        _write_private_tempfile,
        prefix=f"kg_schema_extract_{schema_key}_",
        suffix=".py",
        data=data,
    )
    # 多步声明解析：@step 装饰器（推荐）或顶层 STEPS 清单（兼容）→ 多步链；
    # 无声明 → 单步兜底（入口名沿用上传时存的 functionName）。上传时
    # _validate_script 已校验过形状，这里重新解析兜住绕过上传通道的脚本，
    # 非法即失败（workflow 报清晰错误）。
    try:
        declared_steps = extract_declared_steps(
            data.decode("utf-8-sig", errors="replace"), filename=object_key
        )
    except ValueError as exc:
        raise ValueError(f"Schema 脚本多步声明非法: {exc}") from exc
    steps = declared_steps or [{"id": "_default", "fn": function_name}]
    return {
        "schemaId": schema_id,
        "schemaKey": schema_key,
        "kind": kind,
        "name": name,
        "label": label,
        "activeProps": active_props,
        "sources": sources,
        "scriptPath": script_path,
        # run 级脚本副本定位：execute_transform 的 tempfile 丢失时按此重物化
        "scriptRunKey": run_key,
        "scriptSha256": script_sha256,
        "functionName": function_name,
        # steps 只放 id/fn 两个 str 键（plan 要经 Temporal 序列化进事件历史）
        "steps": steps,
        "multiStep": declared_steps is not None,
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
    from sqlalchemy import text

    from infra.mysql import MySQLClient
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

    # 源库连接统一走 MySQLClient（URL 拼装与引擎参数只此一份）
    source_client = MySQLClient(
        host=params["host"],
        port=int(params["port"]),
        database=database,
        username=params["username"],
        password=params["password"],
    )

    # —— S3 中转（claim-check）总开关：全链路唯一一处读 env 做控制流分支的位置 ——
    # 开启时批行按 chunk 归档 S3、activity 结果只带 chunks 元数据；workflow 按
    # 「已记录进历史的结果形状」分支（chunks 在则走中转），下游不受 env 翻转影响，
    # 在飞旧 run 重放安全。关闭时行为与历史版本逐字节一致。
    from service.extract_payload_store import (
        payload_max_bytes,
        payload_s3_enabled,
        put_extract_payload_json,
    )

    s3_relay = payload_s3_enabled()
    # Temporal 单条 activity 结果/输入受 gRPC 4MB 限制：大文本行（专利摘要等）
    # 一批 500 行轻易超限，activity 完成报 ResourceExhausted 无限重试。这里对
    # 游标/offset 模式自适应折半 LIMIT 直到序列化结果 ≤ 预算；未取的尾部行由
    # 下一批重读（游标按实际返回行推进），语义不丢数据。
    # 预算语义随中转切换：中转开 = 单载荷对象预算（默认 8MB，脚本进程内存量级，
    # 大文本行批吞吐恢复）；中转关 = gRPC 传输预算（512KB，历史行为）。
    budget = payload_max_bytes() if s3_relay else _MAX_BATCH_ROWS_BYTES
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

    engine = source_client.engine
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
                if len(json.dumps(rows, ensure_ascii=False, default=str).encode()) <= budget:
                    break
                n = max(1, n // 2)
    finally:
        source_client.dispose()

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
    if s3_relay:
        # 批行归档 S3（worker 的批内切分逻辑下沉到这里），结果只带元数据：
        # 每批行数受折半预算约束 ≤ 载荷预算；ids 模式全量读，按 batchSize/预算
        # 分组上传。key 由 batchIdx + chunk 序确定性派生，activity 重试同 key
        # 覆盖写（幂等）。ids 模式回传各 chunk 的 recordIds（重跑失败合成要用）。
        step_key_id = request.get("stepId") or "source"
        batch_idx = int(request.get("batchIdx") or 0)
        chunks_meta: list[dict[str, Any]] = []
        for position, group in enumerate(_split_rows_for_upload(rows, batch_size, budget)):
            key = await asyncio.to_thread(
                put_extract_payload_json,
                step_key_id,
                batch_idx,
                f"rows-{position:02d}",
                group,
            )
            meta: dict[str, Any] = {"key": key, "rowCount": len(group)}
            if cursor_kind == "ids":
                meta["recordIds"] = [
                    str(r.get(pk_column)) for r in group if r.get(pk_column) is not None
                ]
            chunks_meta.append(meta)
        return {
            "chunks": chunks_meta,
            "totalRows": len(rows),
            "maxTime": max_time,
            "maxPk": max_pk,
            "effectiveBatchSize": effective_batch,
            # offset 模式回传本批生效的增量水位（时间列过滤起点），reader 链式透传
            **({"watermark": binds.get("wm")} if cursor_kind == "offset" else {}),
        }
    return {
        "rows": rows,
        "recordIds": [str(r.get(pk_column)) for r in rows if r.get(pk_column) is not None],
        "maxTime": max_time,
        "maxPk": max_pk,
        "effectiveBatchSize": effective_batch,
        # offset 模式回传本批生效的增量水位（时间列过滤起点），reader 链式透传
        **({"watermark": binds.get("wm")} if cursor_kind == "offset" else {}),
    }


async def _rematerialize_run_script(request: dict[str, Any]) -> str:
    """tempfile 丢失时按 run 级 S3 副本重物化脚本；sha256 校验不过即硬失败。

    版本一致性优先：副本内容与本 run 开始时钉住的 sha256 不匹配（理论上不该
    发生——run key 不可变）或下载失败都直接抛错，交由 Temporal 重试/失败，
    绝不执行不确定版本的脚本。升级窗口内在飞的旧 plan 没有 run 副本字段，
    保持旧的明确失败语义。
    """
    run_key = request.get("scriptRunKey")
    expected = request.get("scriptSha256")
    if not run_key or not expected:
        raise ValueError(f"脚本不存在且无 run 副本可重物化: {request.get('scriptPath')}")
    from infra.s3 import get_schema_s3_storage

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    storage = get_schema_s3_storage()
    body = None
    try:
        body = storage.get_object(storage.bucket, run_key)
        data = body.read()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"下载 run 脚本副本失败: {run_key}: {exc}") from exc
    finally:
        if body is not None:
            try:
                body.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭 run 脚本流失败: %s", run_key)
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError(f"run 脚本副本 sha256 校验失败: {run_key}")
    return await asyncio.to_thread(
        _write_private_tempfile,
        prefix="kg_schema_extract_run_",
        suffix=".py",
        data=data,
    )


@activity.defn
async def execute_transform(request: dict[str, Any]) -> dict[str, Any]:
    """把批次行交给脚本转换：payload["rows"] = 行 JSON，调脚本入口（默认 transform）。

    多步脚本（顶层 STEPS 声明）时每个 step 调一次本 activity（各自独立 Temporal 重试）：
    - 第 1 步与单步 transform 同构（request/payload 均相同）；
    - 第 N>1 步 request 额外带 ``input``（上一步完整输出 dict）与 ``prevOutputs``
      （已完成各步 {stepId: 输出}），payload 换为 ``{"input": ..., "source_table": ...,
      "kind": ..., "source": ...}``（不再带 rows）；ctx.prev_outputs 同步可读；
    - ``ctxStepId``（多步时形如 ``source:{绑定id}#{stepId}``）只进脚本 ctx 与审核
      case 做观测标识；水位键仍是 ``request.stepId``（source:{绑定id}），语义不变。

    载荷 S3 中转（claim-check，双形状并存，脚本契约不变）：
    - 入参兼容 ``rows`` / ``rowsKey``、``input``/``prevOutputs`` / ``inputKey``/``prevKeys``；
      key 形状在 activity 内下载后组装与内联路径逐字节等价的 payload，脚本对 S3 无感；
    - 中转入参（rowsKey 或 inputKey 在）时输出侧同样走 S3：全量输出与整形后的失败
      清单归档，返回元数据（outKey + 计数 + stats + access）；内联路径返回原样
      （额外键超预算截断，见 _truncate_step_extras）。

    脚本只做转换，返回 ``{"entities": [{id, props}]}`` / ``{"edges": [{fromId, toId, props}]}``；
    可选 ``failures: [{recordId, error}]``（逐行解析失败 → 平台记 T_EXTRACT_FAIL 审核重跑）
    与 ``pendingReview: [...]``（低置信/消歧候选 → 审核队列，item 可带 templateId=T_LINK）。
    返回值里的额外键原样透传给下一步（超预算截断为标记，见 _truncate_step_extras）。
    ctx 注入触发时选择的 mysql/graph/llm/embedding（未显式选 mysql 时回退来源绑定数据源，
    脚本内 resolver 可用 ``current_context().mysql.engine`` 加载查找表）。
    脚本的 ``_watermark``/``_checkpoint`` 元字段被忽略（水位由平台管理）。
    """
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        # worker 崩溃/容器重建导致本地 tempfile 丢失：按 run 副本重物化
        # （sha256 钉版本，换 worker 接手也拿到同一份字节）
        script_path = Path(await _rematerialize_run_script(request))
    function_name = request.get("functionName", "transform")
    source = request.get("source") or {}
    kind = request.get("kind", "entity")
    rows_key = request.get("rowsKey")
    input_key = request.get("inputKey")
    from service.extract_payload_store import load_extract_payload_json

    if rows_key:
        # 中转：批行从 S3 下载（脚本看到的 payload dict 形状与内联路径逐字节等价）
        rows = await asyncio.to_thread(load_extract_payload_json, rows_key)
    else:
        rows = request.get("rows") or []
    payload = {
        "rows": rows,
        "source_table": f"{source.get('databaseName')}.{source.get('tableName')}",
        "kind": kind,
        "source": source,
    }
    if "input" in request or input_key:
        # 第 N>1 步：消费上一步完整输出（额外键/entities 等原样在内），不带 rows；
        # 中转形状从 S3 下载，无截断（「拿到什么 = 上一步返回什么」）
        input_value = request.get("input")
        if input_key:
            input_value = await asyncio.to_thread(load_extract_payload_json, input_key)
        payload = {
            "input": input_value or {},
            "source_table": payload["source_table"],
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
    # ctx 观测标识：多步用「来源#步」复合 id；水位读取键保持 request.stepId 不变
    resolved["stepId"] = request.get("ctxStepId") or request.get("stepId") or "_default"
    try:
        resolved["attempt"] = activity.info().attempt
    except RuntimeError:
        # 单测直调（无 activity 上下文）时给占位 attempt；真实运行恒有上下文
        resolved["attempt"] = 1
    if request.get("prevOutputs") is not None:
        resolved["prevOutputs"] = request["prevOutputs"]
    elif request.get("prevKeys"):
        # 中转：已完成各步输出按 key 下载（ctx.prev_outputs 与内联路径同构）
        resolved["prevOutputs"] = {
            sid: await asyncio.to_thread(load_extract_payload_json, key)
            for sid, key in (request.get("prevKeys") or {}).items()
        }
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
        # 忽略脚本的 _watermark/_checkpoint（平台按批次游标管理水位）
        output = _strip_watermark_meta(output)
        pending = output.pop("pendingReview", []) if isinstance(output, dict) else []
        if pending:
            _enqueue_pending_review(
                {
                    **request,
                    "stepId": request.get("ctxStepId") or request.get("stepId") or "extract",
                },
                pending,
                1,
            )
        if rows_key or input_key:
            # 中转：全量输出/失败清单归档 S3，返回元数据（access 保持内联）
            return await _transform_result_via_s3(request, output, access)
        if access is not None and isinstance(output, dict):
            output = {**output, "access": access}
        return _truncate_step_extras(output) if isinstance(output, dict) else {}
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
    records = request.get("records")
    if records is None and request.get("recordsKey"):
        # S3 中转：全量输出对象（dict）取 entities/edges；消歧产物（list）直用
        records = await _load_records_from_key(request["recordsKey"])
    records = records or []
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
            described = client.execute_read(
                f"DESCRIBE {'TAG' if kind == 'entity' else 'EDGE'} `{name}`"
            )
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
        if kind == "relation" and records:
            # 关系写图前端点消歧（跨执行兜底）：端点命中未决 T_LINK case 的边
            # 暂存进 case 快照（裁决时补写，不产生悬挂点）；已裁决 merge 的端点
            # 改写为目标实体；端点实体被驳回的边丢弃。查询失败按原样写，不阻塞批次
            from service.manual_review_production import manual_review_service

            try:
                parked = manual_review_service.park_or_rewrite_edges(name, records)
                records = parked.get("records") or []
                if parked.get("parked"):
                    logger.info(
                        "关系端点待消歧，暂存 %s 条（随 T_LINK 裁决补写）", parked["parked"]
                    )
                if parked.get("dropped"):
                    logger.info("关系端点实体已被驳回，丢弃 %s 条", parked["dropped"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("关系端点消歧查询失败，按原样写图: %s", exc)
        for record in records:
            props = filtered(record.get("props"))
            if kind == "entity" and not props:
                continue
            if (
                kind == "entity"
                and (not active_props or "id" in active_props)
                and not str(props.get("id") or "").strip()
            ):
                # 身份列 id 平台兜底：vid 即记录 id，脚本未显式输出（或输出空串）时
                # 补齐——id 是 Schema 注入的 NOT NULL 身份列，落空串会让身份失去意义。
                # 仅在 id 属于白名单时注入，避免给未声明 id 列的 Schema 加未知列。
                props["id"] = str(record["id"])
            write_with_self_heal(record, props)
            written += 1
        return {"written": written}
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            logger.exception("关闭图客户端失败")


@activity.defn
async def resolve_entity_batch(request: dict[str, Any]) -> dict[str, Any]:
    """消歧 v2（写前判定）：转换产出的实体在写图前先做同名召回 + 多证据评分。

    三分支：得分 ≥0.85 且分差足够 → 改写 vid 并入已有实体（后续 INSERT VERTEX
    幂等 upsert，"合并"=属性覆盖到目标节点）；灰区 [0.65, 0.85) → 扣留该记录
    并创建 T_LINK case（候选+得分+待定关系随快照走，case 即待写队列）；<0.65 →
    新实体原样写。返回过滤后的 records 供 write_records 继续使用；建案失败时
    fail-open（记录照写，行为退回消歧 v1），不丢数据。阈值见
    service/entity_disambiguation.py（v1 初值，待人工复核样本校准）。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from service.entity_disambiguation import (
        GRAY_LOW,
        MERGE_THRESHOLD,
        TOP_K,
        decide,
        display_name,
        normalize_display_name,
        recall_same_name,
        score_candidate,
    )

    name_tag = request["name"]
    records_in = request.get("records")
    if records_in is None and request.get("recordsKey"):
        # S3 中转：同 write_records 的提取语义（dict 全量输出 → entities/edges）
        records_in = await _load_records_from_key(request["recordsKey"])
    records = [dict(r) for r in (records_in or [])]
    graph = request.get("graph") or {}
    source_table = str(request.get("sourceTable") or "")
    batch_vids = {str(r.get("id")) for r in records}

    # 1) 批内同名去重：同显示名的后到记录改写为先到记录的 vid（同批 upsert 合并）
    first_by_name: dict[str, str] = {}
    deduped = 0
    for record in records:
        key = normalize_display_name(display_name(record.get("props")))
        if not key:
            continue
        first_vid = first_by_name.setdefault(key, str(record.get("id")))
        if first_vid != str(record.get("id")):
            record["id"] = first_vid
            deduped += 1

    # 2) 图库同名召回（带候选完整属性供评分；properties() 失败降级为仅名称）
    by_name: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        display = display_name(record.get("props"))
        if display:
            by_name.setdefault(display, []).append(record)

    existing: dict[str, list[dict[str, Any]]] = {}
    if by_name:
        settings = TRSGraphSettings.from_env()
        if graph.get("space"):
            settings.space = graph["space"]
        client = TRSGraphClient(settings)
        try:
            client.connect()
            existing = recall_same_name(client, name_tag, list(by_name))
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭图客户端失败")

    info = _activity_info_safe()
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(info.workflow_id) or {}
    except Exception:  # noqa: BLE001
        execution = {}
    task_id = execution.get("taskId") or f"PI-extract-{info.workflow_id[:12]}"
    execution_id = execution.get("id")

    from service.manual_review_production import manual_review_service

    kept: list[dict[str, Any]] = []
    stats = {"merged": 0, "withheld": 0, "deduped": deduped, "new": 0}
    for record in records:
        display = display_name(record.get("props"))
        scored = []
        for cand in existing.get(display, []):
            if cand["vid"] in batch_vids:
                continue
            score, detail = score_candidate(
                display, record.get("props"), cand["name"], cand.get("props")
            )
            scored.append(
                {"vid": cand["vid"], "name": cand["name"], "score": round(score, 3), **detail}
            )
        outcome = decide(scored)
        if outcome["decision"] == "merge":
            record["id"] = outcome["targetVid"]
            stats["merged"] += 1
            kept.append(record)
        elif outcome["decision"] == "gray":
            try:
                manual_review_service.create_direct_case(
                    task_id=task_id,
                    execution_id=execution_id,
                    step_id=request.get("stepId") or "align",
                    kind="entity",
                    candidate={
                        "name": display,
                        "newIds": [str(record.get("id"))],
                        "existingCandidates": [
                            {"vid": c["vid"], "name": c["name"], "score": c["score"]}
                            for c in sorted(scored, key=lambda x: x["score"], reverse=True)[:TOP_K]
                        ],
                        "_incoming": {
                            "vid": str(record.get("id")),
                            "props": record.get("props") or {},
                            "sourceTable": source_table,
                        },
                        "_pendingRelations": [],
                        "_graphSpace": graph.get("space"),
                        "_resolution": {
                            "matchScore": outcome["score"],
                            "margin": outcome["margin"],
                            "policyVersion": "disambiguation-gray-v1",
                            "thresholds": {"merge": MERGE_THRESHOLD, "grayLow": GRAY_LOW},
                        },
                    },
                    object_id=str(record.get("id")),
                    object_name=display,
                    node_label=name_tag,
                    reason=(
                        f"消歧得分 {outcome['score']:.2f} 落入灰区 "
                        f"[{GRAY_LOW}, {MERGE_THRESHOLD})，需人工裁决是否并入已有实体"
                    ),
                    confidence=outcome["score"],
                    workflow_id=info.workflow_id,
                    workflow_run_id=info.workflow_run_id,
                    template_id="T_LINK",
                    workflow_type="kg.schema.extract",
                    exception_code="KG_ENTITY_DISAMBIGUATION_GRAY",
                    resume_token=f"extract-resolve:{execution_id}:{record.get('id')}",
                    source_table=source_table or None,
                    source_record_id=str(record.get("id")),
                    extra_snapshot={"jobId": execution.get("jobId")},
                )
                stats["withheld"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("灰区消歧建案失败 vid=%s，记录按原样写图: %s", record.get("id"), exc)
                kept.append(record)
        else:
            stats["new"] += 1
            kept.append(record)
    if request.get("recordsKey"):
        # S3 中转：消歧改写后的 records 重新归档，写图/冲突检测拿 key（历史不进本体）
        from service.extract_payload_store import put_extract_payload_json

        out_key = await asyncio.to_thread(
            put_extract_payload_json,
            request.get("stepId") or "align",
            int(request.get("batchIdx") or 0),
            f"resolved-{int(request.get('chunkIdx') or 0):02d}",
            kept,
        )
        return {"outKey": out_key, "keptCount": len(kept), **stats}
    return {"records": kept, **stats}


@activity.defn
async def detect_extract_collisions(request: dict[str, Any]) -> dict[str, Any]:
    """消歧 v1——同名冲突检测：对本批写入实体按显示名（props.name）查图库同名节点。

    同名不同 vid（含批内互相重名）→ T_LINK「实体对齐裁决」case，人工决定 merge；
    不阻塞写图。入队失败仅告警。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    name_tag = request["name"]
    records = request.get("records")
    if records is None and request.get("recordsKey"):
        # S3 中转：消歧产物（list）或全量输出对象（dict）提取
        records = await _load_records_from_key(request["recordsKey"])
    records = records or []
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
        # 名称列必须 tag 限定（同 recall_same_name 的口径）：空间里多个 tag 都有
        # name 属性时（Person/Organization…），未限定的 v.name 被引擎解析成 NULL，
        # WHERE 静默不命中——同名碰撞永远查空，碰撞 case 建不出来。
        ngql = (
            f"MATCH (v:`{name_tag}`) WHERE v.`{name_tag}`.`name` IN [{name_list}] "
            f"RETURN id(v) AS vid, v.`{name_tag}`.`name` AS nm LIMIT 200"
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

    info = _activity_info_safe()
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
                extra_snapshot={"jobId": execution.get("jobId")},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("同名冲突 case 创建失败 name=%s: %s", display, exc)
    return {"collisions": collisions}


@activity.defn
async def record_extract_failures(request: dict[str, Any]) -> dict[str, Any]:
    """把逐行抽取失败落成 T_EXTRACT_FAIL 审核case（前端人工审核页展示、点击重跑）。

    失败条目双来源：``failures``（内联清单，旧路径/重跑合成）+ ``failureRefs``
    （S3 中转的 failuresKey 引用，activity 内下载展开）；``cap``>0 时截前 cap 条
    建 case（「超 cap 不建 case 但 count 如实」语义与原 workflow 侧截断一致）。
    """
    info = _activity_info_safe()
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
    # jobId 优先取 workflow 入参，兜底执行记录（来源记录跳任务详情）
    job_id = request.get("jobId") or execution.get("jobId")

    from service.manual_review_production import manual_review_service

    items = await _expand_failure_items(request)
    cap = int(request.get("cap") or 0)
    if cap > 0 and len(items) > cap:
        items = items[:cap]
    recorded = 0
    for item in items:
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
    """重跑执行结束后回写 T_EXTRACT_FAIL case：成功→RESOLVED；仍失败→新 case（attempt+1）。

    失败条目双来源（同 record_extract_failures）：内联 + failureRefs 下载展开；
    重跑语义拿全量失败键（无 cap 截断）。
    """
    info = _activity_info_safe()
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(info.workflow_id) or {}
    except Exception:  # noqa: BLE001
        execution = {}
    task_id = execution.get("taskId") or f"PI-extract-{info.workflow_id[:12]}"

    from service.manual_review_production import manual_review_service

    failed_records = await _expand_failure_items(request)
    result = manual_review_service.resolve_extract_rerun(
        rerun_case_ids=request.get("rerunCaseIds") or [],
        failed_records=failed_records,
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
    """declarative 定义的记账工作流：按定义 steps 逐步回显 payload（占位语义，C1 范畴）。

    D3 删掉 execute_kg_step 空壳 activity 后改为 workflow 内直接构造记账结果——
    真实数据处理一律走 kg.schema.extract。
    """

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        await _register_scheduled_run(request)
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        payload = request.get("payload", {})
        results = [
            {
                "step": step if isinstance(step, str) else step.get("id") or step.get("name"),
                "kind": "custom",
                "domain": definition["id"],
                "status": "completed",
                "input": payload,
                "output": payload,
            }
            for step in definition.get("steps", [])
        ]
        return {"definitionId": definition["id"], "status": "completed", "steps": results}


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
    - 脚本可在顶层声明 ``STEPS`` 清单做多步转换（单 ``transform`` = 单步特例）：
      批内步序串行，每步一次 ``execute_transform`` activity（第 k 步失败由 Temporal
      只重试第 k 步）；第 N>1 步 payload 为 ``{"input": 上一步输出, ...}``，
      ``ctx.prev_outputs`` 可读已完成各步输出；任意一步出 entities/edges 即在该步后
      写图，failures 跨步聚合。水位仍是来源级整链推进，不做 per-step 水位。
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
        self._run_script_object: str | None = None
        # chain（多 Schema 串行，kg.schema.extract.chain）进度：schema:{id} →
        # 外层阶段状态；get_steps 查询实时返回（旧 kg.custom.chain 同契约）
        self._chain_steps: dict[str, dict[str, Any]] = {}
        self._current_schema: str | None = None

    async def _report_script_run(self, schema_id: str, *, ok: bool, error: str | None) -> None:
        """收尾回写脚本健康信号（best-effort，失败不影响主流程状态）。"""
        try:
            await workflow.execute_activity(
                record_schema_script_run,
                {
                    "schemaId": schema_id,
                    "status": "ok" if ok else "failed",
                    "error": error,
                    # 顺带清理 run 脚本副本（activity 内 best-effort 删除）
                    "runScriptKey": self._run_script_object,
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
        except ActivityError:
            workflow.logger.warning("回写脚本运行状态失败: %s", schema_id)

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        schema_ids = request.get("schemaIds") or []
        if len(schema_ids) >= 2:
            # chain 模式（kg.schema.extract.chain）：多 Schema 严格串行。
            # 失败记录重跑只支持单 Schema（rerun_failed_records 按单 Schema 建执行）。
            if request.get("recordIdsBySource"):
                raise ApplicationError("多脚本串行任务不支持失败记录重跑（重跑请单 Schema 执行）")
            return await self._run_chain(request, schema_ids)
        schema_id = request.get("schemaId") or (schema_ids[0] if schema_ids else None)
        if not schema_id:
            raise ApplicationError("缺少 schemaId")
        return await self._run_single(request, schema_id)

    async def _run_single(
        self, request: dict[str, Any], schema_id: str, *, force_step_totals: bool = False
    ) -> dict[str, Any]:
        """单 Schema 抽取：包装逻辑与历史 run() 逐字段一致（事件序列不变，重放安全）。"""
        try:
            result = await self._extract_schema(
                request, schema_id, force_step_totals=force_step_totals
            )
        except Exception as exc:
            await self._report_script_run(schema_id, ok=False, error=str(exc)[:1000])
            raise
        await self._report_script_run(schema_id, ok=True, error=None)
        return result

    async def _run_chain(self, request: dict[str, Any], schema_ids: list[str]) -> dict[str, Any]:
        """多 Schema 严格串行：任一环失败即置 FAILED 并中止（恢复走 reset 回放）。"""
        failures_total = {"count": 0, "recorded": 0, "truncated": False}
        for pos, schema_id in enumerate(schema_ids):
            step_key = f"schema:{schema_id}"
            self._current_schema = schema_id
            self._chain_steps[step_key] = {
                "status": "RUNNING",
                "schemaId": schema_id,
                "position": pos + 1,
            }
            try:
                result = await self._run_single(request, schema_id, force_step_totals=True)
            except Exception as exc:
                self._chain_steps[step_key] = {
                    **self._chain_steps[step_key],
                    "status": "FAILED",
                    "error": str(exc)[:500],
                }
                raise
            sources = result.get("sources") or []
            # 内层 activities = 该脚本各转换步聚合（单 transform 脚本聚合为 1 条）
            activities: dict[str, dict[str, Any]] = {}
            for sid, stat in (result.get("steps") or {}).items():
                activities[sid] = {
                    "status": stat.get("status", "COMPLETED"),
                    "name": (result.get("functionName") or sid) if sid == "_default" else sid,
                    "records": int(stat.get("records", 0)),
                    "written": int(stat.get("written", 0)),
                    "failed": int(stat.get("failed", 0)),
                }
            fail = result.get("failures") or {}
            failures_total["count"] += int(fail.get("count", 0))
            failures_total["recorded"] += int(fail.get("recorded", 0))
            failures_total["truncated"] = failures_total["truncated"] or bool(fail.get("truncated"))
            self._chain_steps[step_key] = {
                **self._chain_steps[step_key],
                "status": "COMPLETED",
                "name": result.get("schemaLabel") or result.get("schemaKey") or schema_id,
                "kind": result.get("kind"),
                "description": (
                    f"kg.schema.extract · {result.get('kind', 'entity')} 抽取"
                    f"（{len(sources)} 个来源）"
                ),
                "records": sum(int(s.get("rows", 0)) for s in sources),
                "written": sum(int(s.get("written", 0)) for s in sources),
                "failed": int(fail.get("count", 0)),
                "output": result,
                "activities": activities,
            }
        return {
            "status": "completed",
            "chain": True,
            "definitionId": request.get("chainDefinitionId"),
            "schemaIds": schema_ids,
            "triggerSource": request.get("triggerSource", "MANUAL"),
            "steps": self._chain_steps,
            "failures": failures_total,
        }

    async def _extract_schema(
        self,
        request: dict[str, Any],
        schema_id: str,
        *,
        force_step_totals: bool = False,
    ) -> dict[str, Any]:
        # chain 串行的下一环运行前重置来源级进度，防跨 Schema 串台
        self._sources = {}
        self._slots = {}
        self._current_source = None
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
        # 步清单：STEPS 声明脚本为多步链（批内步序串行，每步一次 execute_transform
        # 独立重试）；单 transform 脚本及升级窗口内在飞重放的旧 plan（无 steps 键）
        # 都兜底单步，行为与历史版本逐字段一致
        steps: list[dict[str, str]] = plan.get("steps") or [
            {"id": "_default", "fn": plan["functionName"]}
        ]
        multi_step = bool(plan.get("multiStep"))
        self._run_script_object = plan.get("scriptRunKey")
        # 分步聚合计数开关：多步脚本原生开启；chain 模式（force_step_totals）下单
        # transform 脚本也聚合为 1 条（key=_default），保证详情页每个 Schema 抽屉有内容
        track_steps = multi_step or force_step_totals

        # 周期 Schedule 触发：request 是扁平 shape（非 {definitionId, payload}），
        # 直接调注册 activity 落 execution/task 行（幂等）。chain 模式下控制面
        # execution/task 行挂在 chain 定义上（chainDefinitionId）；水位读写键不变。
        schedule_id = request.get("_scheduleId")
        if schedule_id:
            info = workflow.info()
            await workflow.execute_activity(
                register_scheduled_execution,
                {
                    "definitionId": request.get("chainDefinitionId") or definition_id,
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
                        {**read_base, "batchIdx": idx, **cursor},
                        start_to_close_timeout=timedelta(seconds=600),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                    )
                    # 批结果双形状：S3 中转（chunks 元数据 + totalRows）或内联 rows
                    # （在飞旧 run 重放 / 未开 flag）。分支只看已记录进历史的形状。
                    if "chunks" in batch:
                        total_rows = int(batch.get("totalRows") or 0)
                    else:
                        total_rows = len(batch.get("rows") or [])
                    if not total_rows:
                        break
                    await queue.put((idx, batch))
                    idx += 1
                    if batch.get("maxTime") and (final_wm is None or batch["maxTime"] > final_wm):
                        final_wm = batch["maxTime"]
                    if plain_table:
                        # 普通表 offset 分页（主键不保证唯一）；增量水位链式透传
                        offset += total_rows
                        cursor = {"offset": offset, "chained": True}
                        if batch.get("watermark") is not None:
                            cursor["watermark"] = batch["watermark"]
                    else:
                        final = {"watermark": batch.get("maxTime"), "pkCursor": batch.get("maxPk")}
                        # 游标列全 NULL 时无法增量分页，读完一批即止（防死循环）
                        if final["watermark"] is None and final["pkCursor"] is None:
                            break
                        cursor = {k: v for k, v in final.items() if v is not None}
                    # 大文本行时 activity 会折半 LIMIT（中转开 = 载荷预算 8MB，
                    # 关 = gRPC 预算 512KB）：终止判断用本批实际请求量，防早停丢尾批
                    effective = int(batch.get("effectiveBatchSize") or batch_size)
                    if total_rows < effective:
                        break
                if plain_table:
                    return {"batches": idx, "watermark": final_wm, "pkCursor": None}
                return {"batches": idx, **final}

            # 分步聚合计数（多步脚本或 chain 模式；stepId → records/written/failed）
            step_totals: dict[str, dict[str, int]] = (
                {s["id"]: {"records": 0, "written": 0, "failed": 0} for s in steps}
                if track_steps
                else {}
            )

            async def worker() -> list[dict[str, Any]]:
                failures: list[dict[str, Any]] = []
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    idx, batch = item
                    # 批内 chunk 统一化：S3 中转形状遍历 chunks 元数据（行数据在 S3），
                    # 内联形状按 batch_size 切 rows（与历史行为一致，重放安全）
                    for chunk in _iter_batch_chunks(batch, batch_size, pk_column):
                        written = 0
                        chunk_step_stats: dict[str, dict[str, int]] = {}
                        batch_failures: list[dict[str, Any]] = []
                        try:
                            # 步链串行执行（批间并行度仍由 max_inflight 的队列背压管）：
                            # 每步一次 execute_transform，带各自的 functionName/payload，
                            # 第 k 步失败由 Temporal 只重试第 k 步（前序步输出在事件
                            # 历史里重放）。任意一步出了 entities/edges 就在该步之后
                            # 写图（实体再接消歧）；failures 跨步聚合。
                            prev_output: dict[str, Any] = {}
                            step_outputs: dict[str, Any] = {}
                            for seq, step in enumerate(steps):
                                step_ctx_id = f"{step_id}#{step['id']}" if multi_step else step_id
                                transform_request: dict[str, Any] = {
                                    "scriptPath": plan["scriptPath"],
                                    # run 副本定位（.get 兼容升级窗口内在飞旧 plan 的重放）
                                    "scriptRunKey": plan.get("scriptRunKey"),
                                    "scriptSha256": plan.get("scriptSha256"),
                                    "functionName": step["fn"],
                                    "source": source,
                                    "kind": kind,
                                    "timeoutSeconds": timeout_seconds,
                                    "selectors": selectors,
                                    "definitionId": definition_id,
                                    # 水位读取键（kg_script_watermark）保持来源级，不随步变
                                    "stepId": step_id,
                                    # 载荷 key 的确定性派生字段（batch/chunk 序，内联路径多带无害）
                                    "batchIdx": idx,
                                    "chunkIdx": chunk["index"],
                                }
                                if multi_step:
                                    transform_request["ctxStepId"] = step_ctx_id
                                if seq:
                                    if "outKey" in prev_output:
                                        # S3 中转：input/prevOutputs 以 key 传递（无截断，
                                        # 「拿到什么 = 上一步返回什么」），activity 内下载
                                        transform_request["inputKey"] = prev_output["outKey"]
                                        transform_request["prevKeys"] = {
                                            sid: out["outKey"]
                                            for sid, out in step_outputs.items()
                                            if "outKey" in out
                                        }
                                    else:
                                        # 第 N>1 步（内联路径，在飞旧 run 重放兼容）：
                                        # 不带 rows（省一半请求体积），input=上一步完整输出、
                                        # prevOutputs=已完成各步输出；超预算截断为标记
                                        # （防 gRPC 上限炸批次）
                                        transform_request["input"] = _shrink_chain_value(
                                            prev_output,
                                            budget=_MAX_STEP_CHAIN_BYTES,
                                            label=f"步 {step['id']} 的 input",
                                        )
                                        transform_request["prevOutputs"] = {
                                            sid: _shrink_chain_value(
                                                out,
                                                budget=_MAX_PREV_OUTPUT_BYTES,
                                                label=f"prevOutputs[{sid}]",
                                            )
                                            for sid, out in step_outputs.items()
                                        }
                                elif "rowsKey" in chunk:
                                    # 第 1 步（S3 中转）：批行以 key 传递
                                    transform_request["rowsKey"] = chunk["rowsKey"]
                                else:
                                    # 第 1 步：与单步 transform 请求形状一致
                                    transform_request["rows"] = chunk["rows"]
                                transformed = await workflow.execute_activity(
                                    execute_transform,
                                    transform_request,
                                    start_to_close_timeout=timedelta(seconds=timeout_seconds + 60),
                                    retry_policy=ACTIVITY_RETRY_POLICY,
                                )
                                # 转换结果双形状：S3 中转（outKey 元数据）或内联（重放兼容）。
                                # records_arg 随形状携带：中转传 recordsKey（全量输出对象，
                                # 消歧/写图/冲突检测 activity 内提取），内联传 records 本体。
                                step_fail_count = 0
                                if "outKey" in transformed:
                                    records_count = int(transformed.get("entityCount") or 0) + int(
                                        transformed.get("edgeCount") or 0
                                    )
                                    records_arg = {"recordsKey": transformed["outKey"]}
                                    step_fail_count = int(transformed.get("failureCount") or 0)
                                    if transformed.get("failuresKey"):
                                        # 失败清单在 S3：历史只过 key + 计数（终态建 case
                                        # 时由 activity 下载展开）
                                        batch_failures.append(
                                            {
                                                "failuresKey": transformed["failuresKey"],
                                                "count": step_fail_count,
                                            }
                                        )
                                else:
                                    records = (
                                        transformed.get("entities")
                                        or transformed.get("edges")
                                        or []
                                    )
                                    records_count = len(records)
                                    records_arg = {"records": records}
                                    step_failures = _shape_step_failures(
                                        transformed.get("failures"),
                                        source_binding_id=source_id,
                                        table_label=table_label,
                                    )
                                    step_fail_count = len(step_failures)
                                    batch_failures.extend(step_failures)
                                step_written = 0
                                if records_count and kind == "entity":
                                    # 消歧 v2（写前判定）：同名召回+评分，改写 vid 并入 /
                                    # 灰区扣留建 T_LINK case / 其余原样——灰区记录从本批
                                    # 剔除（不写图），后续由人工裁决执行器补写
                                    resolved = await workflow.execute_activity(
                                        resolve_entity_batch,
                                        {
                                            "name": plan["name"],
                                            "graph": graph,
                                            "schemaKey": plan["schemaKey"],
                                            "stepId": step_ctx_id,
                                            "sourceTable": table_label,
                                            "batchIdx": idx,
                                            "chunkIdx": chunk["index"],
                                            **records_arg,
                                        },
                                        start_to_close_timeout=timedelta(seconds=300),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                    )
                                    if "outKey" in resolved:
                                        records_count = int(resolved.get("keptCount") or 0)
                                        records_arg = {"recordsKey": resolved["outKey"]}
                                    else:
                                        records_count = len(resolved.get("records") or [])
                                        records_arg = {"records": resolved.get("records") or []}
                                if records_count:
                                    write_result = await workflow.execute_activity(
                                        write_records,
                                        {
                                            "kind": kind,
                                            "name": plan["name"],
                                            "activeProps": plan["activeProps"],
                                            "graph": graph,
                                            "sourceTable": table_label,
                                            **records_arg,
                                        },
                                        start_to_close_timeout=timedelta(seconds=600),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                    )
                                    step_written = int(write_result.get("written", 0))
                                if kind == "entity" and records_count and detect_collisions:
                                    await workflow.execute_activity(
                                        detect_extract_collisions,
                                        {
                                            "name": plan["name"],
                                            "graph": graph,
                                            "schemaKey": plan["schemaKey"],
                                            "stepId": step_ctx_id,
                                            **records_arg,
                                        },
                                        start_to_close_timeout=timedelta(seconds=120),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                    )
                                written += step_written
                                if track_steps:
                                    chunk_step_stats[step["id"]] = {
                                        "records": records_count,
                                        "written": step_written,
                                        "failed": step_fail_count,
                                    }
                                # access 溯源报告是平台观测数据，不进步间链
                                chained = {k: v for k, v in transformed.items() if k != "access"}
                                prev_output = chained
                                step_outputs[step["id"]] = chained
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
                                for rid in chunk["recordIds"]
                            ]
                        failures.extend(batch_failures)
                        prev = slots.get(idx) or {"rows": 0, "written": 0, "failed": 0}
                        slots[idx] = {
                            "rows": prev["rows"] + chunk["rowCount"],
                            "written": prev["written"] + written,
                            "failed": prev["failed"] + _failure_entries_count(batch_failures),
                        }
                        if track_steps:
                            # 分步计数聚合进来源级 step_totals（get_progress/结果摘要用）
                            for sid, stat in chunk_step_stats.items():
                                total = step_totals.setdefault(
                                    sid, {"records": 0, "written": 0, "failed": 0}
                                )
                                for key in total:
                                    total[key] += int(stat.get(key, 0))
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
            source_failed = _failure_entries_count(source_failures)

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
                "failed": source_failed,
                # 分步聚合计数（多步脚本/chain 模式；单步单跑摘要形状保持不变）
                **({"steps": step_totals} if track_steps else {}),
            }
            return {
                "source": step_id,
                "table": table_label,
                "batches": read_summary.get("batches", 0),
                "rows": total_rows,
                "written": total_written,
                "failed": source_failed,
                "failures": source_failures,
                "watermark": read_summary.get("watermark"),
                "pkCursor": read_summary.get("pkCursor"),
                **({"steps": step_totals} if track_steps else {}),
            }

        results = await asyncio.gather(*(extract_source(source) for source in plan["sources"]))
        all_failures = [f for r in results for f in (r.get("failures") or [])]
        # 失败聚合双形状：S3 中转的清单以 failuresKey 引用（历史只过 key + 计数），
        # 内联条目（旧路径 / 重跑合成）原样；终态建 case 的 activity 内下载展开
        failure_refs = [f for f in all_failures if "failuresKey" in f]
        inline_failures = [f for f in all_failures if "failuresKey" not in f]
        failures_total = _failure_entries_count(failure_refs) + len(inline_failures)
        truncated = failures_total > failure_cap
        recorded_count = 0
        index_summary: Any = None
        if rerun_mode:
            # 重跑：resolve 必调且拿全量失败键（未截断），仍失败记录由服务端重建 case
            await workflow.execute_activity(
                resolve_failure_cases,
                {
                    "rerunCaseIds": rerun_case_ids,
                    "rerunOfExecutionId": request.get("rerunOfExecutionId"),
                    "failures": inline_failures,
                    "failureRefs": failure_refs,
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
            if failures_total:
                fail_resp = await workflow.execute_activity(
                    record_extract_failures,
                    {
                        "failures": inline_failures,
                        "failureRefs": failure_refs,
                        "cap": failure_cap,
                        "schemaId": schema_id,
                        "schemaKey": plan["schemaKey"],
                        "kind": kind,
                        "name": plan["name"],
                        "jobId": request.get("jobId"),
                    },
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                )
                recorded_count = int((fail_resp or {}).get("recorded") or 0)

        # 多步脚本（及 chain 模式）的全局分步聚合计数（跨来源求和）。status 供任务
        # 详情 pipeline_steps 把每步渲染成「成功」；单步单跑不加该键，形状与历史一致。
        aggregated_steps: dict[str, dict[str, int]] = {}
        if track_steps:
            for r in results:
                for sid, stat in (r.get("steps") or {}).items():
                    agg = aggregated_steps.setdefault(
                        sid, {"records": 0, "written": 0, "failed": 0}
                    )
                    for key in agg:
                        agg[key] += int(stat.get(key, 0))

        return {
            "status": "completed",
            "schemaId": schema_id,
            "schemaKey": plan["schemaKey"],
            "kind": kind,
            "triggerSource": request.get("triggerSource", "MANUAL"),
            "sources": [{k: v for k, v in r.items() if k != "failures"} for r in results],
            **(
                {
                    "steps": {
                        sid: {**stat, "status": "COMPLETED"}
                        for sid, stat in aggregated_steps.items()
                    },
                    # chain 外层阶段命名（label 优先）与单 transform 步命名（函数名）
                    "schemaLabel": plan.get("label") or plan["name"],
                    "functionName": plan["functionName"],
                }
                if track_steps
                else {}
            ),
            "failures": {
                "count": failures_total,
                "recorded": recorded_count,
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
    def get_steps(self) -> dict[str, Any]:
        """chain 模式实时分步状态（旧 kg.custom.chain get_steps 同契约，前端直读）。"""
        return {"current": self._current_schema, "steps": self._chain_steps}

    @workflow.query
    def get_progress(self) -> dict[str, Any]:
        return {
            "chain": bool(self._chain_steps),
            "schema": self._current_schema,
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
        # 回写收尾时间：uploaded_at > last_run_at 即"脚本已更新待重跑"提示的消除条件
        row.last_run_at = datetime.now()
        session.commit()
    run_key = request.get("runScriptKey")
    if run_key:
        # run 脚本副本随 run 结束清理（best-effort：删除失败只记日志，孤儿对象
        # 无副作用；S3 delete 对不存在 key 幂等，activity 重试安全）
        try:
            from infra.s3 import get_schema_s3_storage

            load_dotenv(Path(__file__).resolve().parents[1] / ".env")
            storage = get_schema_s3_storage()
            storage.delete_object(storage.bucket, run_key)
        except Exception:  # noqa: BLE001
            logger.exception("清理 run 脚本副本失败: %s", run_key)
    return {"ok": True, "status": status}


@workflow.defn(name="kg.schema.extract.chain")
class SchemaExtractChainWorkflow(SchemaExtractWorkflow):
    """多脚本串行链：复用 SchemaExtractWorkflow 全部逻辑，payload.schemaIds ≥2 时串行逐 Schema 抽取。

    temporalio 要求 defn 子类显式重写 run；分发在基类 run 顶端完成，行为全部继承。
    详情页按 workflowType 区分 chain 渲染（每 Schema 一个抽屉，内层为脚本 STEPS 步）。
    """

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await super().run(request)


WORKFLOW_CLASSES = [
    ConfigurableWorkflow,
    SchemaExtractWorkflow,
    SchemaExtractChainWorkflow,
]

ACTIVITIES = [
    load_workflow_definition,
    register_scheduled_execution,
    load_schema_extract_plan,
    read_source_batch,
    execute_transform,
    write_records,
    resolve_entity_batch,
    advance_schema_extract_watermark,
    record_schema_script_run,
    detect_extract_collisions,
    record_extract_failures,
    resolve_failure_cases,
    build_entity_index,
]
