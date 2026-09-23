"""任务变更 SSE 推送：hub 增量比对逻辑 + /jobs/events 流式端点。"""

from __future__ import annotations

import asyncio
import uuid

import pytest


class FakePoll:
    """可变指纹源：测试直接改 state 制造变更/删除。"""

    def __init__(self) -> None:
        self.state: dict[str, tuple] = {}

    def __call__(self) -> dict[str, tuple]:
        return dict(self.state)


def _hub(state: dict[str, tuple]) -> tuple:
    from service.job_events import JobEventHub

    poll = FakePoll()
    poll.state = state
    return JobEventHub(poll=poll, interval=0.01), poll


@pytest.mark.asyncio
async def test_hub_first_poll_builds_baseline_without_event() -> None:
    hub, _poll = _hub({"job:a": ("启用", "h1")})
    queue = hub.subscribe()
    try:
        await asyncio.sleep(0.06)  # 足够跑多轮：只建基线，不发事件
        assert queue.empty()
    finally:
        hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_hub_emits_change_and_remove_events() -> None:
    hub, poll = _hub({"job:a": ("启用", "h1"), "exec:e1": ("RUNNING", "t1")})
    queue = hub.subscribe()
    try:
        await asyncio.sleep(0.06)  # 基线

        poll.state["exec:e1"] = ("COMPLETED", "t1")
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == {"changed": ["exec:e1"], "removed": []}

        del poll.state["job:a"]
        poll.state["job:b"] = ("启用", "h9")
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == {"changed": ["job:b"], "removed": ["job:a"]}
    finally:
        hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_hub_coalesces_backlog() -> None:
    """消费方未取时连发多次变更只积压 1 条——前端只关心"有变化"。"""
    hub, poll = _hub({"job:a": ("启用", "h1")})
    queue = hub.subscribe()
    try:
        await asyncio.sleep(0.06)  # 基线

        poll.state["job:a"] = ("启用", "h2")
        await asyncio.sleep(0.04)
        poll.state["job:a"] = ("启用", "h3")
        await asyncio.sleep(0.04)

        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event["changed"] == ["job:a"]
        assert queue.empty()
    finally:
        hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_hub_refreshes_running_execution_and_emits_terminal_event() -> None:
    """有 RUNNING 执行时按对账周期调 refresh（对账落库先于当轮比对，同轮发现翻转）。"""
    from service.job_events import JobEventHub

    poll = FakePoll()
    poll.state = {"exec:e1": ("RUNNING", "t1")}
    refresh_calls = 0

    async def fake_refresh() -> int:
        nonlocal refresh_calls
        refresh_calls += 1
        poll.state["exec:e1"] = ("COMPLETED", "t1")  # 模拟对账把终态落库
        return 1

    hub = JobEventHub(poll=poll, interval=0.01, refresh=fake_refresh, refresh_interval=1.0)
    queue = hub.subscribe()
    try:
        event = await asyncio.wait_for(queue.get(), timeout=2)
        assert event["changed"] == ["exec:e1"]
        assert refresh_calls == 1  # refresh_interval=1s 内只对账一次（节流）
        await asyncio.sleep(0.05)
        assert refresh_calls == 1
    finally:
        hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_hub_skips_refresh_when_no_execution_running() -> None:
    from service.job_events import JobEventHub

    poll = FakePoll()
    poll.state = {"exec:e1": ("COMPLETED", "t1"), "job:a": ("启用", "h1")}
    refresh_calls = 0

    async def fake_refresh() -> int:
        nonlocal refresh_calls
        refresh_calls += 1
        return 0

    hub = JobEventHub(poll=poll, interval=0.01, refresh=fake_refresh, refresh_interval=0.0)
    queue = hub.subscribe()
    try:
        await asyncio.sleep(0.06)  # 多轮比对：无 RUNNING 执行不应触发对账
        assert queue.empty()
        assert refresh_calls == 0
    finally:
        hub.unsubscribe(queue)


