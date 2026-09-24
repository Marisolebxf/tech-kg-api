"""公共图执行层的并发预算：并发上限 + 有限等待队列 + 过载快速拒绝。

九大业务对 graph-search 的进程内自调用、前端对 graph-search 的直连，全部在
async 层先经过这里拿执行名额，而不是把压力直接推给 ``asyncio.to_thread``
线程池和 trs 会话池（会话池打满曾致 502，且排队的请求只会越等越慢）：

- ``GRAPH_EXEC_CONCURRENCY``：同时在执行的图查询上限（默认 16）；
- ``GRAPH_EXEC_QUEUE_LIMIT``：排队等待者超过该数立即拒绝（默认 64）；
- ``GRAPH_EXEC_WAIT_TIMEOUT``：排队等名额超过该秒数拒绝（默认 10s）。

过载统一抛 :class:`GraphExecOverloaded`，由 graph-search 端点转成
``code=429`` 的 ApiResponse 包络——降级必须可见，而不是静默吞成空结果。
在 async 层排队不占用线程池：等待者只是事件循环里的挂起协程，拿到名额后
才进入 ``asyncio.to_thread``。

按事件循环惰性建预算：asyncio 原语绑定首个使用它的循环，跨循环复用会
RuntimeError（测试每个用例各建循环），服务进程单循环下即全局一份；
WeakKeyDictionary 随循环销毁回收。
"""

from __future__ import annotations

import asyncio
import collections.abc
import contextlib
import os
import weakref
from dataclasses import dataclass

# 并发上限/队列上限/排队超时均可用环境变量调整（压测或排障时）。
GRAPH_EXEC_CONCURRENCY = max(1, int(os.getenv("GRAPH_EXEC_CONCURRENCY", "16")))
GRAPH_EXEC_QUEUE_LIMIT = max(0, int(os.getenv("GRAPH_EXEC_QUEUE_LIMIT", "64")))
GRAPH_EXEC_WAIT_TIMEOUT = max(0.0, float(os.getenv("GRAPH_EXEC_WAIT_TIMEOUT", "10")))


class GraphExecOverloaded(RuntimeError):
    """图执行层过载（等待队列已满或排队超时），调用方应快速拒绝。"""


@dataclass
class _LoopBudget:
    """单个事件循环上的执行预算：信号量 + 当前排队等待数。"""

    semaphore: asyncio.Semaphore
    waiting: int = 0


_budgets: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

# 按事件循环共享的具名信号量（供各业务模块的模块级并发上限使用，替代每请求
# 各建一个 Semaphore 的旧写法——那只限单请求，N 个并发请求就是 N 倍上限）。
_named_semaphores: dict[tuple[int, str], weakref.WeakKeyDictionary] = {}


def _loop_budget() -> _LoopBudget:
    budget = _budgets.get(asyncio.get_running_loop())
    if budget is None:
        budget = _LoopBudget(asyncio.Semaphore(GRAPH_EXEC_CONCURRENCY))
        _budgets[asyncio.get_running_loop()] = budget
    return budget


def loop_scoped_semaphore(name: str, value: int) -> asyncio.Semaphore:
    """按当前事件循环共享的 asyncio.Semaphore（value 变化即视为新预算）。"""
    loops = _named_semaphores.setdefault((value, name), weakref.WeakKeyDictionary())
    loop = asyncio.get_running_loop()
    semaphore = loops.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(value)
        loops[loop] = semaphore
    return semaphore


@contextlib.asynccontextmanager
async def graph_exec_slot() -> collections.abc.AsyncGenerator[None, None]:
    """获取一个图执行名额；过载（队列满/排队超时）抛 GraphExecOverloaded。

    有空位时直取：``Semaphore.acquire`` 在有空位时不挂起协程，检查与获取
    之间无 await 点，事件循环内原子——也不计入等待队列（wait_for 会把
    acquire 包成任务、即使立即完成也经一次调度，瞬时在途获取会被误计成
    "排队中"，令队列上限过度拒绝）。``GRAPH_EXEC_WAIT_TIMEOUT=0`` 表示
    不排队：有空位立即执行，无空位立即拒绝。
    """
    budget = _loop_budget()
    if not budget.semaphore.locked():
        await budget.semaphore.acquire()
    elif GRAPH_EXEC_WAIT_TIMEOUT <= 0:
        raise GraphExecOverloaded("图查询过载：执行名额已满，请稍后重试")
    else:
        if budget.waiting >= GRAPH_EXEC_QUEUE_LIMIT:
            raise GraphExecOverloaded("图查询过载：等待队列已满，请稍后重试")
        budget.waiting += 1
        try:
            try:
                await asyncio.wait_for(budget.semaphore.acquire(), timeout=GRAPH_EXEC_WAIT_TIMEOUT)
            except TimeoutError:
                raise GraphExecOverloaded(
                    f"图查询过载：排队超过 {GRAPH_EXEC_WAIT_TIMEOUT}s，请稍后重试"
                ) from None
        finally:
            budget.waiting -= 1
    try:
        yield
    finally:
        budget.semaphore.release()
