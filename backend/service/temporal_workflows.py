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
import time
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

from service.gray_gate import (
    NAME_RULE_VERSION,
    GrayGateFailClosedError,
    compute_event_version,
    prior_verdict_disposition,
    require_known_policy,
)
from service.gray_gate import (
    decision_policy as gray_gate_policy,
)
from service.script_steps import extract_declared_steps

logger = logging.getLogger(__name__)

# 单批行 JSON 序列化字节预算。两个 4MB 限制都要过：单条 activity 结果/输入
# 的 gRPC 上限，以及 workflow task 完成时**聚合多个在飞批次结果**的事务上限
# （max_inflight=3 + 队列积压，实测 3MB/批时事务 4.29MB 超限）→ 收紧到 512KB
_MAX_BATCH_ROWS_BYTES = 512 * 1024

# 多步链（脚本顶层 @step 声明）的步间透传预算（第 N>1 步 request 的 input 单值 /
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

# 活动排队自愈窗口（缺陷㉙）：worker 重启与调度竞态下，Temporal 匹配层可能把
# Scheduled 任务卡住永不投递（实测 33+ 分钟无 Started、无超时事件，worker poller
# 健康、input 仅 1KB 亦不投递；服务端 matching 反复报 "Workflow task already
# started"）。不设 schedule_to_start_timeout 时该兜底不存在，asyncio.gather 上
# 的来源协程永久挂起 → 整链冻结。注意 **SCHEDULE_TO_START 超时不受 RetryPolicy
# 保护**（Temporal 文档行为：STS 超时立即终败活动、不进重试策略）——所以单靠
# 调 STS 时长只会在「楔子冻结」与「背压饿死」之间换口味：STS 短则高水位退避期
# 4 个活动槽位被占满的排队任务 5 分钟即整链 FAILED（实测 300s 死于 16:04），
# STS 长则楔子要等更久。治本 = 下面 _execute_activity 的 workflow 层重调度：
# STS 取 5 分钟快速换任务位（新任务重新进匹配，绕开单个卡死的匹配槽），
# 背压由重调度预算兜住（24 次 × 5 分钟 = 2 小时排队容忍）。
ACTIVITY_SCHEDULE_TO_START = timedelta(seconds=300)
# 96 次 × 5 分钟 = 8 小时排队容忍：16 来源 × (reader+3 worker) 并发争 4 个活动槽，
# 叠加图库高压窗（水位退避期槽位被慢活动长占），实测任务链可连续排队 12+ 轮
# （每轮 5 分钟）才等到槽位——24 次（2h）曾被打穿到评估线，08 执行放宽到 48；
# 09 执行实测存在**单任务饥饿型**排队（某 resolve 调用 33 次换位重发 165 分钟
# 无投递，同期其他任务 1-8 深度正常轮转）——换位旁路对持续过载下的个体任务
# 不保证公平，48（4h）结构性不够，放宽到 96。常数上界改动重放安全（已记录的
# 重调度决策全在小区间，新旧代码同判 continue）。
_STS_RESCHEDULE_ATTEMPTS = 96
# 图库内存高水位的 workflow 层重发起（缺陷㉛）：㉘ 的活动内水位退避（各活动
# 4-18 次 × 20s）只够「分钟级瞬态窗」，实测共享宿主高压窗可持续 2h+，活动内
# 退避 + RetryPolicy 5 次 ≈ 20 分钟总容忍被打穿终败（08 执行 resolve 实锤）。
# 活动终败后由 workflow 层歇 _SLEEP 再重发起：sleep 是 durable timer，不占活动
# 槽位（终败的活动已释放槽）、不烧 RetryPolicy；30 次 × (120s + 活动内退避
# 包络) ≈ 2-3h 持续窗容忍。幂等活动（读源/消歧/INSERT VERTEX upsert）重发起安全。
_WATERMARK_RESCHEDULE_ATTEMPTS = 30
_WATERMARK_RESCHEDULE_SLEEP = 120.0


def _watermark_failure(exc: ActivityError) -> bool:
    """活动失败链（本体+最多 3 层 cause）里是否图库瞬态错误（㉘ 水位/㉜ 存储 RPC 超时）。"""
    seen = exc.failure
    depth = 0
    while seen is not None and depth < 4:
        if _GRAPH_TRANSIENT_RE.search(seen.message or ""):
            return True
        if not seen.HasField("cause"):
            break
        seen = seen.cause
        depth += 1
    return False


