"""Verify real write_records finally closes only after cancelled writer drains."""

import asyncio
import threading

import pytest

from service.temporal_workflows import write_records
from tests.unit.test_write_records_vid_lock import (
    FakeVidLockRedis,
    LockProbeGraphClient,
    _request,
    _wait_event,
    vid_lock_env,  # noqa: F401 -- fixture
)


@pytest.mark.parametrize("stage", ["fetch", "insert"])
async def test_repeated_cancel_closes_client_only_after_worker_drains(
    vid_lock_env,  # noqa: F811 -- 参数名即 fixture 注入点
    monkeypatch,
    stage,
):
    entered = threading.Event()
    resume = threading.Event()
    returned = threading.Event()
    close_observations = []
    method = "execute_read" if stage == "fetch" else "execute_write"
    original = getattr(LockProbeGraphClient, method)

    def paused_call(self, query, *args, **kwargs):
        if stage == "fetch" and not query.startswith("FETCH PROP ON"):
            return original(self, query, *args, **kwargs)
        entered.set()
        assert resume.wait(5)
        result = original(self, query, *args, **kwargs)
        returned.set()
        return result

    def observe_close(self):
        close_observations.append(returned.is_set())

    monkeypatch.setattr(LockProbeGraphClient, method, paused_call)
    monkeypatch.setattr(LockProbeGraphClient, "close", observe_close)
    task = asyncio.create_task(
        write_records(_request([{"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}]))
    )
    try:
        await _wait_event(entered)
        task.cancel()
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.sleep(0.05)
        assert FakeVidLockRedis.store
        assert close_observations == [], "client closed before in-flight thread returned"
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert close_observations == [True]
        assert FakeVidLockRedis.store == {}
    finally:
        resume.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
