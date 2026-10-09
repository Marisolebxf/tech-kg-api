"""控制库执行状态对账：周期扫 RUNNING 陈旧行，向 Temporal 核实真值回写终态。

背景
----
周期 Schedule 直发 workflow 不经过 API：开头的 ``register_scheduled_execution``
activity 落 RUNNING 行后，终态原本只靠 ``get_execution`` 的惰性刷新（有人点开
执行详情才触发）——没人查看的调度执行会在任务中心永远显示「运行中」。
``temporal_workflows._finalize_scheduled_run`` 让新执行跑完即自报终态；本协程是
兜底：覆盖 CANCELLED（workflow 被取消时无法收尾）、收尾 activity 失败、api/worker
重启丢上下文、以及历史存量僵尸行。

语义
----
- 只挑「RUNNING 且 started_at 早于 stale 阈值」的行（避免刚起步就被核实）；
- 每行调 ``temporal_runtime.refresh_execution`` 向 Temporal 查真值——真长跑的
  抽取 refresh 后仍是 RUNNING，不会被误改；LOCAL_FALLBACK 行 refresh 内部跳过；
- Temporal 不可达时本轮放弃（不写库），下一轮重试；
- 回写 execution + task 同步 + job 最新执行信息，与详情页惰性刷新同口径。

开关：``EXECUTION_RECONCILE_ENABLED``（默认 true；tests/CI 显式关）；
间隔 ``EXECUTION_RECONCILE_INTERVAL_SECONDS``（默认 300）；
stal 阈值 ``EXECUTION_RECONCILE_STALE_MINUTES``（默认 30）。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

_INTERVAL = int(os.getenv("EXECUTION_RECONCILE_INTERVAL_SECONDS", "300"))
_STALE_MINUTES = int(os.getenv("EXECUTION_RECONCILE_STALE_MINUTES", "30"))
_BATCH_LIMIT = 20  # 每轮最多核实条数，防 Temporal RPC 风暴


async def reconcile_once() -> int:
    """扫一轮陈旧 RUNNING 行并回写真值；返回本轮处理条数。"""
    from service.temporal_runtime import temporal_runtime
    from service.workflow_operations import WorkflowOperationsService
    from service.workflow_repository import repository

    stale_before = (datetime.now(UTC).astimezone() - timedelta(minutes=_STALE_MINUTES)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows = repository.list_stale_running_executions(stale_before, limit=_BATCH_LIMIT)
    if not rows:
        return 0
    done = 0
    for execution in rows:
        try:
            refreshed = await temporal_runtime.refresh_execution(execution)
        except Exception as exc:  # noqa: BLE001  # Temporal 不可达：本轮放弃
            logger.warning("执行对账：refresh %s 失败: %s", execution.get("id"), exc)
            return done
        if refreshed.get("status") == execution.get("status"):
            continue  # 真在跑，不动
        repository.save_execution(refreshed)
        try:
            WorkflowOperationsService()._sync_task_from_execution(refreshed)
        except Exception:  # noqa: BLE001
            logger.exception("执行对账：同步 task 失败 %s", refreshed.get("id"))
        from service.temporal_workflows import _stamp_job_latest

        _stamp_job_latest(refreshed)
        done += 1
        logger.info(
            "执行对账：%s %s -> %s",
            refreshed.get("id"),
            execution.get("status"),
            refreshed.get("status"),
        )
    return done


async def run_execution_reconciler() -> None:
    """常驻循环；异常不退出，只记日志。"""
    logger.info("执行状态对账协程启动：间隔 %ss，stale 阈值 %s 分钟", _INTERVAL, _STALE_MINUTES)
    while True:
        try:
            await reconcile_once()
        except Exception:  # noqa: BLE001
            logger.exception("执行对账轮次异常")
        await asyncio.sleep(_INTERVAL)


__all__ = ["reconcile_once", "run_execution_reconciler"]