async def _execute_activity(fn: Any, arg: Any, **kwargs: Any) -> Any:
    """``workflow.execute_activity`` 的两类可自愈失败重发起封装（workflow 内用）。

    - SCHEDULE_TO_START 排队超时（缺陷㉙）：STS 超时不进 RetryPolicy，活动立即
      终败——catch 后**重新发起**同一活动（新任务号重进匹配队列，绕开卡死的
      匹配槽；槽位背压由 ``_STS_RESCHEDULE_ATTEMPTS`` × STS 时长预算兜住）。
    - 图库内存高水位终败（缺陷㉛）：catch 后 ``workflow.sleep`` 再重发起
      （durable timer，sleep 期间活动槽位归还给其他任务）。
    两预算独立计数，同一任务可交替消耗。异常驱动的循环控制流在重放时按历史
    确定性复现（同一历史产生同一异常序列），重放安全；其他失败（含 STC 超时/
    应用错误）原样上抛交 RetryPolicy 之外的原语义。
    """
    from temporalio.api.enums.v1 import TimeoutType

    sts_budget = kwargs.pop("sts_attempts", _STS_RESCHEDULE_ATTEMPTS)
    wm_budget = kwargs.pop("wm_attempts", _WATERMARK_RESCHEDULE_ATTEMPTS)
    sts_used = 0
    wm_used = 0
    while True:
        try:
            return await workflow.execute_activity(fn, arg, **kwargs)
        except ActivityError as exc:
            cause = (
                exc.failure.cause
                if exc.failure is not None and exc.failure.HasField("cause")
                else None
            )
            if (
                sts_used < sts_budget
                and cause is not None
                and cause.HasField("timeout_failure_info")
                and cause.timeout_failure_info.timeout_type
                == TimeoutType.TIMEOUT_TYPE_SCHEDULE_TO_START
            ):
                sts_used += 1
                logger.warning(
                    "活动 %s 排队 %s 超时（第 %d/%d 次重调度），重新发起",
                    getattr(fn, "__name__", fn),
                    ACTIVITY_SCHEDULE_TO_START,
                    sts_used,
                    sts_budget,
                )
                continue
            if wm_used < wm_budget and _watermark_failure(exc):
                wm_used += 1
                logger.warning(
                    "活动 %s 图库内存高水位终败（第 %d/%d 次），workflow 层歇 %.0fs 后重发起",
                    getattr(fn, "__name__", fn),
                    wm_used,
                    wm_budget,
                    _WATERMARK_RESCHEDULE_SLEEP,
                )
                await workflow.sleep(_WATERMARK_RESCHEDULE_SLEEP)
                continue
            raise


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
        from service.llm_config import get_llm_settings_by_id

        params = get_llm_settings_by_id(llm_id, business_id=payload.get("_llm_business_id"))
        if params is None:
            raise ValueError("任务指定的语言模型不可用")
        resources["llm"] = params
    elif payload.get("_llm_env"):
        # Only the non-secret endpoint/model are fixed in history; credentials stay on worker.
        snapshot = payload["_llm_env"]
        key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
        if not key:
            raise ValueError("任务启动时使用的环境语言模型凭据已失效")
        resources["llm"] = {"api_key": key, **snapshot}

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
    """脚本 ``failures`` 整形为平台失败记录（recordId 缺键的条目丢弃；空串保留、
    count 如实——缺 id 无法建 case/重跑，由建 case 环节计数为 noRecordId 汇报；
    error 不截断）。"""
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
    request: dict[str, Any],
    output: Any,
    access: Any,
    pending: list[Any] | None = None,
) -> dict[str, Any]:
    """S3 中转下的 execute_transform 返回形状：全量输出与失败清单归档，历史只进元数据。

    ``output`` 为脚本原始输出（pendingReview 已弹出、水位元字段已剥离、access 未混入
    ——access 属平台观测数据，保持内联返回的现行为）。gray-gate-v2 双流（
    ``pendingMode=resolve``）下 ``pending`` 挂起清单同样归档 S3，返回
    ``pendingKey``/``pendingCount``（由 workflow 调 resolve_pending_entities 处置）。
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
    if pending:
        result["pendingKey"] = await asyncio.to_thread(
            put_extract_payload_json, step_key_id, batch_idx, f"pending-{chunk_tag}", pending
        )
        result["pendingCount"] = len(pending)
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
# 注册进 sys.modules：dataclasses 等标准库按 cls.__module__ 反查模块字典解析
# 字符串注解（from __future__ import annotations 下全是字符串），未注册的合成
# 模块会以 None.__dict__ 在 import 期炸掉——任何带 @dataclass 的上传脚本都中招。
sys.modules[spec.name] = module
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
    *,
    request: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """共享的脚本子进程启动逻辑（平台喂数抽取 execute_transform 共用）。

    在隔离子进程中以 ``runner`` 调 ``script_path`` 的 ``function_name``；``ctx``
    经 ``KG_SCRIPT_CTX`` env 注入（单参脚本用 kg_sdk.current_context 取）。
    返回 ``(解析后的 stdout 包装 dict, sidecar 路径)``——调用方负责合并 access
    报告并在 finally 里 ``_cleanup_sidecar``。超时/非零退出抛 RuntimeError。
    """
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        if request is None:
            raise RuntimeError("隔离脚本缺少已授权的执行上下文")
        from service.script_resource_broker import ScriptResourceBroker
        from service.script_sandbox_client import execute_script

        # This capability scope is supplied by Temporal, never by uploaded code or API input.
        try:
            execution = activity.info()
            run_identity = [execution.workflow_id, execution.workflow_run_id]
        except RuntimeError:
            from uuid import uuid4

            run_identity = ["direct-test", uuid4().hex]
        trusted_request = {
            **request,
            "_sandboxRunKey": hashlib.sha256(json.dumps(run_identity).encode()).hexdigest(),
        }
        broker = ScriptResourceBroker(trusted_request, ctx)
        try:
            public_context = broker.public_context()
        except Exception:
            broker.close()
            raise
        wrapped = await execute_script(
            script_path, function_name, stdin_data, public_context, timeout, broker
        )
        return wrapped, None

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


@activity.defn
async def finalize_scheduled_execution(request: dict[str, Any]) -> dict[str, Any]:
    """调度执行收尾：workflow 自报终态，回写 execution/task 行（与 register 对称）。

    Schedule 直发 workflow 不经过 API，没有完成回调；终态此前只靠详情页惰性刷新，
    没人查看就永远 RUNNING。终态由 workflow 亲口传入（此处不能向 Temporal describe
    核实——activity 执行时 workflow 自身尚未结束，describe 恒为 RUNNING）。幂等：
    行已是终态则跳过；CANCELLED 场景 workflow 无法收尾，由 execution_reconciler 兜底。
    """
    from service.temporal_runtime import _apply_output_failure_status
    from service.workflow_operations import WorkflowOperationsService
    from service.workflow_repository import repository

    run_id = request.get("runId")
    execution = repository.get_execution_by_run(run_id) if run_id else None
    if execution is None:
        return {"ok": False, "reason": "execution-missing"}
    if execution.get("status") not in (None, "", "RUNNING"):
        return {"ok": True, "deduped": True}
    error = request.get("error")
    if error:
        execution["status"] = "FAILED"
        execution["message"] = str(error)[:500]
    else:
        execution["status"] = "COMPLETED"
        execution["message"] = "工作流执行完成"
        output = request.get("result")
        if isinstance(output, dict):
            execution["output"] = output
            execution = _apply_output_failure_status(execution, output)
    execution["completedAt"] = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    repository.save_execution(execution)
    try:
        WorkflowOperationsService()._sync_task_from_execution(execution)
    except Exception:  # noqa: BLE001
        logger.exception("调度执行收尾同步 task 失败: %s", execution.get("id"))
    _stamp_job_latest(execution)
    return {"ok": True, "status": execution.get("status")}


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
    """单个挂起实体项 → 多路召回（同名精确∪Milvus近邻）+ 评分 → T_LINK case（强制灰区人裁）。

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
    for cand in ed.recall_candidates(client, node_label, [display], space=space).get(display, []):
        if cand["vid"] == vid:
            continue
        score, detail = ed.score_candidate(display, incoming_props, cand["name"], cand.get("props"))
        scored.append(
            {"vid": cand["vid"], "name": cand["name"], "score": round(score, 3), **detail}
        )
    top = sorted(scored, key=lambda x: x["score"], reverse=True)[:TOP_K]
    reason = f"脚本挂起改道消歧：{item.get('reason') or '歧义实体待人工确认'}；召回候选 {len(scored)} 个（同名+近邻）"
    if top:
        reason += f"，最高得分 {top[0]['score']:.2f}"
    manual_review_service.create_direct_case(
        graph_space=space,
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
                "recallPolicy": "exact+milvus-dense-v1",
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
async def load_schema_extract_plan(schema_id: str | dict[str, Any]) -> dict[str, Any]:
    """读控制库组装抽取计划：kind/name/activeProps（目录属性全集）/sources/脚本（S3 下载到临时文件）。"""
    from sqlalchemy.orm import Session as OrmSession

    from db_model.schema_management import GraphSchemaDefinition
    from infra.s3 import get_schema_s3_storage
    from infra.workflow_mysql import get_workflow_engine
    from service.business_access_control import rbac_enabled
    from service.config_ownership import ensure_config_access
    from service.workflow_jobs import authorize_background_execution

    actor = None
    context = schema_id if isinstance(schema_id, dict) else {"schemaId": schema_id}
    if rbac_enabled():
        try:
            actor = authorize_background_execution(context)
        except Exception as exc:
            raise ApplicationError(
                str(exc), type="BusinessAuthorizationDenied", non_retryable=True
            ) from exc
    schema_id = context["schemaId"]
    engine = get_workflow_engine()
    with OrmSession(engine) as session:
        definition = session.get(GraphSchemaDefinition, schema_id)
        if definition is None or definition.is_deleted:
            raise ValueError(f"Schema 不存在: {schema_id}")
        graph_space = definition.graph_space
        if rbac_enabled():
            from service.script_resource_broker import validate_source_sql

            for source_binding in definition.sources:
                sql = (
                    source_binding.query_sql
                    or f"SELECT * FROM `{source_binding.database_name}`.`{source_binding.table_name}`"
                )
                validate_source_sql(sql, source_binding.database_name)
        if actor is not None and not actor.is_admin:
            from dao.mysql_datasource import MysqlDatasourceDAO
            from infra.mysql import session_scope

            with session_scope() as source_session:
                for source in definition.sources:
                    source_row = MysqlDatasourceDAO(source_session).get(source.datasource_id)
                    if source_row is None:
                        raise ApplicationError("来源配置不存在", non_retryable=True)
                    ensure_config_access(source_session, actor, "mysql", source_row.id)
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
        timeout_seconds = int(os.getenv("SCHEMA_WORKFLOW_TIMEOUT_SECONDS", "3600"))
        max_inflight = max(1, int(os.getenv("SCHEMA_EXTRACT_MAX_INFLIGHT", "3")))
        failure_case_cap = max(0, int(os.getenv("SCHEMA_EXTRACT_FAILURE_CASE_CAP", "2000")))
        index_timeout_seconds = max(
            60, int(os.getenv("SCHEMA_EXTRACT_INDEX_TIMEOUT_SECONDS", "1800"))
        )
        # 随环索引重建开关（env 只能在 activity 读，经 plan 传给 workflow）
        build_index_enabled = os.getenv("SCHEMA_EXTRACT_BUILD_INDEX", "1") != "0"
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
    # 步声明解析：@step 装饰器是唯一脚本形态（单步 transform / STEPS 清单已删除）。
    # 上传时 _validate_script 已校验过，这里重新解析兜住绕过上传通道的脚本，
    # 非法即失败（workflow 报清晰错误）。
    try:
        steps = extract_declared_steps(
            data.decode("utf-8-sig", errors="replace"), filename=object_key
        )
    except ValueError as exc:
        raise ValueError(f"Schema 脚本步声明非法: {exc}") from exc
    from service.schema_extraction import extract_definition_id

    return {
        "definitionId": extract_definition_id(schema_key, schema_id),
        "schemaId": schema_id,
        "schemaKey": schema_key,
        "graphSpace": graph_space,
        "kind": kind,
        "name": name,
        "label": label,
        "activeProps": active_props,
        "sources": sources,
        "scriptPath": script_path,
        # run 级脚本副本定位：execute_transform 的 tempfile 丢失时按此重物化
        "scriptRunKey": run_key,
        "scriptSha256": script_sha256,
        # steps 只放 id/fn 两个 str 键（plan 要经 Temporal 序列化进事件历史）
        "steps": steps,
        "timeoutSeconds": timeout_seconds,
        "maxInflight": max_inflight,
        "failureCaseCap": failure_case_cap,
        "indexTimeoutSeconds": index_timeout_seconds,
        "buildIndexEnabled": build_index_enabled,
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
    pk_cursor: str | None = None,
) -> str:
    """构造来源批次 SQL（纯函数，便于单测）。

    - 基表：``query_sql`` 存在时包成子查询（须暴露与 time/pk 同名的列），
      否则 ``{database}.{table}`` 全表；
    - watermark 模式（time_column 非空）：``WHERE time > :wm ORDER BY time, pk LIMIT :n``；
      提供 ``pk_cursor``（批间/跨执行续游标）时用组合条件
      ``time > :wm OR (time = :wm AND pk > :cursor)``——同秒多行只按时间比较
      会把与水位同秒的尾行永久切掉（水位已推进，跨执行也读不回）；
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
    if pk_cursor:
        return (
            f"{base} WHERE (`{time_column}` > :wm OR (`{time_column}` = :wm "
            f"AND `{pk_column}` > :cursor)) ORDER BY `{time_column}`, `{pk_column}` LIMIT :n"
        )
    return f"{base} WHERE `{time_column}` > :wm ORDER BY `{time_column}`, `{pk_column}` LIMIT :n"


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


_UNKNOWN_COLUMN_RE = re.compile(r"unknown column [`'\"]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _unknown_column_name(exc: Exception) -> str | None:
    """从图库报错解析 unknown column 列名（Nebula: ``Unknown column 'X' in schema``）。"""
    match = _UNKNOWN_COLUMN_RE.search(str(exc))
    return match.group(1) if match else None


def _since_seed(request: dict[str, Any]) -> str | None:
    """触发请求携带的 since 作为首轮水位种子（仅来源无持久化水位时生效）。

    只接受可解析的时间串（与前端 SINCE_RULE 同口径），坏值忽略回落全量——
    job 建链只查长度，垃圾串不能炸读取 SQL。keyset（pk 游标）来源不适用。
    """
    raw = request.get("since")
    if not raw:
        return None
    try:
        datetime.fromisoformat(str(raw).replace(" ", "T"))
    except ValueError:
        return None
    return str(raw)


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
    if time_column:
        time_column = _require_identifier(time_column)
    pk_column = _require_identifier(request["pkColumn"])
    query_sql = request.get("querySql") or None
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        from service.script_resource_broker import (
            ScriptAccessDenied,
            validate_script_resources,
            validate_source_sql,
        )

        validate_script_resources(request)
        source = request.get("source") or {}
        for read_key, source_key in (
            ("datasourceId", "datasourceId"),
            ("database", "databaseName"),
            ("table", "tableName"),
            ("querySql", "querySql"),
            ("pkColumn", "pkColumn"),
            ("timeColumn", "timeColumn"),
        ):
            if str(request.get(read_key) or "") != str(source.get(source_key) or ""):
                raise ScriptAccessDenied("读取参数与已授权来源绑定不一致")
        if query_sql:
            query_sql = validate_source_sql(query_sql, database)
        else:
            validate_source_sql(f"SELECT * FROM `{database}`.`{table}`", database)
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
    pk_cursor: str | None = None
    if cursor_kind == "ids":
        pass  # 每块单独构造 binds
    elif cursor_kind == "offset":
        binds = {"n": batch_size, "offset": int(request.get("offset") or 0)}
        if time_column:
            watermark = request.get("watermark")
            if watermark is None and not request.get("chained"):
                wm_row = read_watermark(request.get("definitionId"), request.get("stepId") or "")
                watermark = (
                    (wm_row or {}).get("watermark") or _since_seed(request) or "1970-01-01 00:00:00"
                )
            if watermark is not None:
                binds["wm"] = str(watermark)
    elif cursor_kind == "watermark":
        watermark = request.get("watermark")
        pk_cursor = request.get("pkCursor")
        if watermark is None:
            wm_row = read_watermark(request.get("definitionId"), request.get("stepId") or "")
            watermark = (
                (wm_row or {}).get("watermark") or _since_seed(request) or "1970-01-01 00:00:00"
            )
            # 跨执行续跑：持久化 checkpoint 的 pkCursor 与水位同进组合条件，
            # 否则上次执行同秒尾行永久丢失
            pk_cursor = pk_cursor or ((wm_row or {}).get("checkpoint") or {}).get("pkCursor")
        binds = {"wm": str(watermark), "n": batch_size}
        if pk_cursor:
            binds["cursor"] = str(pk_cursor)
    else:
        # keyset 游标键名与 workflow 批循环回传一致（final["pkCursor"]）：此前误读
        # request["cursor"] 恒为空 → 每批从持久化空游标重读首页 → 无限批循环
        # （2026-10-10 复测「转人工审核」链路时实测：时间列留空的 querySql 绑定
        #  5500+ 批不停、执行永不收尾）。首批未带游标时回退持久化 checkpoint。
        cursor = request.get("pkCursor")
        if cursor is None:
            wm_row = read_watermark(request.get("definitionId"), request.get("stepId") or "")
            cursor = ((wm_row or {}).get("checkpoint") or {}).get("pkCursor") or ""
        binds = {"cursor": str(cursor), "n": batch_size}

    # 首批（请求未带水位且非链式续批）回传本次读取的「起点水位」：控制库水位只在
    # 活动内解析，workflow 侧不可见；watermark 是跑完全部批次后的终值，今日新增
    # 的时间窗下界需要开跑前的值，否则窗口缩成最后一批同秒的行
    start_watermark = (
        binds.get("wm")
        if cursor_kind in ("offset", "watermark")
        and request.get("watermark") is None
        and not request.get("chained")
        else None
    )

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
            pk_cursor=pk_cursor if cursor_kind == "watermark" else None,
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

    # 源库读取整体下放线程：async 活动体内做公网 MySQL 同步读（秒级起步）会
    # 冻结 worker 事件循环——workflow task TMPRL1104 超时、活动重投递延迟的
    # 根因（gkx_verify_1 实测 12 分钟「假死」）。语义与原循环逐行一致
    def _read_rows() -> tuple[list[dict[str, Any]], int]:
        if cursor_kind == "ids":
            rows_acc: list[dict[str, Any]] = []
            for sql, sql_binds in sqls:
                with engine.connect() as conn:
                    for raw in conn.execute(text(sql), sql_binds).mappings().all():
                        rows_acc.append({k: _jsonable(v) for k, v in dict(raw).items()})
            return rows_acc, batch_size
        n = batch_size
        while True:
            fetched = _fetch(n)
            if n <= 1:
                return fetched, 1
            if len(json.dumps(fetched, ensure_ascii=False, default=str).encode()) <= budget:
                return fetched, n
            n = max(1, n // 2)

    try:
        rows, effective_batch = await asyncio.to_thread(_read_rows)
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
            **({"startWatermark": start_watermark} if start_watermark else {}),
        }
    return {
        "rows": rows,
        "recordIds": [str(r.get(pk_column)) for r in rows if r.get(pk_column) is not None],
        "maxTime": max_time,
        "maxPk": max_pk,
        "effectiveBatchSize": effective_batch,
        # offset 模式回传本批生效的增量水位（时间列过滤起点），reader 链式透传
        **({"watermark": binds.get("wm")} if cursor_kind == "offset" else {}),
        **({"startWatermark": start_watermark} if start_watermark else {}),
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
    """把批次行交给脚本转换：payload["rows"] = 行 JSON，调 request.functionName 指定步。

    @step 声明的多步脚本每个 step 调一次本 activity（各自独立 Temporal 重试）：
    - 第 1 步消费平台读的源表行（request/payload 同单步形态）；
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
    from service.business_access_control import rbac_enabled

    if rbac_enabled():
        from service.script_resource_broker import validate_script_resources
        from service.workflow_jobs import authorize_background_execution

        authorize_background_execution({**request, **(request.get("selectors") or {})})
        validate_script_resources(request)
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        # worker 崩溃/容器重建导致本地 tempfile 丢失：按 run 副本重物化
        # （sha256 钉版本，换 worker 接手也拿到同一份字节）
        script_path = Path(await _rematerialize_run_script(request))
    expected_hash = request.get("scriptSha256")
    if rbac_enabled() and not expected_hash:
        raise RuntimeError("隔离脚本缺少内容校验值，请重新启动任务")
    if expected_hash:
        actual_hash = await asyncio.to_thread(
            lambda: hashlib.sha256(script_path.read_bytes()).hexdigest()
        )
        if actual_hash != expected_hash:
            raise RuntimeError("脚本 sha256 校验失败，禁止执行修改后的脚本")
    function_name = request["functionName"]
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
    resource_selectors = dict(request.get("selectors") or {})
    if rbac_enabled():
        from service.workflow_jobs import _job_business

        resource_selectors["_llm_business_id"] = _job_business(None, request)
    else:
        resource_selectors["_llm_business_id"] = None
    resolved = _resolve_resources(
        resource_selectors,
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
            request=request,
        )
        output = (
            wrapped.get("result") if isinstance(wrapped, dict) and "result" in wrapped else wrapped
        )
        stdout_access = wrapped.pop("_access", None) if isinstance(wrapped, dict) else None
        access = _merge_access(stdout_access, sidecar_path)
        # 忽略脚本的 _watermark/_checkpoint（平台按批次游标管理水位）
        output = _strip_watermark_meta(output)
        pending = output.pop("pendingReview", []) if isinstance(output, dict) else []
        # gray-gate-v2 双流：pendingMode=resolve 时不在 activity 内强制建案，
        # 挂起清单交 workflow 调 resolve_pending_entities 真实灰区门控处置
        # （S3 中转归档 pendingKey / 内联随返回值上抛 pendingReview）
        pending_via_workflow = bool(pending) and str(request.get("pendingMode") or "") == "resolve"
        if pending and not pending_via_workflow:
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
            return await _transform_result_via_s3(
                request, output, access, pending=pending if pending_via_workflow else None
            )
        if access is not None and isinstance(output, dict):
            output = {**output, "access": access}
        shaped_output = _truncate_step_extras(output) if isinstance(output, dict) else {}
        if pending_via_workflow and isinstance(shaped_output, dict):
            shaped_output["pendingReview"] = pending
        return shaped_output
    finally:
        _cleanup_sidecar(sidecar_path)


def ngql_typed_fallback(col_type: str, nullable: bool) -> str:
    """空/不可解析值在类型化列上的兜底字面量（NOT NULL 列不能写 NULL）。"""
    if nullable:
        return "NULL"
    if col_type.startswith("int"):
        return "0"
    if col_type.startswith(("double", "float")):
        return "0.0"
    if col_type.startswith("datetime"):
        return 'datetime("1970-01-01 00:00:00")'
    if col_type.startswith("date"):
        return 'date("1970-01-01")'
    if col_type.startswith("bool"):
        return "false"
    return '""'


def ngql_datetime_literal(value: Any, *, date_only: bool = False) -> str | None:
    """识别常见日期/时间文本 → date("…")/datetime("…") 字面量；不匹配回 None。"""
    m = re.match(
        r"^(\d{4})-(\d{1,2})-(\d{1,2})"
        r"(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        str(value).strip(),
    )
    if not m:
        return None
    date_part = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if date_only:
        return f'date("{date_part}")'
    if m.group(4) is None:
        time_part = "00:00:00"
    else:
        time_part = f"{int(m.group(4)):02d}:{m.group(5)}:{int(m.group(6) or 0):02d}"
    return f'datetime("{date_part} {time_part}")'


def ngql_value_for_column(value: Any, col_type: str, nullable: bool) -> str:
    """按列类型把脚本输出的值格式化为 nGQL 字面量（双向类型适配）。

    - string 列一律转字符串（数字字面量写 string 列会被 Nebula 拒绝）；
    - int/double 列保持数字字面量，字符串数字按数解析；
    - date/datetime 列发 date("…")/datetime("…")（裸字符串会被拒）；
    - bool 列发 true/false；
    - 空/不可解析值按可空性回退 NULL 或类型化零值。
    """
    if col_type.startswith(("int", "double", "float")):
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(int(value) if col_type.startswith("int") else float(value))
        text_val = str(value).strip()
        if text_val:
            try:
                return str(int(float(text_val)) if col_type.startswith("int") else float(text_val))
            except ValueError:
                pass
        return ngql_typed_fallback(col_type, nullable)
    if col_type.startswith("datetime"):
        literal = ngql_datetime_literal(value)
        return literal if literal else ngql_typed_fallback(col_type, nullable)
    if col_type.startswith("date"):
        literal = ngql_datetime_literal(value, date_only=True)
        return literal if literal else ngql_typed_fallback(col_type, nullable)
    if col_type.startswith("bool"):
        if isinstance(value, bool):
            return "true" if value else "false"
        text_val = str(value).strip().lower()
        if text_val in ("true", "1", "yes"):
            return "true"
        if text_val in ("false", "0", "no", ""):
            return "false"
        return ngql_typed_fallback(col_type, nullable)
    if value is None:
        return "NULL" if nullable else '""'
    # string 列：bool/数字一律转字符串（裸 true/false/42 写 string 列同样会被拒）
    return json.dumps(str(value), ensure_ascii=False)


# —— 共享图库瞬态错误自愈（缺陷㉘/㉜）——
# 图库通道（trs-graph → Nebula）的瞬态错误按「错误族」识别，目前四个实测签名：
# 1. 高压窗水位 "Used memory hits the high watermark(0.900000)"（㉘）；
# 2. 高压窗尾部 storaged "Storage Error: RPC failure, probably timeout"
#    （HTTP 400 内嵌，㉜ 第一发现——不在水位正则内曾终败整链）；
# 3. 图库栈重启窗口 "java.net.ConnectException: Connection refused/reset"
#    （HTTP 500 内嵌，㉜ 第二发现——trsgraph 容器被干净重启的分钟级窗口内
#    两个活动终败整链，05:31 UTC 实锤）；
# 4. graphd 迁移/重启窗内 "create session failed"（HTTP 500 内嵌，㉜ 第三
#    发现——宿主扩容迁移整栈重启窗口内终败整链，11 执行 EV#525 实锤）。
# 四者同治：瞬态压力/重启随刷盘或服务上线回落（分钟级），默认活动重试窗口
# （5 次 × backoff≤30s ≈ 96s）扛不住 → 活动内按本正则长退避（㉘ 包络），
# 烧尽后 workflow 层 sleep 重发起（㉛ 包络）。新签名出现再扩。
_GRAPH_TRANSIENT_RE = re.compile(
    r"high watermark|RPC failure|Connection (?:refused|reset)|create session failed",
    re.IGNORECASE,
)
_WATERMARK_RETRY_SLEEP_SECONDS = 20.0


def _with_watermark_retry(
    fn: Callable[[], Any],
    *,
    label: str,
    max_attempts: int = 18,
    should_abort: Callable[[], bool] | None = None,
) -> Any:
    """图库高水位错误的专用退避重试；非水位错误原样上抛（活动层重试兜底）。

    默认 18 × 20s = 6 分钟窗口（write_records STC 600s：2000 条限步调写入
    ~20s + 退避上限 360s 仍有余量）；调用方活动 STC 更紧时显式传小
    max_attempts（消歧召回 300s 内用 10、碰撞探测 120s 内用 4）。

    ``should_abort``：**每次真正派发前**（含退避睡醒后的重试）检查，真值即
    抛 RuntimeError 中止——写图路径用来在 VID 锁租期丢失/活动取消后阻止旧
    快照继续派发 INSERT（失锁后的重试写入不能用「整批幂等重试」兜底）。
    """
    from infra.graph_db.exceptions import GraphRequestError

    def _abort_check() -> None:
        if should_abort is not None and should_abort():
            raise RuntimeError(f"{label}：VID 写锁租期丢失/活动取消，中止派发（旧快照不可再写）")

    for attempt in range(1, max_attempts + 1):
        _abort_check()
        try:
            return fn()
        except GraphRequestError as exc:
            if not _GRAPH_TRANSIENT_RE.search(str(exc)):
                raise
            logger.warning(
                "%s 遇图库瞬态错误（高水位/存储 RPC 超时，第 %d/%d 次），%.0fs 后重试",
                label,
                attempt,
                max_attempts,
                _WATERMARK_RETRY_SLEEP_SECONDS,
            )
            time.sleep(_WATERMARK_RETRY_SLEEP_SECONDS)
    _abort_check()
    return fn()


def _write_pacing() -> tuple[int, float]:
    """写图步调（env 可调，activity 内读）：每 every 行歇 sleep 秒。

    批量多行 INSERT 落地后按「行」计步调（与旧逐条口径可比）：默认 500 行 /
    0.5s ≈ 单活动 1000 行/s 上限——多行语句把每行的 HTTP 往返/会话/解析成本
    摊薄后，graphd 单条 64 行语句 ~几十 ms，自然速率本就到千行级，步调只作
    聚合上限保护共享图库（缺陷㉘ 的高水位教训；压力窗再现时调小 every 或
    调大 sleep 即可，无需回退批量）。
    """
    try:
        every = max(0, int(os.getenv("SCHEMA_EXTRACT_WRITE_PACE_EVERY", "500")))
        sleep_s = max(0.0, float(os.getenv("SCHEMA_EXTRACT_WRITE_PACE_SLEEP", "0.5")))
    except ValueError:
        return 500, 0.5
    return every, sleep_s


def _write_batch_rows() -> int:
    """批量写图每条多行 INSERT 的行数上限（env 可调）。

    64 行/条在「HTTP 往返摊薄收益」与「graphd 单语句解析/执行内存」间取平衡
    （与召回/碰撞名单 150/块的口径同量级）；大文本行另有语句字符上限兜底。
    """
    try:
        return max(1, int(os.getenv("SCHEMA_EXTRACT_WRITE_BATCH_ROWS", "64")))
    except ValueError:
        return 64


async def _prewrite_recheck(
    client: Any,
    name_tag: str,
    records: list[dict[str, Any]],
    *,
    graph: dict[str, Any],
    source_table: str,
    step_id: str,
    decision_policy: dict[str, Any] | None = None,
) -> dict[str, int]:
    """写前权威终判（守卫核心）：INSERT 落笔前对整批重做多路召回 + 评分。

    resolve 的判定是乐观预判——并行批次链交错时其召回可能跑在其它批次的
    INSERT 之前（同名双盲双写竞态）。此处是最后一刻的权威判定：图里此刻
    真实存在什么就按什么判。三分支与 resolve 同构：merge → 改写 vid（随后
    的 INSERT 幂等 upsert 到目标节点）；gray → 就地建 T_LINK 案扣留该记录；
    new → 照写。排除自身 vid（resolve 已合并改写的记录 vid 即目标节点本身）。

    原地变异 ``records``（改写 id / 剔除扣留项），调用方随后照常写图。召回
    失败 fail-open：本批按 resolve 判定原样写（不劣于守卫前行为）。

    gray-gate-v2（``decision_policy`` 传入时）：**前置裁决（R2-b）先于召回与
    评分**——按稳定事件身份重新确认既有案/已应用裁决（kept_as_new/
    kept_rewrite 幂等写入豁免重评分，withheld/prior-dropped 扣留剔除，FAILED/
    UNKNOWN 失败关闭），已确认的人工裁决不被重评分否定；eligibility 前置过滤
    + 两阶段执行——先整批纯 decide，任一记录命中 merge →
    ``DEFERRED_MERGE_BLOCKED`` 失败关闭（任何建案/改写副作用前抛出，B′）；
    真实 gray 走 v2 建案（逻辑键 + 证据 v2 + 来源账本 + priorVerdict 三态处置）；
    fail-open except 重抛失败关闭族（不吞）。v1 请求（无 decision_policy）行为不变。
    """
    from service.entity_disambiguation import (
        decide,
        display_name,
        recall_candidates,
        score_candidate,
    )

    stats: dict[str, int] = {"guardMerged": 0, "guardWithheld": 0}

    policy: dict[str, Any] | None = None
    if decision_policy is not None:
        policy = dict(require_known_policy(decision_policy))

    # 前置裁决（R2-b，v2 专用）：已确认的人工裁决贯穿至写入前最后一步——写前
    # 守卫从可信事件身份+耐久应用标记重新确认，不依据可由脚本伪造的 bypass
    # 标记。已应用 create/merge 幂等写入（豁免重评分，否则候选得分变为 merge
    # 会以 DEFERRED_MERGE_BLOCKED 阻断已确认裁决）；reject/待裁决案与 resolve
    # 同口径处置；FAILED/UNKNOWN 由 _prior_ingress_disposition 失败关闭上抛。
    # 先于召回执行：召回 fail-open 提前返回时，扣留/剔除同样生效（已确认裁决
    # 不因召回故障被绕过）。
    prior_exempt: set[int] = set()  # id(record)：已确认裁决豁免重评分
    if policy is not None:
        kept_records: list[dict[str, Any]] = []
        for record in records:
            prior = _prior_ingress_disposition(
                step_id=step_id,
                record=record,
                graph_space=graph.get("space"),
                name_tag=name_tag,
                policy=policy,
                stage="prewrite",
            )
            if prior is None:
                kept_records.append(record)
                continue
            action = prior["action"]
            if action == "withheld":
                # 既有待裁决案重复命中：并入既有案（来源行入账），不重复写图
                stats["guardWithheld"] += 1
            elif action == "dropped":
                stats["guardPriorDropped"] = stats.get("guardPriorDropped", 0) + 1
            else:
                if action == "kept_rewrite":
                    record["id"] = str(prior["rewriteVid"])
                # kept_as_new：已应用 create 幂等写入，原样落图
                prior_exempt.add(id(record))
                kept_records.append(record)
        records[:] = kept_records

    by_name: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        display = display_name(record.get("props"))
        if display:
            by_name.setdefault(display, []).append(record)
    if not by_name:
        return stats

    def _recall() -> Any:
        if policy is not None:
            from service.entity_disambiguation import recall_candidates_envelope

            return _with_watermark_retry(
                lambda: recall_candidates_envelope(
                    client, name_tag, list(by_name), space=graph.get("space")
                ),
                label="写前终判召回",
                max_attempts=10,
            )
        return _with_watermark_retry(
            lambda: recall_candidates(client, name_tag, list(by_name), space=graph.get("space")),
            label="写前终判召回",
            max_attempts=10,
        )

    try:
        recalled = await asyncio.to_thread(_recall)
    except GrayGateFailClosedError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("写前终判召回失败，本批按 resolve 判定原样写图: %s", exc)
        return stats
    if policy is not None:
        existing = recalled.get("candidates") or {}
        routes = recalled.get("routes") or {}
    else:
        existing = recalled
        routes = {}

    def _candidates_of(display: str, self_vid: str) -> list[dict[str, Any]]:
        if policy is not None:
            from service.entity_disambiguation import eligible_candidates

            eligible, _ = eligible_candidates(
                display,
                self_vid,
                existing.get(display, []),
                graph_space=graph.get("space"),
                node_label=name_tag,
            )
            return eligible
        return [c for c in existing.get(display, []) if c["vid"] != self_vid]

    # v2 两阶段：先整批纯 decide（merge 在任何副作用前失败关闭），再落副作用；
    # prior 豁免记录（已确认 create/merge 重放）不进重评分
    decisions: list[tuple[int, dict[str, Any], str, dict[str, Any], list[dict[str, Any]]]] = []
    for pos, record in enumerate(records):
        if id(record) in prior_exempt:
            continue
        display = display_name(record.get("props"))
        if not display:
            continue
        self_vid = str(record.get("id"))
        scored = []
        for cand in _candidates_of(display, self_vid):
            score, detail = score_candidate(
                display, record.get("props"), cand["name"], cand.get("props")
            )
            scored.append(
                {"vid": cand["vid"], "name": cand["name"], "score": round(score, 3), **detail}
            )
        if not scored:
            continue
        outcome = decide(scored)
        if policy is not None and outcome["decision"] == "merge":
            from service.gray_gate import DeferredMergeBlockedError

            raise DeferredMergeBlockedError(
                {
                    "stage": "prewrite",
                    "score": round(float(outcome["score"]), 3),
                    "autoMergeEnabled": False,
                    "policyVersion": policy.get("version"),
                }
            )
        decisions.append((pos, record, outcome["decision"], outcome, scored))

    info, task_id, execution_id, execution = _execution_context_for_cases()
    dropped: set[int] = set()
    for pos, record, decision, outcome, scored in decisions:
        display = display_name(record.get("props"))
        if decision == "merge":  # 仅 v1 可达（v2 在纯 decide 阶段已失败关闭）
            record["id"] = outcome["targetVid"]
            stats["guardMerged"] += 1
        elif decision == "gray":
            try:
                if policy is not None:
                    result = _open_entity_gray_case_v2(
                        graph=graph,
                        name_tag=name_tag,
                        display=display,
                        record=record,
                        scored=scored,
                        outcome=outcome,
                        step_id=step_id,
                        source_table=source_table,
                        info=info,
                        task_id=task_id,
                        execution_id=execution_id,
                        execution=execution,
                        policy=policy,
                        routes=routes,
                        stage="写前终判",
                    )
                    action = result["action"]
                    if action == "withheld":
                        stats["guardWithheld"] += 1
                        dropped.add(pos)
                    elif action == "dropped":
                        stats["guardPriorDropped"] = stats.get("guardPriorDropped", 0) + 1
                        dropped.add(pos)
                    elif action == "kept_rewrite":
                        record["id"] = str(result["rewriteVid"])
                    # kept_as_new：终态 create 重放，原样落图
                else:
                    _open_entity_gray_case(
                        graph=graph,
                        name_tag=name_tag,
                        display=display,
                        record=record,
                        scored=scored,
                        outcome=outcome,
                        step_id=step_id,
                        source_table=source_table,
                        info=info,
                        task_id=task_id,
                        execution_id=execution_id,
                        execution=execution,
                        stage="写前终判",
                    )
                    stats["guardWithheld"] += 1
                    dropped.add(pos)
            except GrayGateFailClosedError:
                # fail-open 例外：失败关闭族不被吞（B′ 错误族必须让批失败）
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "写前终判灰区建案失败 vid=%s，记录按原样写图: %s", record.get("id"), exc
                )
    if dropped:
        records[:] = [record for pos, record in enumerate(records) if pos not in dropped]
    return stats