@pytest.mark.asyncio
async def test_hub_stops_watcher_after_last_subscriber() -> None:
    hub, _poll = _hub({})
    queue = hub.subscribe()
    watcher = hub._watcher
    assert watcher is not None
    hub.unsubscribe(queue)
    await asyncio.sleep(0.02)
    assert hub._watcher is None
    assert watcher.cancelled() or watcher.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("business_rbac", [False, True])
async def test_jobs_events_endpoint_streams_changes(
    monkeypatch: pytest.MonkeyPatch, business_rbac: bool
) -> None:
    """直接驱动端点返回的 body_iterator——httpx ASGITransport 会等 app 整体
    跑完才返回响应，无限 SSE 流在 transport 层必然死锁，走不了 client.stream。"""
    import json

    from biz.handler import workflow_system
    from service import job_events as job_events_module
    from service.platform_access import PlatformActor

    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true" if business_rbac else "false")
    actor = PlatformActor(
        user_id="business-developer",
        username="developer",
        display_name="Developer",
        email="",
        is_admin=False,
        business_id="business-a",
        business_role="developer",
    )

    poll = FakePoll()
    monkeypatch.setattr(job_events_module.hub, "_poll", poll)
    monkeypatch.setattr(job_events_module.hub, "_interval", 0.02)

    response = await workflow_system.stream_job_events(actor)
    assert response.media_type.startswith("text/event-stream")
    # nginx 默认缓冲代理响应会攒住流，必须显式关掉
    assert response.headers["x-accel-buffering"] == "no"

    poll.state = {"job:a": ("启用", "h1")}
    await asyncio.sleep(0.1)  # 基线

    poll.state["job:a"] = ("暂停", "h1")
    generator = response.body_iterator
    assert generator is not None
    try:
        first = await asyncio.wait_for(generator.__anext__(), timeout=3)
        assert "retry:" in first  # 首帧：断线重连提示

        event_chunk = ""
        while "jobs-changed" not in event_chunk:
            event_chunk = await asyncio.wait_for(generator.__anext__(), timeout=3)
    finally:
        await generator.aclose()  # 模拟客户端断开 → finally 退订
    await asyncio.sleep(0.02)
    assert job_events_module.hub._watcher is None  # 无人订阅后监视协程停转

    data_line = next(line for line in event_chunk.splitlines() if line.startswith("data:"))
    payload = json.loads(data_line.removeprefix("data: "))
    if business_rbac:
        assert payload == {}  # Invalidate the list without disclosing another business's IDs.
    else:
        assert payload["changed"] == ["job:a"]
        assert payload["removed"] == []


@pytest.mark.external
@pytest.mark.asyncio
async def test_control_fingerprints_reads_real_tables() -> None:
    """指纹面真实读表（jobs status/payload + executions status/started_at）。"""
    from service.job_events import control_fingerprints
    from service.workflow_repository import repository

    job_id = f"job-{uuid.uuid4().hex[:8]}"
    execution_id = f"exec-{uuid.uuid4().hex[:8]}"
    repository.save_job(
        {
            "id": job_id,
            "name": "指纹探测任务",
            "taskType": "extract",
            "definitionId": "schema-extract-probe",
            "status": "启用",
            "schedule": {"kind": "once"},
            "createdAt": "2026-09-17T12:00:00",
        }
    )
    repository.save_execution(
        {
            "id": execution_id,
            "definitionId": "schema-extract-probe",
            "workflowId": f"wf-{job_id}",
            "status": "RUNNING",
            "startedAt": "2026-09-17T12:00:01",
            "payload": {},
        }
    )
    try:
        fingerprints = control_fingerprints()
        assert f"job:{job_id}" in fingerprints
        assert f"exec:{execution_id}" in fingerprints
        assert fingerprints[f"job:{job_id}"][0] == "启用"
        assert fingerprints[f"exec:{execution_id}"][0] == "RUNNING"
    finally:
        repository.delete_job(job_id)
        from sqlalchemy import delete as sa_delete

        from service.workflow_models import WorkflowExecution
        from service.workflow_repository import workflow_session_scope

        with workflow_session_scope() as session:
            session.execute(
                sa_delete(WorkflowExecution).where(WorkflowExecution.id == execution_id)
            )
