"""公共图执行预算（graph-search 卡口1）的单元测试。

预算语义：并发上限 + 有限等待队列（超限立即拒绝）+ 排队超时（超时拒绝），
按事件循环共享（服务进程单循环下即进程级）。
"""

import asyncio

import pytest

from infra import graph_exec_budget
from infra.graph_exec_budget import (
    GraphExecOverloaded,
    graph_exec_slot,
    loop_scoped_semaphore,
)


@pytest.fixture(autouse=True)
def _fresh_budget():
    """清空按循环缓存的预算/信号量，避免用例间串扰。"""
    graph_exec_budget._budgets.clear()
    graph_exec_budget._named_semaphores.clear()
    yield
    graph_exec_budget._budgets.clear()
    graph_exec_budget._named_semaphores.clear()


async def test_slot_caps_concurrency_across_callers(monkeypatch):
    """并发上限对多个调用方共享：两批任务同时抢名额，在飞峰值仍 ≤ 上限。"""
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_CONCURRENCY", 2)
    in_flight = 0
    peak = 0

    async def one_caller():
        async with graph_exec_slot():
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    await asyncio.gather(*[one_caller() for _ in range(8)])

    assert peak == 2  # 上限生效且确实有并发（不是退化成串行）


async def test_slot_rejects_immediately_when_queue_full(monkeypatch):
    """等待队列有界：占满后新到者立即被拒（429 语义），不进队慢慢等。"""
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_CONCURRENCY", 1)
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_QUEUE_LIMIT", 1)

    outcomes: list[str] = []

    async def one_caller():
        try:
            async with graph_exec_slot():
                await asyncio.sleep(0.05)
            outcomes.append("ok")
        except GraphExecOverloaded:
            outcomes.append("rejected")

    # 1 个执行 + 1 个排队 + 1 个超队 → 第三个立即拒绝
    await asyncio.gather(one_caller(), one_caller(), one_caller())

    assert outcomes.count("ok") == 2
    assert outcomes.count("rejected") == 1


async def test_slot_rejects_on_wait_timeout(monkeypatch):
    """排队有超时：名额长期被占时等待者在超时后被拒，而不是无限挂起。"""
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_CONCURRENCY", 1)
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_WAIT_TIMEOUT", 0.05)

    async def holder():
        async with graph_exec_slot():
            await asyncio.sleep(0.2)

    async def waiter():
        async with graph_exec_slot():
            pass  # pragma: no cover - 不应拿到名额

    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)  # 让 holder 先拿到名额
    with pytest.raises(GraphExecOverloaded, match="排队超过"):
        await waiter()

    # 拒绝后等待计数归零，不残留（否则后续请求会被误判队列满）
    assert graph_exec_budget._loop_budget().waiting == 0
    await holder_task


async def test_slot_zero_timeout_never_queues(monkeypatch):
    """WAIT_TIMEOUT=0 = 不排队：有空位立即执行，无空位立即拒绝。"""
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_CONCURRENCY", 1)
    monkeypatch.setattr(graph_exec_budget, "GRAPH_EXEC_WAIT_TIMEOUT", 0)

    # 空位时串行获取全部成功（不因 timeout=0 被误拒）
    async with graph_exec_slot():
        pass
    async with graph_exec_slot():
        pass

    async def holder():
        async with graph_exec_slot():
            await asyncio.sleep(0.05)

    async def impatient():
        async with graph_exec_slot():
            pass  # pragma: no cover

    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)  # 让 holder 先拿到名额
    with pytest.raises(GraphExecOverloaded, match="执行名额已满"):
        await impatient()
    await holder_task


async def test_slot_released_when_body_raises():
    """执行体抛异常也释放名额，不泄漏（否则一个异常请求永久占用预算）。"""

    async def boom():
        async with graph_exec_slot():
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await boom()

    # 名额已回收：下一个调用立即可得
    async with graph_exec_slot():
        pass


def test_budget_shared_within_loop_isolated_across_loops():
    """预算按事件循环共享：单循环内全局一份；跨循环各自独立。"""

    async def grab():
        async with graph_exec_slot():
            return graph_exec_budget._loop_budget()

    first = asyncio.run(grab())
    second = asyncio.run(grab())
    assert first is not second  # 各循环独立实例，跨循环复用会 RuntimeError

    async def same_loop_twice():
        assert graph_exec_budget._loop_budget() is graph_exec_budget._loop_budget()

    asyncio.run(same_loop_twice())


async def test_loop_scoped_semaphore_shared_and_value_scoped():
    """具名信号量：同循环同参数共享一份；参数（上限值）变化即视为新预算。"""
    a1 = loop_scoped_semaphore("m", 5)
    a2 = loop_scoped_semaphore("m", 5)
    b = loop_scoped_semaphore("m", 3)
    c = loop_scoped_semaphore("other", 5)
    assert a1 is a2
    assert a1 is not b
    assert a1 is not c


def test_loop_scoped_semaphore_isolated_across_loops():
    async def in_one_loop():
        return loop_scoped_semaphore("m", 5)

    first = asyncio.run(in_one_loop())
    second = asyncio.run(in_one_loop())
    assert first is not second  # 各循环独立实例，跨循环复用会 RuntimeError