@activity.defn
async def write_records(request: dict[str, Any]) -> dict[str, Any]:
    """把转换结果写图：实体/关系各走 nGQL 多行批量 INSERT。

    实体走 nGQL ``INSERT VERTEX``（vid=记录 id）——REST ``/nodes/merge`` 会把
    id/name/vid 当身份键从属性剥离，而 Schema DDL 把 id/name 建成 NOT NULL 列，
    merge 永远缺列。只写 activeProps 内的属性，Schema 注入的 NOT NULL 溯源列
    （create_time/update_time/source_table）缺省时由平台补默认值（脚本只管业务
    字段）。``graph.space`` 指定目标图空间。

    实体写前合并：Nebula 的 INSERT VERTEX 对已存在顶点是**整标签覆盖**（未列出
    的列被重置，非列级 upsert），多来源绑同一实体或跨批重写同 vid 时后写会把
    先写的列清掉——写前先做同 VID 列级合并（批内累积 + FETCH 图上旧值，未携带
    的列保留，create_time/update_time 每次刷新），见 ``_merge_entity_rows``。

    批量多行：一批记录按属性列集分组，同组拼成一条多行 INSERT（一条语句一次
    HTTP 往返，替代逐条写；行数上限 ``SCHEMA_EXTRACT_WRITE_BATCH_ROWS``，默认
    64，另有语句字符上限兜底大文本行）。组内同目标去重保最后一条、组间按原始
    序排序，与逐条顺序写语义等价。

    写图自愈：写图遇 ``GraphRequestError`` 且报错为 unknown column 时，从整组
    props 中剔除对应列重试（兜住「运行任务检查通过 → 任务恰好启动 → 属性被删」
    的时序窗口及一切计划快照与图库 schema 的错位）；无法定位列名则原样抛出。
    语句级行值错误（类型不匹配等）回退逐条写定位坏行，坏行按原语义上抛。

    增量索引走方案②a：实际写入的 vid 清单经 S3 claim-check（``vidsKey``）
    传给环末的索引 activity 按冻结词表批级 upsert，本活动不再直连索引。

    写前守卫（``service/entity_write_guard.py``）：INSERT 前对整批做权威终判
    （``_prewrite_recheck``）并持同名微锁包住「终判 + INSERT」临界区——根治
    并行批次同名双盲双写竞态（resolve 召回跑在它批 INSERT 之前）。终判扣留的
    记录从本批剔除，过滤后的 records 经返回值交回工作流（碰撞检测/计数只看
    真正落图的记录）。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from infra.graph_db.exceptions import GraphRequestError
    from service import entity_write_guard as _entity_write_guard

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
    # 增量索引 vid 清单（方案②a）：随环索引改批级增量后，实际写入的 vid 经
    # S3 claim-check 传给环末的索引 activity（事件历史只过 key）。旧请求不带
    # 这些字段 = 不收集，在飞旧 run 的 activity 重试向后兼容。
    index_vids = bool(request.get("indexVids"))
    vid_step_id = str(request.get("stepId") or "")
    vid_batch_idx = int(request.get("batchIdx") or 0)
    vid_chunk_idx = int(request.get("chunkIdx") or 0)

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
        _with_watermark_retry(client.connect, label=f"写图连接 {name}")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 列类型感知序列化：脚本输出的值类型与注册 schema 声明的列类型并不总一致
        # （计数值是 int/float 而列可能声明 string；时间列常收到 "" 或 ISO 文本，
        # 而 DDL 是 datetime/int64——裸字面量与列类型不匹配都会被 Nebula 以
        # "data type does not meet the requirements" 拒绝）。DESCRIBE 一次拿列类型，
        # ngql_value_typed 按列类型双向适配。
        column_types: dict[str, str] = {}
        not_null_cols: set[str] = set()
        try:
            described = _with_watermark_retry(
                lambda: client.execute_read(
                    f"DESCRIBE {'TAG' if kind == 'entity' else 'EDGE'} `{name}`"
                ),
                label=f"DESCRIBE {name}",
                max_attempts=8,
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
            return ngql_value_for_column(value, col_type, nullable=(col or "") not in not_null_cols)

        def filtered(props: dict[str, Any] | None) -> dict[str, Any]:
            # 实体空属性按旧语义跳过（由调用方 continue）；关系纯连接边（脚本
            # 无任何属性输出）不能空列清单 INSERT——EDGE DDL 的审计列是平台
            # 注入的 NOT NULL，缺列会被 Nebula 拒绝，必须走注入/回填
            if not props and kind == "entity":
                return {}
            merged = dict(props) if props else {}
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
            # Nebula 拒绝（"not null field doesn't have a default value"）。
            # not_null_cols 来自 DESCRIBE（图库 DDL 真值），不要求在 activeProps
            # 内——目录与 DDL 错位时以 DDL 为准补列
            for col in not_null_cols:
                if col not in result:
                    default = "" if column_types.get(col, "string").startswith("string") else "0"
                    result[col] = default
            return result

        def write_with_self_heal(record: dict[str, Any], props: dict[str, Any]) -> None:
            while True:
                if _abort_write():
                    raise RuntimeError(
                        "写图自愈：VID 写锁租期丢失/活动取消，中止派发（旧快照不可再写）"
                    )
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
                        # 关系也走 nGQL INSERT EDGE：REST /edges/merge 要求
                        # identityProps 非空（平台语义里边以 from/to/rank 定位），
                        # 空 identity 会被 400 拒绝
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

        if kind == "relation" and records:
            # 关系写图前端点消歧（跨执行兜底）：端点命中未决 T_LINK case 的边
            # 暂存进 case 快照（裁决时补写，不产生悬挂点）；已裁决 merge 的端点
            # 改写为目标实体；端点实体被驳回的边丢弃。查询失败按原样写，不阻塞批次
            from service.manual_review_production import manual_review_service

            if request.get("decisionPolicy") is not None:
                # gray-gate-v2 失败关闭链：① 应用 resolve_pending_entities 给出的
                # 端点覆写（canonical 改写 + 无效端点过滤）；② park 版本化路由
                # （失败关闭族上抛转 ApplicationError，不降级原样写）；③ 剩余端点
                # 存在性批量终判（未知端点 claim-check 归档 + 全批失败关闭）。
                # 三步都不再「查询失败按原样写」——边悬挂的代价高于批失败。
                try:
                    records, skipped_invalid = _apply_endpoint_overrides(
                        records,
                        invalid_vids=request.get("invalidEndpointVids") or [],
                        rewrite_map=request.get("rewriteMap") or {},
                    )
                    if skipped_invalid:
                        logger.info("端点未通过写入描述符门控，跳过 %s 条边", skipped_invalid)
                    if records:
                        parked = await asyncio.to_thread(
                            manual_review_service.park_or_rewrite_edges,
                            name,
                            records,
                            graph_space=space or None,
                            decision_policy=request.get("decisionPolicy"),
                        )
                        records = parked.get("records") or []
                        if parked.get("parked"):
                            logger.info(
                                "关系端点待消歧，暂存 %s 条（随 T_LINK 裁决补写）",
                                parked["parked"],
                            )
                        if parked.get("dropped"):
                            logger.info("关系端点实体已被驳回，丢弃 %s 条", parked["dropped"])
                    if records:
                        unknown = await _assert_endpoints_exist(
                            client,
                            records,
                            step_id=request.get("stepId") or "write",
                            batch_idx=int(request.get("batchIdx") or 0),
                            chunk_idx=int(request.get("chunkIdx") or 0),
                        )
                        if unknown:
                            from service.gray_gate import BlockedEndpointUnknownError

                            claim = await _claim_check_unknown_endpoints(
                                unknown,
                                step_id=request.get("stepId") or "write",
                                batch_idx=int(request.get("batchIdx") or 0),
                                chunk_idx=int(request.get("chunkIdx") or 0),
                            )
                            raise BlockedEndpointUnknownError({"edgeType": name, **claim})
                except GrayGateFailClosedError as exc:
                    raise _fail_closed_error(exc) from None
            else:
                try:
                    parked = manual_review_service.park_or_rewrite_edges(
                        name, records, graph_space=space or None
                    )
                    records = parked.get("records") or []
                    if parked.get("parked"):
                        logger.info(
                            "关系端点待消歧，暂存 %s 条（随 T_LINK 裁决补写）", parked["parked"]
                        )
                    if parked.get("dropped"):
                        logger.info("关系端点实体已被驳回，丢弃 %s 条", parked["dropped"])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("关系端点消歧查询失败，按原样写图: %s", exc)

        # 批量多行写图下放线程：一批记录按「属性列集」分组拼成多行 INSERT 语句
        # （一条语句一次 HTTP 往返，摊薄逐条写的会话/解析成本，吞吐 5-10×）。
        # 注意 Nebula 的 INSERT VERTEX/EDGE 对已存在目标是整标签/整边覆盖：
        # 未列出的列会被重置成默认值，「不同列集的组各写各的列」并不成立
        # （2026-10-18 页面测试实测证伪）。实体的多来源/跨批同 VID 由
        # _merge_entity_rows 先做列级合并兜住；分组只影响语句拼装形状。
        # 组内单行级错误（类型不匹配等）回退逐条隔离；高水位/瞬态错误走专用
        # 退避（_with_watermark_retry），每累计 pace_every 行歇 pace_sleep 秒。
        pace_every, pace_sleep = _write_pacing()
        batch_rows = _write_batch_rows()
        # 语句字符上限：防大文本行（abstract 级）把单条语句撑过 graphd 语句
        # 长度/REST body 限制；超限即切块（单行超限仍独占一条语句）。
        max_stmt_chars = 2_000_000
        # per-VID 写锁状态（fail-closed）：lost=心跳续期失败置位；cancel=活动
        # 取消排空置位。_write_all 在 chunk 间、_write_chunk/write_with_self_heal
        # 在每次真正派发前（含高水位退避重试、未知列自愈、逐条回退）检查——
        # 失锁/取消后旧快照不得再派发 INSERT
        vid_lost: dict[str, Any] = {}

        def _abort_write() -> bool:
            return bool(vid_lost.get("lost") or vid_lost.get("cancel"))

        def _fetch_existing_props(vids: list[str]) -> dict[str, dict[str, Any]]:
            """批量读图上已有属性（实体写前合并用）。

            ``FETCH PROP ON tag v1,v2,... YIELD id(vertex), properties(vertex)``；
            64 个 vid 一条语句（与写批同量级）。trs-graph 可能把 map 序列化成
            JSON 字符串，两种形状都兜住。读失败经 _with_watermark_retry 烧尽后
            上抛——合并失败宁可让活动重试，不能静默退回「覆盖清列」旧行为。
            同理，**旧属性无法解析或形状异常也必须抛错**（P2 熔断）：按「无
            旧值」继续写 = 静默覆盖清列，且发生在任何 INSERT 之前，抛错时本批
            零写入。
            """
            from infra.graph_db.exceptions import GraphRequestError

            out: dict[str, dict[str, Any]] = {}
            for start in range(0, len(vids), 64):
                part = vids[start : start + 64]
                quoted = ", ".join(json.dumps(v, ensure_ascii=False) for v in part)
                result = _with_watermark_retry(
                    lambda quoted=quoted: client.execute_read(
                        f"FETCH PROP ON `{name}` {quoted} "
                        "YIELD id(vertex) AS vid, properties(vertex) AS props"
                    ),
                    label=f"读旧值合并 {name} ×{len(part)}",
                )
                for row in getattr(result, "records", None) or []:
                    vid = str(row.get("vid") or "")
                    if not vid:
                        continue
                    value = row.get("props")
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except ValueError as exc:
                            raise GraphRequestError(
                                f"图上旧属性无法解析（{name} vid={vid}，值形如 "
                                f"{str(value)[:60]!r}）——中止写入防覆盖清列",
                                status_code=502,
                            ) from exc
                    if not isinstance(value, dict):
                        raise GraphRequestError(
                            f"图上旧属性形状异常（{name} vid={vid}，"
                            f"type={type(value).__name__}）——中止写入防覆盖清列",
                            status_code=502,
                        )
                    # 图上 NULL（从未置过的列）不进合并，交给 filtered 的
                    # NOT NULL 兜底，避免把 NULL 显式写回
                    out[vid] = {k: v for k, v in value.items() if v is not None}
            return out

        def _merge_entity_rows() -> list[dict[str, Any]]:
            """实体同 VID 列级合并：批内累积 + 图上旧值保留。

            多来源绑同一实体（如 Person=dwd_scholar+dwd_zh_author）或跨批重写
            同一 vid 时，后写只携带子集列，裸 INSERT 会把先写的列重置掉。合并
            规则（列级「后写覆盖、未携带保留」）：
            1) 批内同 VID 多条按出现序累积 props（同列后者覆盖，先出现的列保留）；
            2) FETCH 图上已有属性，记录未携带的列保留图上值——create_time/
               update_time 除外（每次写入由平台兜底刷新，维持旧口径）；
            3) DESCRIBE 可知标签全列且本批已覆盖全部列时跳过 FETCH 省一次往返。
            """
            if not records:
                return records
            accumulated: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for record in records:
                vid = str(record.get("id") or "")
                if not vid:
                    continue
                if vid not in accumulated:
                    accumulated[vid] = {"id": record["id"], "props": {}}
                    order.append(vid)
                accumulated[vid]["props"].update(record.get("props") or {})
            if not order:
                return records
            tag_cols = set(column_types) if column_types else None
            fetch_vids = [
                vid
                for vid in order
                if tag_cols is None or (tag_cols - set(accumulated[vid]["props"]))
            ]
            existing = _fetch_existing_props(fetch_vids) if fetch_vids else {}
            for vid in order:
                old = existing.get(vid) or {}
                merged = {
                    **{k: v for k, v in old.items() if k not in ("create_time", "update_time")},
                    **accumulated[vid]["props"],
                }
                accumulated[vid]["props"] = merged
            return [accumulated[vid] for vid in order]

        def _prepared(
            rows: list[dict[str, Any]] | None = None,
        ) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
            prepared_rows: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
            for idx, record in enumerate(records if rows is None else rows):
                props = filtered(record.get("props"))
                if kind == "entity" and not props:
                    continue
                if (
                    kind == "entity"
                    and (not active_props or "id" in active_props)
                    and not str(props.get("id") or "").strip()
                ):
                    # 身份列 id 平台兜底：vid 即记录 id，脚本未显式输出（或输出
                    # 空串）时补齐——id 是 Schema 注入的 NOT NULL 身份列，落空串
                    # 会让身份失去意义。仅在 id 属于白名单时注入，避免给未声明
                    # id 列的 Schema 加未知列。
                    props["id"] = str(record["id"])
                prepared_rows.append((idx, record, props))
            return prepared_rows

        def _row_segment(record: dict[str, Any], props: dict[str, Any], cols: list[str]) -> str:
            values = ", ".join(ngql_value_typed(props.get(col), col) for col in cols)
            if kind == "entity":
                vid = json.dumps(str(record["id"]), ensure_ascii=False)
                return f"{vid}:({values})"
            src = json.dumps(str(record["fromId"]), ensure_ascii=False)
            dst = json.dumps(str(record["toId"]), ensure_ascii=False)
            return f"{src}->{dst}:({values})"

        def _write_chunk(
            cols: list[str], chunk: list[tuple[dict[str, Any], dict[str, Any]]]
        ) -> int:
            while True:
                if _abort_write():
                    raise RuntimeError(
                        "批量写图：VID 写锁租期丢失/活动取消，中止本 chunk 派发（旧快照不可再写）"
                    )
                cols_sql = ", ".join(f"`{col}`" for col in cols)
                values_sql = ", ".join(_row_segment(record, props, cols) for record, props in chunk)
                if kind == "entity":
                    stmt = f"INSERT VERTEX `{name}`({cols_sql}) VALUES {values_sql}"
                else:
                    stmt = f"INSERT EDGE `{name}`({cols_sql}) VALUES {values_sql}"
                try:
                    _with_watermark_retry(
                        lambda stmt=stmt: client.execute_write(stmt),
                        label=f"批量写图 {name} ×{len(chunk)}",
                        should_abort=_abort_write,
                    )
                    return len(chunk)
                except GraphRequestError as exc:
                    if _GRAPH_TRANSIENT_RE.search(str(exc)):
                        # 瞬态包络已烧尽：上抛给活动层重试/工作流层重发起，
                        # 不在本层降级（保持与逐条时代相同的失败语义）。
                        raise
                    bad_column = _unknown_column_name(exc)
                    if bad_column and bad_column in cols and len(cols) > 1:
                        logger.warning(
                            "批量写图遇未知列 %s，整组剔除后重试（%s）",
                            bad_column,
                            name,
                        )
                        cols.remove(bad_column)
                        for _, props in chunk:
                            props.pop(bad_column, None)
                        continue
                    if len(chunk) > 1:
                        # 行级错误（值类型不匹配等）整条语句被拒：回退逐条定位，
                        # 坏行仍按原语义上抛（活动失败 → Temporal 重试整批，
                        # 幂等 upsert），好行不陪葬。
                        logger.warning(
                            "批量写图语句被拒回退逐条（%s：%s）",
                            name,
                            str(exc)[:200],
                        )
                        for record, props in chunk:
                            _with_watermark_retry(
                                lambda record=record, props=props: write_with_self_heal(
                                    record, props
                                ),
                                label=f"写图 {name} {record.get('id') or record.get('fromId')}",
                                should_abort=_abort_write,
                            )
                        return len(chunk)
                    raise

        # 实际写入成功的实体 vid（空属性跳过/组内去重掉的都不进清单）——环末
        # 增量索引用；在 _write_chunk 语句成功后按 chunk 收集（chunk 是组内
        # 去重后的实际写入行，回退逐条路径同样以整 chunk 成功返回）。
        written_vids: list[str] = []

        def _write_all() -> int:
            written_local = 0
            unslept = 0
            # 实体写前合并（守卫锁临界区内）：多来源/跨批同 VID 未携带的列
            # 保留图上旧值，不再被后写覆盖清空
            write_rows = _merge_entity_rows() if kind == "entity" else records
            groups: dict[tuple[str, ...], list[tuple[int, dict[str, Any], dict[str, Any]]]] = {}
            for idx, record, props in _prepared(write_rows):
                groups.setdefault(tuple(props.keys()), []).append((idx, record, props))
            # 组间按组内最后一条记录的原始序执行（共享列终值与逐条写一致）
            ordered = sorted(groups.items(), key=lambda kv: kv[1][-1][0])
            for _, items in ordered:
                # 同列集组内同目标去重保最后一条（同列覆盖 = 顺序写的最后写者）
                by_target: dict[Any, tuple[dict[str, Any], dict[str, Any]]] = {}
                for _, record, props in items:
                    if kind == "entity":
                        by_target[str(record["id"])] = (record, props)
                    else:
                        by_target[(str(record["fromId"]), str(record["toId"]))] = (record, props)
                rows = list(by_target.values())
                cols = list(items[0][2].keys())
                start = 0
                while start < len(rows):
                    if _abort_write():
                        raise RuntimeError(
                            "VID 写锁租期丢失/活动取消，中止本批后续 chunk"
                            "（已写 chunk 幂等，活动层整批重试）"
                        )
                    chunk: list[tuple[dict[str, Any], dict[str, Any]]] = []
                    size = 0
                    while start < len(rows) and len(chunk) < batch_rows:
                        record, props = rows[start]
                        row_len = 64 + sum(len(str(v)) for v in props.values())
                        if chunk and size + row_len > max_stmt_chars:
                            break
                        chunk.append((record, props))
                        size += row_len
                        start += 1
                    written_local += _write_chunk(cols, chunk)
                    if kind == "entity":
                        written_vids.extend(str(record["id"]) for record, _ in chunk)
                    unslept += len(chunk)
                    if pace_every and unslept >= pace_every:
                        time.sleep(pace_sleep)
                        unslept = 0
            return written_local

        guard_stats: dict[str, int] = {}

        async def _run_write_all() -> int:
            # per-VID fail-closed 写锁包住「FETCH 旧值 → 合并 → INSERT」整个读改写
            # 窗口（多来源 asyncio.gather 并行 + 来源内 N worker 下，同名锁按显示名
            # 加键管不到无名/异名同 VID 的并发子集写）。在调用点惰性取 records 的
            # vid——终判会原地改写目标 vid（合并→既有节点），按最终写入目标加锁；
            # FETCH 在 _write_all 内，锁全程覆盖。与同名锁分野：同名锁保消歧活性
            # （fail-open），VID 锁保数据正确性（fail-closed，Redis 故障即重试，
            # 不降级）。
            vid_lock = (
                _entity_write_guard.vid_write_locks(
                    space, name, (r.get("id") for r in records), lost=vid_lost
                )
                if kind == "entity" and records and _entity_write_guard.vid_lock_enabled()
                else nullcontext()
            )
            async with vid_lock:
                # 同步写线程不随协程取消而停（to_thread 取消只放弃等待）：
                # shield + 取消排空——置停止派发标志后**等在途线程收尾**再退
                # 出临界区（期间仍持锁 + 心跳续期），杜绝「锁已还、僵尸线程
                # 持旧快照继续 INSERT」的并发清列窗口；只 shield 不排空无效。
                write_task = asyncio.create_task(asyncio.to_thread(_write_all))
                try:
                    return await asyncio.shield(write_task)
                except asyncio.CancelledError:
                    vid_lost["cancel"] = True
                    logger.warning("写图活动取消：置停止派发标志，排空在途写线程后再解锁")
                    while True:
                        try:
                            # 排空期间每次等待同样 shield：外层重复取消只落在
                            # shield 外壳上，不传染 write_task。一旦传染，任务已
                            # 取消而底层同步线程停不下来，再 await 已取消任务会
                            # 立即抛错且不让出事件循环——无让出点忙等，饿死同
                            # 循环的心跳与一切协程（Codex 三轮探针：watchdog 42）。
                            await asyncio.shield(write_task)
                        except asyncio.CancelledError:
                            if write_task.cancelled():
                                # 防御分支（持续 shield 下不可达）：工作任务自身
                                # 已取消，其结果不再承载线程收尾信号，继续等只会
                                # 忙等；取消标志已置、线程不会再派发，跳出上抛。
                                break
                            continue  # 外层重复取消：write_task 未受传染，继续排空
                        except Exception:  # noqa: BLE001
                            break  # 线程以错误收尾（含失锁熔断）：取消仍优先上抛
                        break
                    raise

        if kind == "entity" and records and _entity_write_guard.prewrite_recheck_enabled():
            from service.entity_disambiguation import display_name as _entity_display_name

            names = sorted(
                {
                    display
                    for display in (_entity_display_name(r.get("props")) for r in records)
                    if display
                }
            )
            # 同名微锁包住「终判 + INSERT」临界区：同名写入方跨批/跨来源/跨 job
            # 串行（Redis SET NX PX，fail-open），异名完全并行。终判后 INSERT
            # （含 VID 锁）仍在同名锁内——后到者的终判召回必须能看到先到者
            # 已提交的 INSERT，否则同名双写根治被退化
            lock = (
                _entity_write_guard.name_write_locks(settings.space, name, names)
                if names and _entity_write_guard.name_lock_enabled()
                else nullcontext()
            )
            async with lock:
                try:
                    guard_stats = await _prewrite_recheck(
                        client,
                        name,
                        records,
                        graph=graph,
                        source_table=source_table,
                        step_id=request.get("stepId") or "write",
                        decision_policy=request.get("decisionPolicy"),
                    )
                except GrayGateFailClosedError as exc:
                    # 写前终判的失败关闭族（DEFERRED_MERGE_BLOCKED 等）不降级照写
                    raise _fail_closed_error(exc) from None
                written = await _run_write_all()
        else:
            written = await _run_write_all()
        result: dict[str, Any] = {"written": written, **guard_stats}
        if kind == "entity" and index_vids and vid_step_id and written_vids:
            # S3 中转未开 = 本栈增量索引不可用：计划内不带 key（索引步跳过），
            # 不算失败；上传失败则上抛——activity 重试幂等重写图 + 重传，绝不
            # 静默丢失 vid 清单（e2e 抽取静默丢失红线）
            from service.extract_payload_store import payload_s3_enabled, put_extract_payload_json

            if not payload_s3_enabled():
                logger.warning(
                    "增量索引需要批载荷 S3 中转（SCHEMA_EXTRACT_PAYLOAD_S3_ENABLED=true），"
                    "本批 %s 个 vid 未留档，随环索引步将跳过",
                    len(written_vids),
                )
            else:
                result["vidsKey"] = await asyncio.to_thread(
                    put_extract_payload_json,
                    vid_step_id,
                    vid_batch_idx,
                    f"vids-{vid_chunk_idx:02d}",
                    {"label": name, "vids": written_vids},
                )
        if guard_stats.get("guardWithheld"):
            # 写前终判扣留了记录：把过滤后的 records 交回工作流，后续碰撞检测/
            # 计数只看真正落图的记录（与 resolve 扣留同一语义）
            if request.get("recordsKey"):
                from service.extract_payload_store import put_extract_payload_json

                result["outKey"] = await asyncio.to_thread(
                    put_extract_payload_json,
                    request.get("stepId") or "write",
                    int(request.get("batchIdx") or 0),
                    f"guarded-{int(request.get('chunkIdx') or 0):02d}",
                    records,
                )
                result["keptCount"] = len(records)
            else:
                result["records"] = records
        return result
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            logger.exception("关闭图客户端失败")


def _execution_context_for_cases() -> tuple[Any, str, Any, dict[str, Any]]:
    """建案所需的执行上下文（taskId/executionId/execution），拿不到给兜底。"""
    info = _activity_info_safe()
    try:
        from service.workflow_repository import repository

        execution = repository.get_execution_by_workflow(info.workflow_id) or {}
    except Exception:  # noqa: BLE001
        execution = {}
    task_id = execution.get("taskId") or f"PI-extract-{info.workflow_id[:12]}"
    return info, task_id, execution.get("id"), execution


# ---------------------------------------------------------------------------
# gray-gate-v2：失败关闭边界转换 + 灰案 ingress（逻辑键 + 来源账本 + priorVerdict）
# ---------------------------------------------------------------------------


def _fail_closed_error(exc: Exception) -> ApplicationError:
    """GrayGate 失败关闭错误族 → Temporal ApplicationError（activity 边界转换）。

    不可重试（错误族语义：同输入重试不改变判定）；``error_type``=稳定错误码；
    ``details`` 只带零标识符诊断负载（原始 vid/rid 完整清单走受控 claim-check）。
    """
    code = getattr(exc, "code", None)
    detail = getattr(exc, "detail", None)
    # temporalio ApplicationError 的 details 是位置可变参数（无 details=/error_type=
    # 关键字）；单 detail 元组传入，type=稳定错误码
    return ApplicationError(
        str(exc),
        *((detail,) if detail is not None else ()),
        type=str(code or "GRAY_GATE_FAIL_CLOSED"),
        non_retryable=True,
    )


def _source_binding_of_step(step_id: str) -> str:
    """step_id（``source:{绑定id}#{步id}``）→ 来源绑定 id（ingress 逻辑键材料）。"""
    head = str(step_id or "").split("#", 1)[0]
    return head.removeprefix("source:") or str(step_id or "align")


