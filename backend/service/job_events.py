"""任务变更推送（SSE）——API 进程内监视控制面表变化并广播给订阅连接。

为什么不在 worker 侧发事件：写控制面的不止 worker（API 的触发、惰性复核
也在写），进程内事件总线覆盖不全；统一收敛为「API 侧周期快照比对」一个
观察点。对浏览器仍是推送语义（连接常驻、变更即时下行），N 个前端的轮询
开销收敛为服务端单份；无订阅者时监视协程自动停转，零空转。

指纹面 = workflow_jobs（status + payload 哈希：暂停/恢复/增删与
lastExecutionStatus 等富字段翻转）+ workflow_executions（status +
started_at：Schedule 到点起跑插 RUNNING 行、执行翻终态）。前端收到事件
后静默重拉任务列表即可，不依赖事件内容的语义细节。
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)

Event = dict[str, list[str]]


def control_fingerprints() -> dict[str, tuple]:
    """控制面变更指纹：job:<id> → (status, payload sha256)，exec:<id> → (status, started_at)。"""
    from sqlalchemy import select

    from infra.workflow_mysql import workflow_session_scope
    from service.workflow_models import WorkflowExecution, WorkflowJob

    fingerprints: dict[str, tuple] = {}
    with workflow_session_scope() as session:
        for row in session.execute(select(WorkflowJob.id, WorkflowJob.status, WorkflowJob.payload)):
            fingerprints[f"job:{row.id}"] = (
                row.status,
                hashlib.sha256(row.payload.encode("utf-8")).hexdigest(),
            )
        for row in session.execute(
            select(WorkflowExecution.id, WorkflowExecution.status, WorkflowExecution.started_at)
        ):
            fingerprints[f"exec:{row.id}"] = (row.status, row.started_at)
    return fingerprints


def _poll_interval() -> float:
    try:
        return max(float(os.getenv("JOB_EVENT_POLL_SECONDS", "2")), 0.5)
    except ValueError:
        return 2.0


def _refresh_interval() -> float:
    try:
        return max(float(os.getenv("JOB_EVENT_REFRESH_SECONDS", "5")), 1.0)
    except ValueError:
        return 5.0


async def refresh_running_executions(limit: int = 10) -> int:
    """把控制库里 RUNNING 的执行向 Temporal 对账，返回本次尝试对账的条数。

    终态只有 API 侧惰性刷新会落库（worker 只在起跑时写 RUNNING 行）——纯 SSE
    架构下没有前端轮询驱动刷新，必须由后台主动对账：对完账终态落库，hub 下一
    轮指纹比对才能发现并推送，否则「已完成」事件永远不发，前端卡在运行中。
    """
    from sqlalchemy import select

    from infra.workflow_mysql import workflow_session_scope
    from service.workflow_models import WorkflowExecution
    from service.workflow_operations import workflow_operations_service

    with workflow_session_scope() as session:
        ids = list(
            session.execute(
                select(WorkflowExecution.id)
                .where(WorkflowExecution.status == "RUNNING")
                .limit(limit)
            ).scalars()
        )
    for exec_id in ids:
        try:
            # get_execution 内部只对 RUNNING 做 Temporal describe 并落库 + 同步 task
            await workflow_operations_service.get_execution(exec_id)
        except Exception:  # noqa: BLE001
            # Temporal/DB 不可用：放弃本轮剩余对账，下轮重试
            break
    return len(ids)


class JobEventHub:
    """订阅者各持一条 asyncio.Queue；首个订阅者启动监视协程，最后一个退出时取消。

    ``refresh``（可选）：指纹面存在 RUNNING 执行时按节流周期调用（对账终态落库，
    见 ``refresh_running_executions``）；对账先于当轮指纹比对，同轮即可发现翻转。
    """

    def __init__(
        self,
        poll: Callable[[], dict[str, tuple]],
        interval: float | None = None,
        refresh: Callable[[], object] | None = None,
        refresh_interval: float | None = None,
    ) -> None:
        self._poll = poll
        self._interval = interval if interval is not None else _poll_interval()
        self._refresh = refresh
        self._refresh_interval = (
            refresh_interval if refresh_interval is not None else _refresh_interval()
        )
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._watcher: asyncio.Task[None] | None = None
        self._snapshot: dict[str, tuple] | None = None
        self._last_refresh = float("-inf")  # 首个 RUNNING 轮立即对账（loop.time 从近 0 起）

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.add(queue)
        if self._watcher is None or self._watcher.done():
            # 无监视期间不做增量比对（基线清空），重连方靠 open 回调全量重拉补齐
            self._snapshot = None
            self._watcher = asyncio.create_task(self._watch_loop())
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)
        if not self._subscribers and self._watcher is not None:
            self._watcher.cancel()
            self._watcher = None

    async def _watch_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._maybe_refresh()
            try:
                current = await asyncio.to_thread(self._poll)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("任务变更监视轮询失败（跳过本轮）")
                continue
            previous, self._snapshot = self._snapshot, current
            if previous is None:
                continue  # 首轮只建基线
            changed = sorted(key for key, fp in current.items() if fp != previous.get(key))
            removed = sorted(key for key in previous if key not in current)
            if not (changed or removed):
                continue
            event: Event = {"changed": changed, "removed": removed}
            for queue in list(self._subscribers):
                if queue.empty():  # 合并连发：消费方只关心"有变化"，积压一条足够
                    queue.put_nowait(event)

    async def _maybe_refresh(self) -> None:
        """有 RUNNING 执行且到对账周期时，向 Temporal 对账让终态落库（先于当轮比对）。"""
        if self._refresh is None or self._snapshot is None:
            return
        running = any(
            key.startswith("exec:") and fp and fp[0] == "RUNNING"
            for key, fp in self._snapshot.items()
        )
        if not running:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        if now - self._last_refresh < self._refresh_interval:
            return
        self._last_refresh = now
        try:
            outcome = self._refresh()
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:  # noqa: BLE001
            logger.exception("执行状态后台对账失败（跳过本轮）")


hub = JobEventHub(poll=control_fingerprints, refresh=refresh_running_executions)