def _gray_ingress_material(
    *,
    step_id: str,
    record: dict[str, Any],
    graph_space: str | None,
    name_tag: str,
    reprocess_batch_id: str | None = None,
) -> tuple[list[str], str, str]:
    """灰案 ingress 逻辑键材料（gray-gate-v2）。

    ``[sourceBindingId, sourceRecordId, sourceEventVersion, graphSpace, nodeLabel,
    vid (, reprocessBatchId)?]``——``sourceRecordId`` 权威（来源行主键，缺省回退
    ``id``＝vid）；sourceEventVersion 声明值权威（记录自带
    ``sourceEventVersion`` 即用之），否则 canonicalization-v1 全量 HMAC（dedupe
    专用密钥 ``GRAY_GATE_DEDUPE_IDENTITY_KEY``，缺失失败关闭=部署前置条件），
    摘要排除运行时生成的摄取/审计列（``GRAY_GATE_VOLATILE_SOURCE_KEYS``，
    R4）——同一源业务行跨重跑换 digest 不再重复建案。执行 id、策略/评分
    版本、快照哈希一律不进键：重跑/换版命中同一案。
    """
    from service.gray_gate import GRAY_GATE_VOLATILE_SOURCE_KEYS, UnstableSourceIdentityError

    source_record_id = str(record.get("sourceRecordId") or record.get("id") or "").strip()
    if not source_record_id:
        raise UnstableSourceIdentityError({"stage": "ingress"})
    event_version, basis = compute_event_version(
        record,
        declared_version=record.get("sourceEventVersion"),
        volatile_keys=GRAY_GATE_VOLATILE_SOURCE_KEYS,
    )
    material = [
        _source_binding_of_step(step_id),
        source_record_id,
        event_version,
        str(graph_space or ""),
        str(name_tag),
        str(record.get("id") or source_record_id),
    ]
    if reprocess_batch_id:
        material.append(str(reprocess_batch_id))
    # 与 gray_gate.ingress_dedupe_key 同构（create_direct_case 对材料整体 sha）：
    # 逻辑键派生口径的唯一权威在 gray_gate，此处只组材料
    return material, event_version, basis


def _prior_ingress_disposition(
    *,
    step_id: str,
    record: dict[str, Any],
    graph_space: str | None,
    name_tag: str,
    policy: dict[str, Any] | None = None,
    stage: str,
) -> dict[str, Any] | None:
    """稳定事件身份前置裁决（R2）：先于重新评分与任何图写副作用。

    按逻辑 ingress identity 查既有案（``find_ingress_case``，材料与建案同构）：

    - 无既有案 → None（调用方正常评分建案）；
    - 既有案待裁决（OPEN/CLAIMED/IN_REVIEW 重复命中）→ ``{"action":
      "withheld"}``——来源行幂等入账后并入既有案等裁决，不重新评分建新案；
    - 既有案终态 → ``priorVerdict`` 三态处置（reject 召回退化/评分变化不再
      复活写图；merge 在 remap 未就绪时 ``MERGE_CANONICAL_MISSING`` 失败关闭）；
    - 应用失败/UNKNOWN → 失败关闭上抛（VerdictNotAppliedError，不猜测）。

    失败关闭族原样上抛——调用方的 fail-open except 必须重抛。
    """
    from service.gray_gate import prior_verdict_disposition
    from service.manual_review_production import manual_review_service

    material, event_version, _basis = _gray_ingress_material(
        step_id=step_id, record=record, graph_space=graph_space, name_tag=name_tag
    )
    found = manual_review_service.find_ingress_case(material)
    if not found:
        return None
    prior = found.get("priorVerdict") if isinstance(found, dict) else None
    if isinstance(prior, dict):
        disposition = prior_verdict_disposition(prior, source_vid=str(record.get("id") or ""))
        if disposition["disposition"] == "drop_record":
            return {"action": "dropped", "rewriteVid": None}
        if disposition["disposition"] == "rewrite_to_canonical":
            return {"action": "kept_rewrite", "rewriteVid": str(disposition["vid"])}
        return {"action": "kept_as_new", "rewriteVid": None}
    # 重复命中待裁决案：并入既有案（来源行幂等入账），不重新评分
    info, task_id, execution_id, execution = _execution_context_for_cases()
    manual_review_service.append_case_sources(
        str(found.get("reviewId") or ""),
        [
            {
                "executionId": str(execution_id or ""),
                "sourceBindingId": _source_binding_of_step(step_id),
                "sourceRecordId": str(record.get("sourceRecordId") or record.get("id") or ""),
                "sourceEventVersion": event_version,
                "evidence": {
                    "stage": stage,
                    "policyVersion": (policy or {}).get("version"),
                    "nameRuleVersion": (policy or {}).get("nameRuleVersion") or NAME_RULE_VERSION,
                    "propKeys": sorted((record.get("props") or {}).keys()),
                },
                "reason": f"gray-dup:{stage}",
            }
        ],
    )
    return {"action": "withheld", "rewriteVid": None}


def _open_entity_gray_case_v2(
    *,
    graph: dict[str, Any],
    name_tag: str,
    display: str,
    record: dict[str, Any],
    scored: list[dict[str, Any]],
    outcome: dict[str, Any],
    step_id: str,
    source_table: str,
    info: Any,
    task_id: str,
    execution_id: Any,
    execution: dict[str, Any],
    policy: dict[str, Any],
    routes: dict[str, Any] | None,
    stage: str,
) -> dict[str, Any]:
    """gray-gate-v2 灰案建案：只有真实 decide=gray 才建 T_LINK（B′）。

    相对 v1（``_open_entity_gray_case``）：dedupe 用逻辑 ingress identity（快照
    哈希不再随召回可用性漂移）；候选证据 v2（comparedProps/propCompared/
    propMatched/nameSim/propsAgree 原样上桌）；``_resolution`` 记 scoreDecision/
    effectiveDisposition/weights/thresholds/nameRuleVersion/policyVersion；召回
    路由状态与事件版本 basis 进 extra_snapshot（input_snapshot）。建案响应带
    ``priorVerdict``（终态重复命中）时按 application 表权威三态处置返回动作，
    由调用方改写/丢弃记录；新案与 OPEN 重复命中追加来源账本行（幂等）。
    失败关闭族异常原样上抛——调用方的 fail-open except 必须重抛。
    """
    from service.entity_disambiguation import TOP_K
    from service.manual_review_production import manual_review_service

    thresholds = policy.get("thresholds") or {}
    material, event_version, basis = _gray_ingress_material(
        step_id=step_id, record=record, graph_space=graph.get("space"), name_tag=name_tag
    )
    evidence_candidates = [
        {
            "vid": c["vid"],
            "name": c["name"],
            "score": c["score"],
            **{
                key: c[key]
                for key in ("nameSim", "propsAgree", "propCompared", "propMatched", "comparedProps")
                if key in c
            },
        }
        for c in sorted(scored, key=lambda x: x["score"], reverse=True)[:TOP_K]
    ]
    response = manual_review_service.create_direct_case(
        graph_space=graph.get("space"),
        task_id=task_id,
        execution_id=execution_id,
        step_id=step_id,
        kind="entity",
        candidate={
            "name": display,
            "newIds": [str(record.get("id"))],
            "existingCandidates": evidence_candidates,
            "_incoming": {
                "vid": str(record.get("id")),
                "props": record.get("props") or {},
                "sourceTable": source_table,
                "sourceEventVersion": event_version,
                "sourceEventBasis": basis,
            },
            "_pendingRelations": [],
            "_graphSpace": graph.get("space"),
            "_nodeLabel": name_tag,
            "_resolution": {
                "policyVersion": policy.get("version"),
                "evidenceVersion": policy.get("evidenceVersion"),
                "nameRuleVersion": policy.get("nameRuleVersion") or NAME_RULE_VERSION,
                "scoreDecision": outcome["decision"],
                "effectiveDisposition": "withhold_pending_review",
                "matchScore": outcome["score"],
                "margin": outcome["margin"],
                "weights": policy.get("weights") or {},
                "thresholds": thresholds,
                "recallPolicy": "exact+milvus-dense-v1",
            },
        },
        object_id=str(record.get("id")),
        object_name=display,
        node_label=name_tag,
        reason=(
            f"消歧得分 {outcome['score']:.2f} 落入灰区 "
            f"[{thresholds.get('grayLow')}, {thresholds.get('merge')})，需人工裁决（{stage}）"
        ),
        confidence=outcome["score"],
        workflow_id=info.workflow_id,
        workflow_run_id=info.workflow_run_id,
        template_id="T_LINK",
        workflow_type="kg.schema.extract",
        exception_code="KG_ENTITY_DISAMBIGUATION_GRAY",
        resume_token=f"extract-resolve:{execution_id}:{record.get('id')}",
        source_table=source_table or None,
        source_record_id=str(record.get("sourceRecordId") or record.get("id") or ""),
        dedupe_material=material,
        extra_snapshot={
            "jobId": execution.get("jobId"),
            "routes": routes or {},
            "sourceEventBasis": basis,
        },
    )
    prior = response.get("priorVerdict") if isinstance(response, dict) else None
    if isinstance(prior, dict):
        # 终态案重放：三态处置（FAILED/UNKNOWN 在 prior_verdict_disposition 内
        # 失败关闭上抛，调用方不得吞；merge 重放 canonical 只能来自持久 remap）
        disposition = prior_verdict_disposition(prior, source_vid=str(record.get("id") or ""))
        if disposition["disposition"] == "drop_record":
            return {"action": "dropped", "rewriteVid": None}
        if disposition["disposition"] == "rewrite_to_canonical":
            return {"action": "kept_rewrite", "rewriteVid": str(disposition["vid"])}
        return {"action": "kept_as_new", "rewriteVid": None}
    # 新案或 OPEN 重复命中：记录扣留等裁决，来源行入账（幂等追加）
    manual_review_service.append_case_sources(
        str(response.get("reviewId") or ""),
        [
            {
                "executionId": str(execution_id or ""),
                "sourceBindingId": _source_binding_of_step(step_id),
                "sourceRecordId": str(record.get("sourceRecordId") or record.get("id") or ""),
                "sourceEventVersion": event_version,
                "evidence": {
                    "stage": stage,
                    "policyVersion": policy.get("version"),
                    "nameRuleVersion": policy.get("nameRuleVersion") or NAME_RULE_VERSION,
                    "propKeys": sorted((record.get("props") or {}).keys()),
                },
                "reason": f"gray:{stage}",
            }
        ],
    )
    return {"action": "withheld", "rewriteVid": None}


def _pending_write_descriptor_ok(client: Any, node_label: str, graph_space: str | None) -> bool:
    """pending 实体写入描述符门控（三条件，gray-gate-v2）。

    ① 平台目录有该实体 Schema（``kg_schema_definition``：name==nodeLabel、
    graph_space 匹配、kind=entity、未删、ddl_status=succeeded）；② ``DESCRIBE TAG``
    实际可读；③ 实际列含至少一个显示名列（``name_columns_in``）。任一不满足即
    该 pending 实体不可写（``skippedInvalidPending`` + 进 ``invalidEndpointVids``，
    引用它的边随后被过滤）——平台没有「合法写入口」的实体不允许借旁路上图。

    业务判定（invalid）只有两种：目录确无该实体、DESCRIBE 成功且列确不含
    显示名列。技术故障（目录查询失败 / 连接 / 超时 / DESCRIBE 异常 / 响应
    损坏=空列集）原样上抛（R1）——activity 失败、执行 FAILED、受影响来源
    水位不推进；不得把技术故障当作业务 invalid 计入水位照推。
    """
    from sqlalchemy import select as _sa_select

    from db_model.schema_management import GraphSchemaDefinition
    from infra.graph_db.config import TRSGraphSettings
    from infra.mysql import get_session_factory
    from service.entity_disambiguation import name_columns_in

    effective_space = str(graph_space or "") or TRSGraphSettings.from_env().space
    with get_session_factory()() as session:
        row = session.scalar(
            _sa_select(GraphSchemaDefinition.id).where(
                GraphSchemaDefinition.name == node_label,
                GraphSchemaDefinition.graph_space == effective_space,
                GraphSchemaDefinition.kind == "entity",
                GraphSchemaDefinition.is_deleted.is_(False),
                GraphSchemaDefinition.ddl_status == "succeeded",
            )
        )
    if row is None:
        return False
    described = client.execute_query(f"DESCRIBE TAG `{node_label}`")
    fields = {f for f in (r.get("Field") for r in described.records or []) if isinstance(f, str)}
    if not fields:
        # 目录 succeeded + DESCRIBE 成功但零列=响应损坏（DESCRIBE TAG 至少返回
        # 自身业务列），不是合法业务态——按技术故障上抛，不判 invalid
        raise RuntimeError("DESCRIBE TAG 响应无列（label 存在且 ddl=succeeded），按技术故障上抛")
    return bool(name_columns_in(fields))


def _apply_endpoint_overrides(
    records: list[dict[str, Any]],
    *,
    invalid_vids: list[str] | set[str],
    rewrite_map: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """边端点覆写（gray-gate-v2）：先应用裁决改写映射，再滤已知无效端点。

    ``rewrite_map``＝priorVerdict/resolve_pending_entities 给出的 canonical 改写
    （旧 vid → canonical vid）；``invalid_vids``＝未通过写入描述符门控、从未落图
    的 vid——引用它的边直接跳过（``skippedInvalidEndpoint`` 计数），不产生悬挂。
    """
    invalid = {str(v) for v in invalid_vids}
    rewrite = {str(k): str(v) for k, v in (rewrite_map or {}).items()}
    kept: list[dict[str, Any]] = []
    skipped = 0
    for record in records:
        frm, to = str(record.get("fromId")), str(record.get("toId"))
        if frm in rewrite or to in rewrite:
            record = {
                **record,
                "fromId": rewrite.get(frm, frm),
                "toId": rewrite.get(to, to),
            }
            frm, to = record["fromId"], record["toId"]
        if frm in invalid or to in invalid:
            skipped += 1
            continue
        kept.append(record)
    return kept, skipped


async def _assert_endpoints_exist(
    client: Any, records: list[dict[str, Any]], *, step_id: str, batch_idx: int, chunk_idx: int
) -> list[str]:
    """写边前端点存在性批量终判（gray-gate-v2）：MATCH id(v) IN [...] 分块查。

    park/覆写之后仍无 case 背书的端点必须真实存在于图，否则该边悬挂——全批
    失败关闭（``BLOCKED_ENDPOINT_UNKNOWN``），未知端点完整清单经 claim-check
    归档（S3 key + 64hex SHA-256，随错误 detail 上桌；payload 本体零标识符）。
    返回未知端点清单（空=全通过）。
    """
    endpoints = sorted(
        {
            str(vid)
            for record in records
            for vid in (record.get("fromId"), record.get("toId"))
            if vid
        }
    )
    if not endpoints:
        return []
    found: set[str] = set()

    def _probe() -> None:
        for start in range(0, len(endpoints), 64):
            part = endpoints[start : start + 64]
            quoted = ", ".join(json.dumps(v, ensure_ascii=False) for v in part)
            result = _with_watermark_retry(
                lambda quoted=quoted: client.execute_read(
                    f"MATCH (v) WHERE id(v) IN [{quoted}] RETURN id(v) AS vid"
                ),
                label=f"端点存在性终判 ×{len(part)}",
            )
            for row in getattr(result, "records", None) or []:
                vid = str(row.get("vid") or "")
                if vid:
                    found.add(vid)

    await asyncio.to_thread(_probe)
    unknown = [vid for vid in endpoints if vid not in found]
    if not unknown:
        return []
    return unknown


async def _claim_check_unknown_endpoints(
    unknown: list[str], *, step_id: str, batch_idx: int, chunk_idx: int
) -> dict[str, Any]:
    """未知端点完整清单 claim-check 归档（S3 key + SHA-256），零标识符入错误负载。"""
    from service.extract_payload_store import put_extract_payload_json

    key = await asyncio.to_thread(
        put_extract_payload_json,
        str(step_id or "write"),
        int(batch_idx or 0),
        f"unknown-endpoints-{int(chunk_idx or 0):02d}",
        {"unknownEndpoints": unknown},
    )
    digest = hashlib.sha256(json.dumps(unknown, ensure_ascii=False).encode()).hexdigest()
    return {"claimCheckKey": key, "sha256": digest, "unknownEndpointCount": len(unknown)}


def _open_entity_gray_case(
    *,
    graph: dict[str, Any],
    name_tag: str,
    display: str,
    record: dict[str, Any],
    scored: list[dict[str, Any]],
    outcome: dict[str, Any],
    step_id: str,
    source_table: str,
    info: Any,
    task_id: str,
    execution_id: Any,
    execution: dict[str, Any],
    stage: str = "resolve",
) -> None:
    """灰区实体建 T_LINK 案：消歧判定（resolve）与写前守卫（write）共用同一快照口径。

    失败上抛，由调用方决定 fail-open（记录照写，行为退回消歧 v1）。建案本身
    按 dedupe_key 幂等——活动重试同输入不重复建案。
    """
    from service.entity_disambiguation import GRAY_LOW, MERGE_THRESHOLD, TOP_K
    from service.manual_review_production import manual_review_service

    manual_review_service.create_direct_case(
        graph_space=graph.get("space"),
        task_id=task_id,
        execution_id=execution_id,
        step_id=step_id,
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
                "recallPolicy": "exact+milvus-dense-v1",
                "thresholds": {"merge": MERGE_THRESHOLD, "grayLow": GRAY_LOW},
            },
        },
        object_id=str(record.get("id")),
        object_name=display,
        node_label=name_tag,
        reason=(
            f"消歧得分 {outcome['score']:.2f} 落入灰区 "
            f"[{GRAY_LOW}, {MERGE_THRESHOLD})，需人工裁决是否并入已有实体（{stage}）"
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


@activity.defn
async def resolve_entity_batch(request: dict[str, Any]) -> dict[str, Any]:
    """消歧 v2（写前判定）：转换产出的实体在写图前先做多路召回 + 多证据评分。

    批内同名同样走评分（先到记录作为唯一候选）：≥0.85 才并（同批 upsert）、
    灰区开 T_LINK 案扣留、低分各自建点——同名不自动等于同一实体。
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
        decide,
        display_name,
        normalize_display_name,
        recall_candidates,
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
    if request.get("decisionPolicy") is not None:
        # gray-gate-v2 主流程：真实 decide=gray 才建 T_LINK；召回命中 merge 在
        # autoMergeEnabled=false 下统一 DEFERRED_MERGE_BLOCKED 失败关闭（B′）。
        # 失败关闭族在 activity 边界转 ApplicationError（不可重试、零标识符）
        try:
            return await _resolve_entity_batch_v2(request, records, graph, name_tag, source_table)
        except GrayGateFailClosedError as exc:
            raise _fail_closed_error(exc) from None
    batch_vids = {str(r.get("id")) for r in records}

    # 1) 批内同名合并走评分：后到记录与先到记录过 score_candidate/decide——
    #    ≥0.85 改写 vid 并入（同批 upsert）；灰区打标 _batchGray（步骤 3 统一
    #    开 T_LINK 案扣留）；<0.65 各自建点。不再无条件并：同批同显示名不等于
    #    同一实体，重名（张伟×N）必须交给评分器（2026-10-16 同字重名同批必并的洞）
    first_by_name: dict[str, dict[str, Any]] = {}
    deduped = 0
    for record in records:
        display = display_name(record.get("props"))
        key = normalize_display_name(display)
        if not key:
            continue
        first = first_by_name.setdefault(key, record)
        if first is record:
            continue
        first_display = display_name(first.get("props"))
        score, detail = score_candidate(
            display, record.get("props"), first_display, first.get("props")
        )
        scored = [
            {
                "vid": str(first.get("id")),
                "name": first_display,
                "score": round(score, 3),
                **detail,
            }
        ]
        outcome = decide(scored)
        if outcome["decision"] == "merge":
            record["id"] = str(first.get("id"))
            deduped += 1
        elif outcome["decision"] == "gray":
            record["_batchGray"] = {"scored": scored, "outcome": outcome}

    # 2) 多路召回（图库同名精确 ∪ Milvus 近邻；带候选完整属性供评分，
    #    近邻路 fail-open 不可用即退化为仅同名精确——properties() 失败降级为仅名称）
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

        # 多路召回整体下放线程（同步 HTTP 批量 LOOKUP / Milvus 检索；read_source_batch
        # 同款根因）；高水位走专用退避（本活动 STC 300s，max_attempts=10 ≈ 200s 内安全，缺陷㉘）
        def _recall() -> dict[str, list[dict[str, Any]]]:
            _with_watermark_retry(client.connect, label="消歧召回连接", max_attempts=10)
            return _with_watermark_retry(
                lambda: recall_candidates(
                    client, name_tag, list(by_name), space=graph.get("space")
                ),
                label="消歧多路召回",
                max_attempts=10,
            )

        try:
            existing = await asyncio.to_thread(_recall)
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭图客户端失败")

    info, task_id, execution_id, execution = _execution_context_for_cases()

    kept: list[dict[str, Any]] = []
    stats = {"merged": 0, "withheld": 0, "deduped": deduped, "new": 0}
    for record in records:
        display = display_name(record.get("props"))
        batch_gray = record.pop("_batchGray", None)
        if batch_gray is not None:
            # 批内同名灰区：与先到记录分数落入灰区，扣留开案人工裁决
            # （建案失败 fail-open 照写，与图库灰区同口径）
            try:
                _open_entity_gray_case(
                    graph=graph,
                    name_tag=name_tag,
                    display=display,
                    record=record,
                    scored=batch_gray["scored"],
                    outcome=batch_gray["outcome"],
                    step_id=request.get("stepId") or "align",
                    source_table=source_table,
                    info=info,
                    task_id=task_id,
                    execution_id=execution_id,
                    execution=execution,
                    stage="批内同名",
                )
                stats["withheld"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "批内同名灰区建案失败 vid=%s，记录按原样写图: %s", record.get("id"), exc
                )
                kept.append(record)
            continue
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
                _open_entity_gray_case(
                    graph=graph,
                    name_tag=name_tag,
                    display=display,
                    record=record,
                    scored=scored,
                    outcome=outcome,
                    step_id=request.get("stepId") or "align",
                    source_table=source_table,
                    info=info,
                    task_id=task_id,
                    execution_id=execution_id,
                    execution=execution,
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


async def _resolve_entity_batch_v2(
    request: dict[str, Any],
    records: list[dict[str, Any]],
    graph: dict[str, Any],
    name_tag: str,
    source_table: str,
) -> dict[str, Any]:
    """消歧 gray-gate-v2 主流程（写前判定，docs/人工审核专项方案复核_20261021.md）。

    与 v1 的分野（decisionPolicy 在 workflow 启动解析一次固化进输入，activity
    不读环境变量改策略）：

    - eligibility 前置过滤（``eligible_candidates``）：只做 vid≠自身 + 归一显示名
      相同两件事——异名近邻候选只作诊断（召回信封 routes），不进 decide；
    - 稳定事件身份前置裁决（R2）：重新评分与任何图写副作用之前，按逻辑
      ingress identity 查既有案——待裁决重复并入既有案（来源行入账），
      终态案按 priorVerdict 三态处置（reject 不因召回退化复活），应用失败/
      UNKNOWN 失败关闭；
    - 两阶段执行：先整批纯 decide，任一记录命中 merge → ``DEFERRED_MERGE_BLOCKED``
      失败关闭（B′：scoreDecision=merge 不是真实灰区，remap 未就绪不写实体/
      不放行边/不建案/不伪装，任何副作用前抛出；受影响来源水位不推进，执行
      FAILED，remap 方案 A 部署后手动重跑恢复）。批内同名 first-by-name 去重
      同口径：真实 merge 同样失败关闭（R3，不改写 id 继续）；
    - 真实 decide=gray 才建 T_LINK（逻辑 ingress identity dedupe + 证据 v2 +
      来源账本 + priorVerdict 三态处置）。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from service.entity_disambiguation import (
        decide,
        display_name,
        eligible_candidates,
        normalize_display_name,
        recall_candidates_envelope,
        score_candidate,
    )
    from service.gray_gate import DeferredMergeBlockedError, UnknownPolicyVersionError

    policy = dict(require_known_policy(request.get("decisionPolicy")))
    if policy.get("autoMergeEnabled") is not False:
        # v2 契约 autoMergeEnabled 恒 false（true=v3 auto-merge，未实施另行审批）
        raise UnknownPolicyVersionError(
            {"field": "autoMergeEnabled", "received": policy.get("autoMergeEnabled")}
        )
    batch_vids = {str(r.get("id")) for r in records}

    # 0) 稳定事件身份前置裁决（R2）：既有案/既有裁决处置先于重新评分与任何
    #    副作用（批内去重改写、召回、建案、放行）
    prior_handled: list[tuple[dict[str, Any], dict[str, Any]]] = []
    remaining_records: list[dict[str, Any]] = []
    for record in records:
        prior = _prior_ingress_disposition(
            step_id=str(request.get("stepId") or "align"),
            record=record,
            graph_space=graph.get("space"),
            name_tag=name_tag,
            policy=policy,
            stage="resolve",
        )
        if prior is None:
            remaining_records.append(record)
        else:
            prior_handled.append((record, prior))
    records = remaining_records

    # 1) 批内同名 first-by-name 去重：真实 merge 与阶段 3 同口径失败关闭（R3）；
    #    灰区打标 _batchGray（阶段 3 建案）
    first_by_name: dict[str, dict[str, Any]] = {}
    deduped = 0
    for record in records:
        display = display_name(record.get("props"))
        key = normalize_display_name(display)
        if not key:
            continue
        first = first_by_name.setdefault(key, record)
        if first is record:
            continue
        first_display = display_name(first.get("props"))
        eligible, _ = eligible_candidates(
            display,
            str(record.get("id")),
            [{"vid": str(first.get("id")), "name": first_display, "props": first.get("props")}],
            graph_space=graph.get("space"),
            node_label=name_tag,
        )
        if not eligible:
            continue
        score, detail = score_candidate(
            display, record.get("props"), first_display, first.get("props")
        )
        scored = [
            {
                "vid": str(first.get("id")),
                "name": first_display,
                "score": round(score, 3),
                **detail,
            }
        ]
        outcome = decide(scored)
        if outcome["decision"] == "merge":
            # R3：批内同名真实 merge 与阶段 3 同口径统一失败关闭（B′）——不
            # 改写 id 继续写图（等于在无 remap 的情况下执行合并）、不伪装状态；
            # 受影响来源水位不推进，remap 方案 A 落地后手动重跑恢复
            raise DeferredMergeBlockedError(
                {
                    "stage": "resolve-batch-dedupe",
                    "score": round(float(outcome["score"]), 3),
                    "autoMergeEnabled": False,
                    "policyVersion": policy.get("version"),
                }
            )
        if outcome["decision"] == "gray":
            record["_batchGray"] = {"scored": scored, "outcome": outcome}

    # 2) 多路召回（信封五态：routes 状态进 extra_snapshot，不遮蔽判定分支）
    by_name: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        display = display_name(record.get("props"))
        if display:
            by_name.setdefault(display, []).append(record)
    envelope: dict[str, Any] = {"candidates": {}, "routes": {}}
    if by_name:
        settings = TRSGraphSettings.from_env()
        if graph.get("space"):
            settings.space = graph["space"]
        client = TRSGraphClient(settings)

        def _recall() -> dict[str, Any]:
            _with_watermark_retry(client.connect, label="消歧召回连接", max_attempts=10)
            return _with_watermark_retry(
                lambda: recall_candidates_envelope(
                    client, name_tag, list(by_name), space=graph.get("space")
                ),
                label="消歧多路召回",
                max_attempts=10,
            )

        try:
            envelope = await asyncio.to_thread(_recall)
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭图客户端失败")
    existing = envelope.get("candidates") or {}
    routes = envelope.get("routes") or {}

    # 3) 纯 decide 阶段：全部记录先出判定（无副作用）——merge 在任何建案/放行
    #    前统一失败关闭，防部分扣留部分并入的伪装态
    decisions: list[tuple[dict[str, Any], str, dict[str, Any], list[dict[str, Any]], str]] = []
    for record in records:
        display = display_name(record.get("props"))
        batch_gray = record.get("_batchGray")
        if batch_gray is not None:
            decisions.append(
                (record, "gray", batch_gray["outcome"], batch_gray["scored"], "批内同名")
            )
            continue
        eligible, _ = eligible_candidates(
            display,
            str(record.get("id")),
            existing.get(display, []),
            graph_space=graph.get("space"),
            node_label=name_tag,
        )
        scored = []
        for cand in eligible:
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
            raise DeferredMergeBlockedError(
                {
                    "stage": "resolve",
                    "score": round(float(outcome["score"]), 3),
                    "autoMergeEnabled": False,
                    "policyVersion": policy.get("version"),
                }
            )
        decisions.append((record, outcome["decision"], outcome, scored, "resolve"))

    # 4) 副作用阶段：gray → v2 建案（逻辑键/证据 v2/来源账本/priorVerdict 处置）
    info, task_id, execution_id, execution = _execution_context_for_cases()
    kept: list[dict[str, Any]] = []
    stats: dict[str, int] = {
        "merged": 0,
        "withheld": 0,
        "deduped": deduped,
        "new": 0,
        "priorDropped": 0,
        "priorRewritten": 0,
        "keptAsNew": 0,
    }
    for record, decision, outcome, scored, stage in decisions:
        record.pop("_batchGray", None)
        if decision != "gray":
            stats["new"] += 1
            kept.append(record)
            continue
        try:
            result = _open_entity_gray_case_v2(
                graph=graph,
                name_tag=name_tag,
                display=display_name(record.get("props")),
                record=record,
                scored=scored,
                outcome=outcome,
                step_id=request.get("stepId") or "align",
                source_table=source_table,
                info=info,
                task_id=task_id,
                execution_id=execution_id,
                execution=execution,
                policy=policy,
                routes=routes,
                stage=stage,
            )
        except GrayGateFailClosedError:
            # fail-open 例外：失败关闭族不被吞（fail-open 只兜普通建案故障）
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("灰区消歧建案失败 vid=%s，记录按原样写图: %s", record.get("id"), exc)
            stats["new"] += 1
            kept.append(record)
            continue
        action = result["action"]
        if action == "withheld":
            stats["withheld"] += 1
        elif action == "dropped":
            stats["priorDropped"] += 1
        elif action == "kept_rewrite":
            kept.append({**record, "id": str(result["rewriteVid"])})
            stats["priorRewritten"] += 1
        else:  # kept_as_new：终态 create 重放，按预留 vid 原样写
            kept.append(record)
            stats["keptAsNew"] += 1
    # 前置裁决（R2）的记录折入统计与放行清单（与建案路径三态同口径）
    for record, prior in prior_handled:
        action = prior["action"]
        if action == "withheld":
            stats["withheld"] += 1
        elif action == "dropped":
            stats["priorDropped"] += 1
        elif action == "kept_rewrite":
            kept.append({**record, "id": str(prior["rewriteVid"])})
            stats["priorRewritten"] += 1
        else:  # kept_as_new：终态 create 重放，按预留 vid 原样写
            kept.append(record)
            stats["keptAsNew"] += 1
    if request.get("recordsKey"):
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
async def resolve_pending_entities(request: dict[str, Any]) -> dict[str, Any]:
    """pending 旁路真实灰区门控（gray-gate-v2 双流，pendingMode=resolve）。

    取代 v1「挂起实体一律强制 T_LINK」（取消测试脚本强制送审）：挂起实体按
    同一套 eligibility + 评分 decide——真实 gray 才建 T_LINK（逻辑键/证据 v2/
    来源账本/priorVerdict 三态）；重新评分前先按稳定事件身份前置查既有案
    （R2：reject 不因召回退化复活、待裁决重复并入既有案、应用失败/UNKNOWN
    失败关闭）；new 直接写图（写入描述符门控三条件：目录
    Schema 存在且 ddl 成功 + DESCRIBE TAG 可读 + 实际列含显示名列，不满足=
    ``skippedInvalidPending`` + 进 ``invalidEndpointVids``，引用它的边随后被
    write_records 过滤；技术故障上抛、水位不推进）；merge 在 autoMergeEnabled=false
    下统一 ``DEFERRED_MERGE_BLOCKED`` 失败关闭（B′）。批内两阶段：先整批纯
    decide，任一 deferred 在任何副作用（写图/建案）前抛出。返回
    ``{written, grayCases, skippedInvalidPending, invalidEndpointVids,
    rewriteMap}`` 供 workflow 聚合传给写边请求。失败关闭族在边界转
    ApplicationError（不可重试、零标识符）。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from service.entity_disambiguation import (
        decide,
        eligible_candidates,
        recall_candidates_envelope,
        score_candidate,
    )
    from service.gray_gate import DeferredMergeBlockedError, UnknownPolicyVersionError

    try:
        policy = dict(require_known_policy(request.get("decisionPolicy")))
        if policy.get("autoMergeEnabled") is not False:
            raise UnknownPolicyVersionError(
                {"field": "autoMergeEnabled", "received": policy.get("autoMergeEnabled")}
            )
        graph = request.get("graph") or {}
        step_id = str(request.get("stepId") or "pending")
        source_table = str(request.get("sourceTable") or "")
        pending_in = request.get("pending")
        if pending_in is None and request.get("pendingKey"):
            from service.extract_payload_store import load_extract_payload_json

            pending_in = await asyncio.to_thread(load_extract_payload_json, request["pendingKey"])
        items = [i for i in (pending_in or []) if isinstance(i, dict)]
        # 关系项已废弃（歧义即端点实体歧义）：丢弃并告警（与 v1 改道口径一致）
        entities = []
        for item in items:
            if str(item.get("kind") or "entity") != "entity":
                logger.warning(
                    "pendingReview 关系项已废弃（歧义改挂实体，走 T_LINK），丢弃: step=%s",
                    step_id,
                )
                continue
            entities.append(item)

        info, task_id, execution_id, execution = _execution_context_for_cases()
        invalid_endpoint_vids: list[str] = []
        rewrite_map: dict[str, str] = {}
        written = 0
        gray_cases = 0
        skipped_invalid = 0
        if not entities:
            return {
                "written": 0,
                "grayCases": 0,
                "skippedInvalidPending": 0,
                "invalidEndpointVids": [],
                "rewriteMap": {},
            }

        settings = TRSGraphSettings.from_env()
        if graph.get("space"):
            settings.space = graph["space"]
        client = TRSGraphClient(settings)

        # 写入描述符门控（三条件）按 nodeLabel 结论一致，一次判定整组复用
        gate_by_label: dict[str, bool] = {}

        def _gate(label: str) -> bool:
            if label not in gate_by_label:
                gate_by_label[label] = _pending_write_descriptor_ok(
                    client, label, graph.get("space")
                )
                if not gate_by_label[label]:
                    logger.warning(
                        "pending 实体写入描述符门控未通过 label=%s（目录/DESCRIBE/显示名列）",
                        label,
                    )
            return gate_by_label[label]

        try:
            _with_watermark_retry(client.connect, label="pending 消歧连接", max_attempts=10)

            # 召回按 nodeLabel 分组（tag 限定，同名跨标签不串），组内显示名批量查
            by_label: dict[str, dict[str, list[dict[str, Any]]]] = {}
            for item in entities:
                candidate = item.get("candidate") or {}
                display = str(item.get("objectName") or candidate.get("name") or "").strip()
                node_label = str(item.get("nodeLabel") or "").strip()
                if display and node_label:
                    by_label.setdefault(node_label, {}).setdefault(display, []).append(item)

            def _recall_label(node_label: str, names: list[str]) -> dict[str, Any]:
                return _with_watermark_retry(
                    lambda: recall_candidates_envelope(
                        client, node_label, names, space=graph.get("space")
                    ),
                    label=f"pending 多路召回 {node_label}",
                    max_attempts=10,
                )

            recall_by_label: dict[str, dict[str, Any]] = {}
            for node_label, name_items in by_label.items():
                recall_by_label[node_label] = await asyncio.to_thread(
                    _recall_label, node_label, list(name_items)
                )
            routes_by_label = {
                label: env.get("routes") or {} for label, env in recall_by_label.items()
            }

            # 阶段一：前置裁决（R2）+ 门控标记 + 纯 decide（merge → 任何副作用前
            # 失败关闭）。decisions: (item, display, decision, outcome, scored)；
            # prior_items: (item, node_label, record, prior处置)
            decisions: list[
                tuple[dict[str, Any], str, str, dict[str, Any], list[dict[str, Any]]]
            ] = []
            prior_items: list[tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]] = []
            for item in entities:
                candidate = item.get("candidate") or {}
                display = str(item.get("objectName") or candidate.get("name") or "").strip()
                vid = str(item.get("objectId") or "").strip()
                node_label = str(item.get("nodeLabel") or "").strip()
                if not (display and vid and node_label):
                    # 身份字段缺失：UNSTABLE_SOURCE_IDENTITY 失败关闭（不猜测写图）
                    from service.gray_gate import UnstableSourceIdentityError

                    raise UnstableSourceIdentityError({"stage": "pending"})
                record = {
                    "id": vid,
                    "props": {**(candidate.get("props") or {}), "name": display},
                    "sourceTable": item.get("sourceTable") or source_table,
                    "sourceRecordId": item.get("sourceRecordId"),
                    # 声明事件版本（R4-b）：业务版本变化=新事件，摄取时间变化=同事件
                    "sourceEventVersion": item.get("sourceEventVersion"),
                }
                # 稳定事件身份前置（R2）：既有案/既有裁决先于重新评分与任何写副作用
                prior = _prior_ingress_disposition(
                    step_id=step_id,
                    record=record,
                    graph_space=graph.get("space"),
                    name_tag=node_label,
                    policy=policy,
                    stage="pending",
                )
                if prior is not None:
                    prior_items.append((item, node_label, record, prior))
                    continue
                if not _gate(node_label):
                    continue  # 阶段二计入 skippedInvalidPending/invalidEndpointVids
                incoming_props = dict(candidate.get("props") or {})
                incoming_props.setdefault("name", display)
                existing = (recall_by_label.get(node_label) or {}).get("candidates") or {}
                eligible, _ = eligible_candidates(
                    display,
                    vid,
                    existing.get(display, []),
                    graph_space=graph.get("space"),
                    node_label=node_label,
                )
                scored = []
                for cand in eligible:
                    score, detail = score_candidate(
                        display, incoming_props, cand["name"], cand.get("props")
                    )
                    scored.append(
                        {
                            "vid": cand["vid"],
                            "name": cand["name"],
                            "score": round(score, 3),
                            **detail,
                        }
                    )
                outcome = decide(scored)
                if outcome["decision"] == "merge":
                    raise DeferredMergeBlockedError(
                        {
                            "stage": "pending",
                            "score": round(float(outcome["score"]), 3),
                            "autoMergeEnabled": False,
                            "policyVersion": policy.get("version"),
                        }
                    )
                decisions.append((item, display, outcome["decision"], outcome, scored))

            # 阶段二：副作用（写图 / 建案 / 处置）
            for item, display, decision, outcome, scored in decisions:
                candidate = item.get("candidate") or {}
                vid = str(item.get("objectId") or "").strip()
                node_label = str(item.get("nodeLabel") or "").strip()
                record = {
                    "id": vid,
                    "props": {**(candidate.get("props") or {}), "name": display},
                    "sourceTable": item.get("sourceTable") or source_table,
                    "sourceRecordId": item.get("sourceRecordId"),
                    # 声明事件版本（R4-b）：与阶段一同键，查案/建案材料一致
                    "sourceEventVersion": item.get("sourceEventVersion"),
                }
                if decision != "gray":
                    # decide=new：门控已过，直接写图（列级合并防覆盖清列）
                    await asyncio.to_thread(
                        _write_pending_vertex,
                        client,
                        node_label,
                        vid,
                        record["props"],
                        item.get("sourceTable") or source_table,
                    )
                    written += 1
                    continue
                result = _open_entity_gray_case_v2(
                    graph=graph,
                    name_tag=node_label,
                    display=display,
                    record=record,
                    scored=scored,
                    outcome=outcome,
                    step_id=step_id,
                    source_table=item.get("sourceTable") or source_table,
                    info=info,
                    task_id=task_id,
                    execution_id=execution_id,
                    execution=execution,
                    policy=policy,
                    routes=routes_by_label.get(node_label) or {},
                    stage="pending",
                )
                action = result["action"]
                if action == "withheld":
                    gray_cases += 1
                elif action == "dropped":
                    # 终态 reject 重放：实体不写，边由 park 丢弃；vid 无效引用
                    invalid_endpoint_vids.append(vid)
                elif action == "kept_rewrite":
                    rewrite_map[vid] = str(result["rewriteVid"])
                else:  # kept_as_new：终态 create 重放，按预留 vid 补写实体
                    await asyncio.to_thread(
                        _write_pending_vertex,
                        client,
                        node_label,
                        vid,
                        record["props"],
                        item.get("sourceTable") or source_table,
                    )
                    written += 1

            # 前置裁决（R2）的处置：与建案路径三态同口径
            for _item, node_label, record, prior in prior_items:
                vid = str(record["id"])
                action = prior["action"]
                if action == "withheld":
                    # 既有待裁决案重复命中：记录继续扣留等裁决
                    gray_cases += 1
                elif action == "dropped":
                    # 终态 reject 重放：实体不写，边由 park 丢弃；vid 无效引用
                    invalid_endpoint_vids.append(vid)
                elif action == "kept_rewrite":
                    rewrite_map[vid] = str(prior["rewriteVid"])
                else:  # kept_as_new：终态 create 重放，按预留 vid 幂等补写
                    await asyncio.to_thread(
                        _write_pending_vertex,
                        client,
                        node_label,
                        vid,
                        record["props"],
                        record["sourceTable"],
                    )
                    written += 1

            # 门控未通过的项：不写图，vid 进无效端点清单（边过滤）
            gated_vids = {
                str(item.get("objectId") or "").strip()
                for item in entities
                if str(item.get("nodeLabel") or "") and not _gate(str(item.get("nodeLabel") or ""))
            }
            skipped_invalid = len(gated_vids)
            invalid_endpoint_vids.extend(sorted(gated_vids - set(invalid_endpoint_vids)))
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭 pending 消歧图客户端失败")
        return {
            "written": written,
            "grayCases": gray_cases,
            "skippedInvalidPending": skipped_invalid,
            "invalidEndpointVids": sorted(set(invalid_endpoint_vids)),
            "rewriteMap": rewrite_map,
        }
    except GrayGateFailClosedError as exc:
        raise _fail_closed_error(exc) from None


def _write_pending_vertex(
    client: Any, node_label: str, vid: str, props: dict[str, Any], source_table: str
) -> None:
    """pending 实体落图（同步，调用方包 to_thread）：列级合并防整标签覆盖清列。

    FETCH 图上旧值（不存在=空）→ 未携带列保留 / 携带列覆盖 → 单行
    ``INSERT VERTEX``；列集按 DESCRIBE 实际列过滤（未知列剔除），溯源审计列
    存在才补（与平台写图口径一致）。写失败上抛（activity 重试，幂等重写）。
    """
    import time as _time

    described = client.execute_query(f"DESCRIBE TAG `{node_label}`")
    col_types: dict[str, str] = {}
    for row in described.records or []:
        field = row.get("Field")
        if isinstance(field, str):
            col_types[field] = str(row.get("Type") or "").lower()
    if not col_types:
        raise RuntimeError(f"DESCRIBE TAG {node_label} 无列，pending 实体不可写")
    fields = set(col_types)
    existing = _fetch_vertex_props(client, node_label, vid)
    merged = dict(existing)
    merged.update({k: v for k, v in props.items() if k in fields})
    now_str = _time.strftime("%Y-%m-%d %H:%M:%S")
    for key, default in (
        ("source_table", source_table or "platform"),
        ("create_time", now_str),
        ("update_time", now_str),
    ):
        if key in fields:
            merged.setdefault(key, default)
    if "update_time" in fields:
        merged["update_time"] = now_str
    merged = {k: v for k, v in merged.items() if k in fields and v is not None}
    cols = ", ".join(f"`{k}`" for k in merged)
    values = ", ".join(
        ngql_value_for_column(v, col_types.get(k, ""), nullable=True) for k, v in merged.items()
    )
    client.execute_write(
        f"INSERT VERTEX `{node_label}`({cols}) VALUES {json.dumps(vid, ensure_ascii=False)}:({values})"
    )


def _fetch_vertex_props(client: Any, node_label: str, vid: str) -> dict[str, Any]:
    """FETCH 单顶点属性（不存在返回空 dict；map 序列化字符串兜住）。"""
    quoted = json.dumps(vid, ensure_ascii=False)
    result = client.execute_read(
        f"FETCH PROP ON `{node_label}` {quoted} "
        "YIELD id(vertex) AS vid, properties(vertex) AS props"
    )
    for row in getattr(result, "records", None) or []:
        if str(row.get("vid") or "") != vid:
            continue
        value = row.get("props")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                value = {}
        return dict(value) if isinstance(value, dict) else {}
    return {}


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

    # 同名碰撞探测整体下放线程（同步 HTTP MATCH；read_source_batch 同款根因）；
    # 名单分块（同 recall_same_name 的 _RECALL_NAME_CHUNK 口径——批次 2000 的
    # 单条 IN 巨查会撑爆共享 graphd，缺陷㉘）；高水位走专用退避
    # （STC 120s，max_attempts=4 ≈ 80s 内安全）
    def _probe_existing() -> dict[str, list[str]]:
        _with_watermark_retry(client.connect, label="碰撞探测连接", max_attempts=4)
        all_names = list(by_name)
        found: dict[str, list[str]] = {}
        for start in range(0, len(all_names), 150):
            names = all_names[start : start + 150]
            name_list = ",".join(json.dumps(n, ensure_ascii=False) for n in names)
            # 名称列必须 tag 限定（同 recall_same_name 的口径）：空间里多个 tag
            # 都有 name 属性时（Person/Organization…），未限定的 v.name 被引擎
            # 解析成 NULL，WHERE 静默不命中——同名碰撞永远查空，碰撞 case 建不出来。
            ngql = (
                f"MATCH (v:`{name_tag}`) WHERE v.`{name_tag}`.`name` IN [{name_list}] "
                f"RETURN id(v) AS vid, v.`{name_tag}`.`name` AS nm LIMIT 200"
            )
            result = _with_watermark_retry(
                lambda ngql=ngql: client.execute_read(ngql),
                label="同名碰撞探测",
                max_attempts=4,
            )
            for rec in result.records or []:
                nm = str(rec.get("nm") or "")
                vid = str(rec.get("vid") or "")
                if nm and vid:
                    found.setdefault(nm, []).append(vid)
        return found

    try:
        existing = await asyncio.to_thread(_probe_existing)
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
                graph_space=graph.get("space"),
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

    缺 ``recordId`` 的条目建不了 case（审核展示与失败重跑都按记录 id 定位），
    如实计数为 ``skippedNoRecordId`` 上抛——执行消息/任务日志据此说明「未入
    审核队列」，不再一律宣称已转人工审核（2026-10-09 用例：脚本找错列名致
    88 条失败全无 id，队列空但文案谎报已转审）。
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
    skipped_no_id = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        record_id = str(item.get("recordId") or "")
        if not record_id:
            skipped_no_id += 1
            continue
        source_table = item.get("sourceTable") or ""
        error = str(item.get("error") or "")[:1000]
        try:
            manual_review_service.create_direct_case(
                graph_space=request.get("graphSpace"),
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
    if skipped_no_id:
        logger.warning(
            "%d 条失败记录缺 recordId 未建审核 case（脚本 failures 须携带记录主键）",
            skipped_no_id,
        )
    return {"recorded": recorded, "skippedNoRecordId": skipped_no_id}


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
async def revert_rerun_failure_cases(request: dict[str, Any]) -> dict[str, Any]:
    """重跑执行异常中止时把 RERUNNING case 回滚 OPEN（不滞留，可再次点重跑）。

    ``resolve_failure_cases`` 只在 workflow 正常走到结尾时调用；重跑执行中途
    崩溃（批次 activity 重试耗尽 / 写图异常）时 case 已被 API 侧 ``mark_extract_rerun``
    标成 RERUNING，无人回滚就永远滞留——审核队列看不到也点不了重跑。
    """
    from service.manual_review_production import manual_review_service

    reverted = manual_review_service.revert_extract_rerun(
        request.get("rerunCaseIds") or [],
        reason=str(request.get("reason") or "重跑执行失败"),
    )
    return {"reverted": reverted}


@activity.defn
async def build_entity_index(request: dict[str, Any]) -> dict[str, Any]:
    """实体 Milvus 混合检索索引：随环批级增量（冻结 BM25 词表）或整空间全量重建。

    ``vidsKeys`` 存在 → 增量路径：下载 write_records 留档的 vid 清单（S3
    claim-check），合并去重后 ``upsert_entities`` 定向 upsert（代价 ∝ 变更量，
    替代随环全量重建——后者耗时 > activity 超时会自锁整链 FAILED）。守卫不
    满足（重建在跑 / 空间索引未建）按计划内跳过返回；真实组件故障上抛重试。
    ``vidsKeys`` 缺失 → 旧全量 reindex 路径（在飞旧 run 重放 / 手动触发专属，
    新 run 的 workflow 已不产生该形状）。
    """
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    from infra.workflow_mysql import get_workflow_engine
    from service.entity_search import EntitySearchService, invalidate_entity_caches_sync

    space = request.get("space")
    entity_types = request.get("entityTypes") or []
    vids_keys = request.get("vidsKeys")

    def _run() -> dict[str, Any]:
        # BM25 状态表（kg_entity_search_state）在控制库：与 handler 的
        # get_workflow_session 同源，走默认业务库会报 Table doesn't exist
        from sqlalchemy.orm import Session as OrmSession

        with OrmSession(get_workflow_engine()) as session:
            service = EntitySearchService(session)
            if vids_keys is None:
                return service.reindex(space=space, entity_types=entity_types)
            from service.extract_payload_store import load_extract_payload_json

            # 跨来源/跨步/跨批合并去重（同 vid 首个 label 生效；重触发重写
            # 幂等）。工件下载失败上抛 → activity 重试（严格口径）
            items: list[dict[str, Any]] = []
            seen: set[str] = set()
            for key in vids_keys:
                payload = load_extract_payload_json(key)
                if not isinstance(payload, dict):
                    continue
                label = str(payload.get("label") or "")
                for vid in payload.get("vids") or []:
                    vid = str(vid)
                    if vid and vid not in seen:
                        seen.add(vid)
                        items.append({"vid": vid, "label": label})
            result = service.upsert_entities(space=space, items=items)
            result["vidManifests"] = len(vids_keys)
            return result

    result = await asyncio.to_thread(_run)
    # 增量生效后失效检索缓存（L1 进程 + L2 Redis，同 T_LINK 裁决联动）；
    # 全量 reindex 路径服务内已自清
    if isinstance(result, dict) and result.get("mode") == "incremental":
        invalidate_entity_caches_sync()
    return {"reindexed": result}


@activity.defn
async def refresh_graph_stats(request: dict[str, Any]) -> dict[str, Any]:
    """触发图库 SUBMIT JOB STATS，让平台总览 SHOW STATS 反映本次写图（00918）。

    SHOW STATS 只返回最近一次 stats job 的预计算结果——INSERT VERTEX 写图后
    不自动刷新，不触发则总览实体/关系总量停在旧值。异步 job 提交即返回；
    另一个 stats job 已在跑等异常只告警降级（下次抽取会再触发），不拖垮抽取。
    """
    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    settings = TRSGraphSettings.from_env()
    if request.get("space"):
        settings.space = str(request["space"])
    client = TRSGraphClient(settings)
    try:
        client.connect()
        result = client.execute_write("SUBMIT JOB STATS")
        job_id = None
        for rec in result.records or []:
            if isinstance(rec, dict) and rec.get("New Job Id") is not None:
                job_id = rec.get("New Job Id")
                break
        return {"submitted": True, "jobId": job_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "SUBMIT JOB STATS 提交失败 space=%s（总览统计将滞后至下次触发）: %s",
            settings.space,
            exc,
        )
        return {"submitted": False, "error": str(exc)[:200]}
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            logger.exception("关闭图客户端失败")


async def _register_scheduled_run(request: dict[str, Any]) -> None:
    """payload 带 _scheduleId 时（周期 Schedule 触发），先落 execution/task 行。"""
    schedule_id = (request.get("payload") or {}).get("_scheduleId")
    if not schedule_id:
        return
    info = workflow.info()
    await _execute_activity(
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
        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
    )


def _is_rerun_request(request: dict[str, Any]) -> bool:
    """手动 RERUN 载荷识别（rerun_failed_records 构造，schema_extraction.py）。

    带 ``rerunCaseIds`` / ``triggerSource=RERUN`` 且无 ``_scheduleId``——这类执行
    不经 Schedule 直发，控制库执行行此前无人收尾（MR-SYNC：审核队列把已成功
    重跑误报成 RERUN_FAILED 的根因之一）。extract 类定义 workflow 入参为扁平
    payload（temporal_runtime 对 sourceKind=extract 不包装），保险起见两种
    层级都认（与 _finalize_scheduled_run 读 _scheduleId 同口径）。
    """
    payload = request.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    for carrier in (request, payload):
        if carrier.get("rerunCaseIds") or carrier.get("triggerSource") == "RERUN":
            return True
    return False


async def _finalize_scheduled_run(
    request: dict[str, Any], *, result: Any = None, error: str | None = None
) -> None:
    """与 ``_register_scheduled_run`` 对称的收尾：workflow 自报终态回写控制库。

    在 payload 带 ``_scheduleId``（周期调度）**或为手动 RERUN 载荷**时生效；
    best-effort（失败不阻断 workflow 终态），CANCELLED 场景 workflow 无法收尾，
    由 ``service.execution_reconciler`` 对账兜底。
    """
    schedule_id = request.get("_scheduleId") or (request.get("payload") or {}).get("_scheduleId")
    if not schedule_id and not _is_rerun_request(request):
        return
    info = workflow.info()
    try:
        await _execute_activity(
            finalize_scheduled_execution,
            {"runId": info.run_id, "result": result, "error": error},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=ACTIVITY_RETRY_POLICY,
            schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
        )
    except ActivityError:
        workflow.logger.warning("调度执行收尾回写失败: %s", info.run_id)


@workflow.defn(name="kg.custom.configurable")
class ConfigurableWorkflow:
    """declarative 定义的记账工作流：按定义 steps 逐步回显 payload（占位语义，C1 范畴）。

    D3 删掉 execute_kg_step 空壳 activity 后改为 workflow 内直接构造记账结果——
    真实数据处理一律走 kg.schema.extract。
    """

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        await _register_scheduled_run(request)
        try:
            definition = await _execute_activity(
                load_workflow_definition,
                request["definitionId"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
                schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
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
            result = {"definitionId": definition["id"], "status": "completed", "steps": results}
        except Exception as exc:
            await _finalize_scheduled_run(request, error=str(exc)[:500])
            raise
        await _finalize_scheduled_run(request, result=result)
        return result


@activity.defn
async def resolve_execution_llm(request: dict[str, Any]) -> dict[str, Any]:
    """Resolve once per run; Temporal records only IDs and non-secret env model metadata."""
    from fastapi import HTTPException

    try:
        return _resolve_execution_llm(request)
    except HTTPException as exc:
        raise ApplicationError(
            str(exc.detail), type="ModelSelectionDenied", non_retryable=True
        ) from exc


def _resolve_execution_llm(request: dict[str, Any]) -> dict[str, Any]:
    from infra.mysql import session_scope
    from service.business_access_control import rbac_enabled
    from service.llm_config import DEFAULT_BASE_URL, DEFAULT_MODEL
    from service.llm_defaults import resolve_default_config
    from service.workflow_jobs import _job_business, authorize_background_execution

    actor = authorize_background_execution(request) if rbac_enabled() else None
    business_id = _job_business(actor, request) if rbac_enabled() else None
    if rbac_enabled() and request.get("clientId") and request["clientId"] != business_id:
        raise ApplicationError("任务业务与目标图空间不一致", non_retryable=True)
    with session_scope() as session:
        row = resolve_default_config(
            session,
            business_id=business_id,
            config_id=request.get("llm_config_id") or request.get("llmConfigId"),
        )
        result = {
            "llm_config_id": row.id if row else None,
            "_llm_business_id": business_id,
            "_llm_env": None,
        }
    if row is None and (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip():
        result["_llm_env"] = {
            "base_url": os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
            "model": os.getenv("LLM_MODEL", DEFAULT_MODEL),
        }
    return result


_EXTRACT_SELECTOR_KEYS = (
    "mysql_datasource_id",
    "mysql_database",
    "milvus_config_id",
    "milvus_database",
    "graph_space",
    "llm_config_id",
    "_llm_business_id",
    "_llm_env",
    "embedding_config_id",
    "since",
)


@workflow.defn(name="kg.schema.extract")
class SchemaExtractWorkflow:
    """Schema 平台喂数抽取：分批读源表 → 脚本转换（只出 JSON）→ 平台写图/消歧/索引。

    - 来源间 ``asyncio.gather`` 并行；来源内 1 reader（串行读推进游标）+ N worker
      （转换→写图→冲突检测）经 ``asyncio.Queue(maxsize=N)`` 背压并发——十万级数据
      也不会一次进内存/一次跑完。
    - 脚本用 ``@step`` 装饰器声明转换步（唯一形态，单步 ``transform`` / ``STEPS``
      清单已删除）：批内步序串行，每步一次 ``execute_transform`` activity（第 k 步
      失败由 Temporal 只重试第 k 步）；第 N>1 步 payload 为 ``{"input": 上一步输出,
      ...}``，``ctx.prev_outputs`` 可读已完成各步输出；任意一步出 entities/edges
      即在该步后写图，failures 跨步聚合。水位仍是来源级整链推进，不做 per-step 水位。
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
        # 步间暂停（pause_extraction/resume_extraction 信号）：当前步/环正常
        # 结束后，下一步开始前挂起在 workflow.condition 上——Temporal 无原生
        # pause，这是官方推荐的 signal + condition 模式；重放安全（信号在
        # 事件历史里有序记录）
        self._paused = False

    @workflow.signal
    def pause_extraction(self) -> None:
        self._paused = True

    @workflow.signal
    def resume_extraction(self) -> None:
        self._paused = False

    async def _wait_if_paused(self) -> None:
        """暂停挂起点：在每个转换步/环开始前调用（步内不打断，activity 无法中断）。"""
        if self._paused:
            workflow.logger.info("任务已暂停，挂起在下一步开始前")
        await workflow.wait_condition(lambda: not self._paused)

    async def _report_script_run(self, schema_id: str, *, ok: bool, error: str | None) -> None:
        """收尾回写脚本健康信号（best-effort，失败不影响主流程状态）。"""
        try:
            await _execute_activity(
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
                schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
            )
        except ActivityError:
            workflow.logger.warning("回写脚本运行状态失败: %s", schema_id)

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        # 周期 Schedule 触发的执行：收尾时自报终态回写控制库（与开头的
        # register_scheduled_execution 落行对称），否则没人查看详情就永远 RUNNING。
        # rerun-finalize-1020：手动 RERUN 执行同样收尾——执行行滞留 RUNNING 会让
        # 审核队列把已成功重跑误报成 RERUN_FAILED（MR-SYNC）。patched 守卫保证
        # 升级时已在飞的旧 RERUN workflow 重放走旧分支、不向旧历史追加新命令；
        # 残余（升级窗口在飞的旧 RERUN）由 get_execution 惰性刷新/reconciler 对账
        # 兜底，不据此宣称旧历史重放零风险（未做真实旧历史回放验证）。
        schedule_id = request.get("_scheduleId") or (request.get("payload") or {}).get(
            "_scheduleId"
        )
        finalize = bool(schedule_id) or (
            workflow.patched("rerun-finalize-1020") and _is_rerun_request(request)
        )
        if not finalize:
            return await self._run_dispatch(request)
        try:
            result = await self._run_dispatch(request)
        except Exception as exc:
            await _finalize_scheduled_run(request, error=str(exc)[:500])
            raise
        await _finalize_scheduled_run(request, result=result)
        return result

    async def _run_dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """原 run() 分发体：单 Schema / chain（kg.schema.extract.chain）。"""
        if workflow.patched("business-llm-default-v1"):
            selected = await _execute_activity(
                resolve_execution_llm,
                request,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
                schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
            )
            request = {**request, **selected}
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
            # 重跑执行中途崩溃：case 已标 RERUNING 且 resolve_failure_cases 不会
            # 再被调用——不回滚会永远滞留（队列不可见、无法再次重跑）
            if request.get("recordIdsBySource"):
                try:
                    await _execute_activity(
                        revert_rerun_failure_cases,
                        {
                            "rerunCaseIds": request.get("rerunCaseIds") or [],
                            "reason": f"重跑执行失败: {str(exc)[:300]}",
                        },
                        start_to_close_timeout=timedelta(seconds=60),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                    )
                except ActivityError:
                    workflow.logger.warning("重跑 case 回滚 OPEN 失败（可能滞留 RERUNING）")
            raise
        await self._report_script_run(schema_id, ok=True, error=None)
        return result

    async def _run_chain(self, request: dict[str, Any], schema_ids: list[str]) -> dict[str, Any]:
        """多 Schema 严格串行：任一环失败即置 FAILED 并中止（恢复走 reset 回放）。"""
        failures_total = {"count": 0, "recorded": 0, "noRecordId": 0, "truncated": False}
        for pos, schema_id in enumerate(schema_ids):
            # 步间暂停挂起点：当前环正常结束后、下一环开始前等待恢复
            await self._wait_if_paused()
            step_key = f"schema:{schema_id}"
            # current 与 chain_steps 键同形（带 schema: 前缀）：前端以
            # current 是否命中 steps 判断「当前环」补位节点，裸 id 恒未命中
            # 会在任务完成后仍显示一个「执行中」幻影步
            self._current_schema = step_key
            step_started = workflow.now().astimezone()
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
                    "startedAt": step_started.isoformat(sep=" ", timespec="seconds"),
                    "finishedAt": workflow.now()
                    .astimezone()
                    .isoformat(sep=" ", timespec="seconds"),
                }
                raise
            sources = result.get("sources") or []
            # 内层 activities = 该脚本各 @step 转换步聚合（position：Temporal 编码
            # 按 key 排序，前端须按 position 还原脚本步序）
            activities: dict[str, dict[str, Any]] = {}
            for act_pos, (sid, stat) in enumerate((result.get("steps") or {}).items()):
                activities[sid] = {
                    "status": stat.get("status", "COMPLETED"),
                    "name": sid,
                    "position": act_pos + 1,
                    "records": int(stat.get("records", 0)),
                    "written": int(stat.get("written", 0)),
                    "failed": int(stat.get("failed", 0)),
                }
            fail = result.get("failures") or {}
            failures_total["count"] += int(fail.get("count", 0))
            failures_total["recorded"] += int(fail.get("recorded", 0))
            failures_total["noRecordId"] += int(fail.get("noRecordId", 0))
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
                "startedAt": step_started.isoformat(sep=" ", timespec="seconds"),
                "finishedAt": workflow.now().astimezone().isoformat(sep=" ", timespec="seconds"),
                # 输入 = 该环的触发上下文与来源绑定（详情页「阶段真实输入输出」卡片）
                "input": {
                    "schemaId": schema_id,
                    "graphSpace": request.get("graph_space"),
                    "batchSize": request.get("batchSize"),
                    "triggerSource": request.get("triggerSource", "MANUAL"),
                    "sources": [
                        {
                            "source": s.get("source"),
                            "table": s.get("table"),
                            "batches": s.get("batches"),
                        }
                        for s in sources
                    ],
                },
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
        plan = await _execute_activity(
            load_schema_extract_plan,
            (
                {**request, "schemaId": schema_id}
                if workflow.patched("business-rbac-context-v1")
                else schema_id
            ),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=ACTIVITY_RETRY_POLICY,
            schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
        )
        if workflow.patched("business-rbac-context-v1") and not graph_space:
            graph_space = plan.get("graphSpace")
            graph = {"space": graph_space} if graph_space else {}
        timeout_seconds = max(int(plan.get("timeoutSeconds", 3600)), 60)
        kind = plan.get("kind", "entity")
        definition_id = (
            plan.get("definitionId") if workflow.patched("business-rbac-context-v1") else None
        ) or f"schema-extract-{plan['schemaKey']}"
        # 步清单：@step 声明是唯一脚本形态（上传与计划组装双重校验），批内步序
        # 串行，每步一次 execute_transform 独立重试
        steps: list[dict[str, str]] = plan["steps"]
        self._run_script_object = plan.get("scriptRunKey")
        # 分步聚合计数：详情页每个 Schema 抽屉展示各转换步统计
        track_steps = True

        # 周期 Schedule 触发：request 是扁平 shape（非 {definitionId, payload}），
        # 直接调注册 activity 落 execution/task 行（幂等）。chain 模式下控制面
        # execution/task 行挂在 chain 定义上（chainDefinitionId）；水位读写键不变。
        schedule_id = request.get("_scheduleId")
        if schedule_id:
            info = workflow.info()
            # 执行记录 payload 带上解析后的目标图空间：Schedule 直发载荷可能没记
            # 空间（job 建时未传 graphSpace，实际落图空间来自 Schema 绑定），而
            # 总览「昨日新增」/任务列表都按 payload.graph_space 归属空间，缺记
            # 会被算进默认空间
            record_payload = dict(request)
            if graph_space:
                record_payload["graph_space"] = graph_space
            await _execute_activity(
                register_scheduled_execution,
                {
                    "definitionId": request.get("chainDefinitionId") or definition_id,
                    "scheduleId": schedule_id,
                    "workflowId": info.workflow_id,
                    "runId": info.run_id,
                    "payload": record_payload,
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=ACTIVITY_RETRY_POLICY,
                schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
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
        if workflow.patched("business-script-sandbox-v1"):
            # Use the resolved Schema space for scripts and pending-review creation,
            # including runs started without an explicit graph-space override.
            selectors["graph_space"] = graph_space
        # 方案②a：随环索引改批级增量（write_records 留档 vid 清单 → 环末索引
        # activity 下载后按冻结 BM25 词表 upsert）。patch 守卫保证在飞旧 run
        # 重放进旧分支（全量重建），无历史失配；新 run 全量路径不可达，消除
        # 「重建耗时 > activity 超时 → 自锁整链 FAILED」缺陷。
        use_incremental_index = workflow.patched("entity-index-incremental-v1")
        # gray-gate-v2：单一 patch id 门控全部 v2 行为（在飞旧 run 重放走旧分支，
        # 事件历史零失配）。decisionPolicy 在 workflow 启动解析一次、固化进各
        # activity 输入（纯常量，重放确定性；activity 内禁止再读环境变量改策略）
        gray_gate_v2 = workflow.patched("gray-gate-v1")
        decision_policy: dict[str, Any] | None = gray_gate_policy() if gray_gate_v2 else None

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
            # 增量索引 vid 留档状态（worker 协程并发变更 dict 字段，无 nonlocal）：
            # keys = write_records 回传的 S3 工件 key；missing = 有实体写入但
            # 工件不可得（S3 中转未开），索引步跳过时给可区分的原因
            vids_manifest: dict[str, Any] = {"keys": [], "missing": False}

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
                    # 触发时填的增量游标：无持久化水位的来源首轮从这读起（_since_seed）
                    "since": selectors.get("since"),
                }
                if workflow.patched("business-source-sandbox-v1"):
                    read_base.update(
                        actorUserId=request.get("actorUserId"),
                        clientId=request.get("clientId"),
                        schemaId=schema_id,
                        graphSpace=graph_space,
                        source=source,
                        selectors=selectors,
                    )
                if rerun_mode:
                    read_base["recordIds"] = rerun_ids.get(source_id)
                    try:
                        batch = await _execute_activity(
                            read_source_batch,
                            read_base,
                            start_to_close_timeout=timedelta(seconds=600),
                            retry_policy=ACTIVITY_RETRY_POLICY,
                            schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
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
                # 首批回传的读取起点水位（活动内由控制库解析），空批也要带上
                start_wm: str | None = None
                while True:
                    batch = await _execute_activity(
                        read_source_batch,
                        {**read_base, "batchIdx": idx, **cursor},
                        start_to_close_timeout=timedelta(seconds=600),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                    )
                    if idx == 0:
                        start_wm = batch.get("startWatermark")
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
                    return {
                        "batches": idx,
                        "watermark": final_wm,
                        "pkCursor": None,
                        "startWatermark": start_wm,
                    }
                return {"batches": idx, **final, "startWatermark": start_wm}

            # 分步聚合计数（多步脚本或 chain 模式；stepId → position/records/written/failed）
            # step_times：各转换步首末批时间（耗时列展示；暂停时长计入不剔除）
            step_times: dict[str, dict[str, str]] = {}
            step_totals: dict[str, dict[str, int]] = (
                {
                    s["id"]: {"position": pos + 1, "records": 0, "written": 0, "failed": 0}
                    for pos, s in enumerate(steps)
                }
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
                        # gray-gate-v2 pending 旁路聚合（chunk 内跨步累积，随写边请求
                        # 下发；跨 chunk/worker 的缺口由 write_records 端点存在性终判兜底）
                        pending_invalid_endpoints: set[str] = set()
                        pending_rewrite_map: dict[str, str] = {}
                        # 当前步标识：整批 ActivityError 的按步归因用（except 块里可见）
                        current_step_id: str | None = None
                        current_seq = 0
                        try:
                            # 步链串行执行（批间并行度仍由 max_inflight 的队列背压管）：
                            # 每步一次 execute_transform，带各自的 functionName/payload，
                            # 第 k 步失败由 Temporal 只重试第 k 步（前序步输出在事件
                            # 历史里重放）。任意一步出了 entities/edges 就在该步之后
                            # 写图（实体再接消歧）；failures 跨步聚合。
                            prev_output: dict[str, Any] = {}
                            step_outputs: dict[str, Any] = {}
                            for seq, step in enumerate(steps):
                                # 步间暂停挂起点：当前步结束后、下一步开始前等待
                                await self._wait_if_paused()
                                current_step_id = step["id"]
                                current_seq = seq
                                step_started = workflow.now().astimezone()
                                transform_request: dict[str, Any] = {
                                    "scriptPath": plan["scriptPath"],
                                    # run 副本定位（tempfile 丢失时按此重物化）
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
                                    "ctxStepId": f"{step_id}#{step['id']}",
                                    # 载荷 key 的确定性派生字段（batch/chunk 序，内联路径多带无害）
                                    "batchIdx": idx,
                                    "chunkIdx": chunk["index"],
                                }
                                if workflow.patched("business-script-sandbox-v1"):
                                    transform_request.update(
                                        actorUserId=request.get("actorUserId"),
                                        clientId=request.get("clientId"),
                                        schemaId=schema_id,
                                        graphSpace=graph_space,
                                    )
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
                                    # 第 1 步：消费平台读的源表行
                                    transform_request["rows"] = chunk["rows"]
                                if gray_gate_v2:
                                    # 双流：挂起清单不在 activity 内强制建案，交
                                    # resolve_pending_entities 做真实灰区门控处置
                                    transform_request["pendingMode"] = "resolve"
                                transformed = await _execute_activity(
                                    execute_transform,
                                    transform_request,
                                    start_to_close_timeout=timedelta(seconds=timeout_seconds + 60),
                                    retry_policy=ACTIVITY_RETRY_POLICY,
                                    schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                                )
                                # gray-gate-v2 双流：挂起清单浮现（S3=pendingKey / 内联=
                                # pendingReview，弹出防混入步间链），写图前先过
                                # resolve_pending_entities 真实灰区门控；聚合的
                                # invalidEndpointVids/rewriteMap 随本 chunk 的写边请求下发
                                pending_items: list[dict[str, Any]] = []
                                pending_s3_key: str | None = None
                                if "outKey" in transformed:
                                    pending_s3_key = transformed.get("pendingKey") or None
                                else:
                                    pending_items = transformed.pop("pendingReview", []) or []
                                if gray_gate_v2 and (pending_items or pending_s3_key):
                                    resolved_pending = await _execute_activity(
                                        resolve_pending_entities,
                                        {
                                            "graph": graph,
                                            "stepId": f"{step_id}#{step['id']}",
                                            "batchIdx": idx,
                                            "chunkIdx": chunk["index"],
                                            "sourceTable": table_label,
                                            "decisionPolicy": decision_policy,
                                            **(
                                                {"pending": pending_items}
                                                if pending_items
                                                else {"pendingKey": pending_s3_key}
                                            ),
                                        },
                                        start_to_close_timeout=timedelta(seconds=900),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                                    )
                                    pending_invalid_endpoints.update(
                                        resolved_pending.get("invalidEndpointVids") or []
                                    )
                                    pending_rewrite_map.update(
                                        resolved_pending.get("rewriteMap") or {}
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
                                    resolved = await _execute_activity(
                                        resolve_entity_batch,
                                        {
                                            "name": plan["name"],
                                            "graph": graph,
                                            "schemaKey": plan["schemaKey"],
                                            "stepId": f"{step_id}#{step['id']}",
                                            "sourceTable": table_label,
                                            "batchIdx": idx,
                                            "chunkIdx": chunk["index"],
                                            **(
                                                {"decisionPolicy": decision_policy}
                                                if gray_gate_v2
                                                else {}
                                            ),
                                            **records_arg,
                                        },
                                        # STC 900s（缺陷㉚）：批 2000 名按 150 分块召回 16 条
                                        # 查询 + 水位退避（10×20s）在图库高压期合法超 300s，
                                        # 原 300s 窗口在 RetryPolicy 5 次内同撞墙 → 终败整链
                                        # （第七次执行 21:11 实锤 2 个任务烧尽）。留 3 倍余量。
                                        start_to_close_timeout=timedelta(seconds=900),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                                    )
                                    if "outKey" in resolved:
                                        records_count = int(resolved.get("keptCount") or 0)
                                        records_arg = {"recordsKey": resolved["outKey"]}
                                    else:
                                        records_count = len(resolved.get("records") or [])
                                        records_arg = {"records": resolved.get("records") or []}
                                if records_count:
                                    write_request: dict[str, Any] = {
                                        "kind": kind,
                                        "name": plan["name"],
                                        "activeProps": plan["activeProps"],
                                        "graph": graph,
                                        "sourceTable": table_label,
                                        # 写前守卫终判建案时的溯源（同 resolve 口径）
                                        "stepId": f"{step_id}#{step['id']}",
                                        "batchIdx": idx,
                                        "chunkIdx": chunk["index"],
                                        **records_arg,
                                    }
                                    if gray_gate_v2:
                                        # v2：写前守卫（实体 prewrite）/关系写边都按
                                        # decisionPolicy 分支；pending 旁路聚合的端点
                                        # 处置（invalid 过滤 / rewrite 改写）随关系请求下发
                                        write_request["decisionPolicy"] = decision_policy
                                        if kind == "relation":
                                            write_request["invalidEndpointVids"] = sorted(
                                                pending_invalid_endpoints
                                            )
                                            write_request["rewriteMap"] = dict(pending_rewrite_map)
                                    if use_incremental_index and kind == "entity":
                                        # vid 清单 claim-check 派生字段（与
                                        # resolve_entity_batch 的键派生一致，
                                        # activity 内同 request → 同 key → 幂等）
                                        write_request["indexVids"] = True
                                    write_result = await _execute_activity(
                                        write_records,
                                        write_request,
                                        start_to_close_timeout=timedelta(seconds=600),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                                    )
                                    step_written = int(write_result.get("written", 0))
                                    # 写前终判扣留时拿过滤后的 records：碰撞检测/计数
                                    # 只看真正落图的记录（与 resolve 扣留同一语义）
                                    if "outKey" in write_result:
                                        records_count = int(
                                            write_result.get("keptCount", records_count)
                                        )
                                        records_arg = {"recordsKey": write_result["outKey"]}
                                    elif "records" in write_result:
                                        records_arg = {"records": write_result["records"]}
                                        records_count = len(records_arg["records"])
                                    if use_incremental_index and kind == "entity":
                                        # 按已记录的结果形状分支（重放安全）：
                                        # S3 关/0 写入 → 无 vidsKey
                                        if write_result.get("vidsKey"):
                                            vids_manifest["keys"].append(write_result["vidsKey"])
                                        elif step_written > 0:
                                            vids_manifest["missing"] = True
                                # v2 退出消歧 v1 碰撞检测（同名召回已在 resolve/prewrite
                                # 统一接管，真实灰区才建 T_LINK，不再强制送审）
                                if (
                                    kind == "entity"
                                    and records_count
                                    and detect_collisions
                                    and not gray_gate_v2
                                ):
                                    await _execute_activity(
                                        detect_extract_collisions,
                                        {
                                            "name": plan["name"],
                                            "graph": graph,
                                            "schemaKey": plan["schemaKey"],
                                            "stepId": f"{step_id}#{step['id']}",
                                            **records_arg,
                                        },
                                        # STC 120→300s（缺陷㉚预防）：碰撞探测 150 名/块分块
                                        # 查询 + 水位退避 4×20s，与 resolve 同型的高压期风险
                                        start_to_close_timeout=timedelta(seconds=300),
                                        retry_policy=ACTIVITY_RETRY_POLICY,
                                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                                    )
                                written += step_written
                                step_finished = workflow.now().astimezone()
                                if track_steps:
                                    chunk_step_stats[step["id"]] = {
                                        # position：Temporal JSON 编码会按 key 排序，
                                        # 步序必须显式携带否则详情页乱序
                                        "position": seq + 1,
                                        "records": records_count,
                                        "written": step_written,
                                        "failed": step_fail_count,
                                    }
                                    # 首末批时间：started 取首见，finished 取最后一次
                                    step_times.setdefault(
                                        step["id"],
                                        {
                                            "startedAt": step_started.isoformat(
                                                sep=" ", timespec="seconds"
                                            ),
                                        },
                                    )
                                    step_times[step["id"]]["finishedAt"] = step_finished.isoformat(
                                        sep=" ", timespec="seconds"
                                    )
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
                            if track_steps and current_step_id:
                                # 整批失败按步归因：失败行计入 activity 重试耗尽时所在的
                                # 步，步级 failed>0 让任务详情/审核日志弹窗的阶段显示
                                # 「异常」，与执行概要 ABNORMAL 对齐——否则步级恒零骨架
                                # 恒显成功（2026-10-11 用例 MR-20261009-A2DBE6074880）
                                stat = chunk_step_stats.setdefault(
                                    current_step_id,
                                    {
                                        "position": current_seq + 1,
                                        "records": 0,
                                        "written": 0,
                                        "failed": 0,
                                    },
                                )
                                stat["failed"] += _failure_entries_count(batch_failures)
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
                                    sid,
                                    {
                                        "position": int(stat.get("position", 0)),
                                        "records": 0,
                                        "written": 0,
                                        "failed": 0,
                                    },
                                )
                                for key in ("records", "written", "failed"):
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
                    await _execute_activity(
                        advance_schema_extract_watermark,
                        advance_req,
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                    )

            self._sources[step_id] = {
                **self._sources[step_id],
                "status": "COMPLETED",
                "batches": read_summary.get("batches", 0),
                "rows": total_rows,
                "written": total_written,
                "failed": source_failed,
                # 分步聚合计数（多步脚本/chain 模式；单步单跑摘要形状保持不变）
                **(
                    {
                        "steps": {
                            sid: {**stat, **step_times.get(sid, {})}
                            for sid, stat in step_totals.items()
                        }
                    }
                    if track_steps
                    else {}
                ),
            }
            return {
                "vidsKeys": vids_manifest["keys"],
                "vidsMissing": vids_manifest["missing"],
                "source": step_id,
                "table": table_label,
                "batches": read_summary.get("batches", 0),
                "rows": total_rows,
                "written": total_written,
                "failed": source_failed,
                "failures": source_failures,
                "watermark": read_summary.get("watermark"),
                # 开跑前的读取起点水位：watermark 是跑完后的终值，今日新增
                # 反查图内对象的窗口下界优先用它，避免窗口退化成最后一批同秒
                "startWatermark": read_summary.get("startWatermark"),
                "pkCursor": read_summary.get("pkCursor"),
                **(
                    {
                        "steps": {
                            sid: {**stat, **step_times.get(sid, {})}
                            for sid, stat in step_totals.items()
                        }
                    }
                    if track_steps
                    else {}
                ),
            }

        results = await asyncio.gather(*(extract_source(source) for source in plan["sources"]))
        all_failures = [f for r in results for f in (r.get("failures") or [])]
        # 增量索引 vid 工件合并（跨来源/跨步去重在索引 activity 内做；旧 run
        # 与 relation 环恒为空列表，不影响既有分支）
        index_vid_keys = [k for r in results for k in (r.get("vidsKeys") or [])]
        index_vids_missing = any(r.get("vidsMissing") for r in results)
        # 失败聚合双形状：S3 中转的清单以 failuresKey 引用（历史只过 key + 计数），
        # 内联条目（旧路径 / 重跑合成）原样；终态建 case 的 activity 内下载展开
        failure_refs = [f for f in all_failures if "failuresKey" in f]
        inline_failures = [f for f in all_failures if "failuresKey" not in f]
        failures_total = _failure_entries_count(failure_refs) + len(inline_failures)
        truncated = failures_total > failure_cap
        recorded_count = 0
        # 缺记录 id 未入审核队列的条数（record_extract_failures 回报；重跑/无失败恒 0）
        no_record_id_count = 0
        index_summary: Any = None
        if rerun_mode:
            # 重跑：resolve 必调且拿全量失败键（未截断），仍失败记录由服务端重建 case
            await _execute_activity(
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
                schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
            )
        else:
            do_index = request.get("buildIndex")
            if do_index is None:
                # 共享图库内存受限时可不随环重建（SCHEMA_EXTRACT_BUILD_INDEX=0，
                # env 在 load_schema_extract_plan activity 内读、经 plan 传入）：
                # 全空间重建 pass 自身也可能把宿主顶过高水位，且被上限取消的
                # 线程仍后台读图，与下一环写图叠加越线整链 FAILED。显式跳过
                # 不是失败，用管理端点 POST /entity-search/reindex 在全部抽取
                # 结束后统一全量重建。
                do_index = kind == "entity" and plan.get("buildIndexEnabled", True)
            if do_index and kind == "entity":
                # 索引构建失败即任务 FAILED（2026-09-29 用户口径）：不再降级成
                # 警告吞掉——重试耗尽后 ActivityError 上抛，整链失败，执行详情
                # 的失败原因带上索引 activity 的报错信息。显式关闭
                # （buildIndexEnabled=False）属计划内跳过，不算失败。
                if use_incremental_index:
                    # 方案②a：vid 工件非空 → 冻结词表批级增量（秒级~分钟级，
                    # 代价 ∝ 变更量）；空 → 计划内跳过（0 写入环不再白跑全量
                    # 重建；S3 中转未开的栈 vid 不可得，同样跳过不算失败）
                    if index_vid_keys:
                        index_result = await _execute_activity(
                            build_entity_index,
                            {"space": graph_space, "vidsKeys": index_vid_keys},
                            start_to_close_timeout=timedelta(
                                seconds=int(plan.get("indexTimeoutSeconds", 1800))
                            ),
                            retry_policy=ACTIVITY_RETRY_POLICY,
                            schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                        )
                        index_summary = (index_result or {}).get("reindexed")
                    else:
                        index_summary = {
                            "mode": "skip",
                            "reason": (
                                "写入 vid 未留档（批载荷 S3 中转未开）"
                                if index_vids_missing
                                else "本环无新增实体"
                            ),
                        }
                else:
                    index_result = await _execute_activity(
                        build_entity_index,
                        {"space": graph_space},
                        start_to_close_timeout=timedelta(
                            seconds=int(plan.get("indexTimeoutSeconds", 1800))
                        ),
                        retry_policy=ACTIVITY_RETRY_POLICY,
                        schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                    )
                    index_summary = (index_result or {}).get("reindexed")
            if failures_total:
                fail_resp = await _execute_activity(
                    record_extract_failures,
                    {
                        "failures": inline_failures,
                        "failureRefs": failure_refs,
                        "graphSpace": graph_space,
                        "cap": failure_cap,
                        "schemaId": schema_id,
                        "schemaKey": plan["schemaKey"],
                        "kind": kind,
                        "name": plan["name"],
                        "jobId": request.get("jobId"),
                    },
                    start_to_close_timeout=timedelta(seconds=600),
                    retry_policy=ACTIVITY_RETRY_POLICY,
                    schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
                )
                recorded_count = int((fail_resp or {}).get("recorded") or 0)
                no_record_id_count = int((fail_resp or {}).get("skippedNoRecordId") or 0)
        if sum(int(r.get("written") or 0) for r in results):
            # 写图后触发图库 stats job：SHOW STATS（平台总览实体/关系总量的数据源）
            # 只反映最近一次 SUBMIT JOB STATS 预计算，不触发则总览不随抽取更新（00918）。
            # activity 内部吞异常降级，失败不影响执行终态。
            await _execute_activity(
                refresh_graph_stats,
                {"space": graph_space},
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=ACTIVITY_RETRY_POLICY,
                schedule_to_start_timeout=ACTIVITY_SCHEDULE_TO_START,
            )

        # 多步脚本（及 chain 模式）的全局分步聚合计数（跨来源求和）。status 供任务
        # 详情 pipeline_steps 把每步渲染成「成功」；单步单跑不加该键，形状与历史一致。
        aggregated_steps: dict[str, dict[str, Any]] = {}
        if track_steps:
            for r in results:
                for sid, stat in (r.get("steps") or {}).items():
                    agg = aggregated_steps.setdefault(
                        sid,
                        {
                            # 步序与起止时间随聚合保留（Temporal 编码按 key
                            # 排序，详情页步序/耗时列依赖这些字段）
                            "position": int(stat.get("position") or 0),
                            "startedAt": stat.get("startedAt"),
                            "finishedAt": stat.get("finishedAt"),
                            "records": 0,
                            "written": 0,
                            "failed": 0,
                        },
                    )
                    for key in ("records", "written", "failed"):
                        agg[key] += int(stat.get(key, 0))
                    # 多来源并行：取最早开始 / 最晚结束
                    if stat.get("startedAt") and (
                        not agg["startedAt"] or stat["startedAt"] < agg["startedAt"]
                    ):
                        agg["startedAt"] = stat["startedAt"]
                    if stat.get("finishedAt") and (
                        not agg["finishedAt"] or stat["finishedAt"] > agg["finishedAt"]
                    ):
                        agg["finishedAt"] = stat["finishedAt"]

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
                    # chain 外层阶段命名（label 优先）
                    "schemaLabel": plan.get("label") or plan["name"],
                }
                if track_steps
                else {}
            ),
            "failures": {
                "count": failures_total,
                "recorded": recorded_count,
                "noRecordId": no_record_id_count,
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
        return {
            "current": self._current_schema,
            "steps": self._chain_steps,
            # 暂停确认：前端「暂停中 → 已暂停」以此为准（信号已收且到达挂起点）
            "paused": self._paused,
        }

    @workflow.query
    def get_progress(self) -> dict[str, Any]:
        return {
            "chain": bool(self._chain_steps),
            "schema": self._current_schema,
            "current": self._current_source,
            "sources": self._sources,
            "slots": self._slots,
            "paused": self._paused,
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
    详情页按 workflowType 区分 chain 渲染（每 Schema 一个抽屉，内层为脚本 @step 转换步）。
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
    resolve_execution_llm,
    load_workflow_definition,
    register_scheduled_execution,
    finalize_scheduled_execution,
    load_schema_extract_plan,
    read_source_batch,
    execute_transform,
    write_records,
    resolve_entity_batch,
    resolve_pending_entities,
    advance_schema_extract_watermark,
    record_schema_script_run,
    detect_extract_collisions,
    record_extract_failures,
    resolve_failure_cases,
    revert_rerun_failure_cases,
    build_entity_index,
    refresh_graph_stats,
]
