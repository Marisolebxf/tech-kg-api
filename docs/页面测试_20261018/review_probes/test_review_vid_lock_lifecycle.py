"""Independent lifecycle probes for a9fe42a8; fake clients only, no external writes."""
import asyncio
import threading

import pytest

from service import temporal_workflows as workflows
from tests.unit.test_write_records_vid_lock import (
    FakeVidLockRedis,
    LockProbeGraphClient,
    _request,
    vid_lock_env,  # noqa: F401 -- imported fixture
)


async def _wait_event(event):
    for _ in range(300):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("probe event timed out")


@pytest.mark.asyncio
async def test_cancelled_activity_must_not_unlock_running_write_thread(vid_lock_env, monkeypatch):
    fetched = threading.Event()
    resume = threading.Event()
    finished = threading.Event()
    original_read = LockProbeGraphClient.execute_read
    original_write = LockProbeGraphClient.execute_write
    first = True

    def delayed_read(self, query, *args, **kwargs):
        nonlocal first
        result = original_read(self, query, *args, **kwargs)
        if query.startswith("FETCH PROP ON") and first:
            first = False
            fetched.set()
            assert resume.wait(5), "probe cleanup did not resume worker"
        return result

    def observe_write(self, query, *args, **kwargs):
        result = original_write(self, query, *args, **kwargs)
        if resume.is_set():
            finished.set()
        return result

    monkeypatch.setattr(LockProbeGraphClient, "execute_read", delayed_read)
    monkeypatch.setattr(LockProbeGraphClient, "execute_write", observe_write)
    first_task = asyncio.create_task(workflows.write_records(_request([
        {"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}
    ])))
    try:
        await _wait_event(fetched)
        first_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_task
        # Current implementation has released its lock while its thread is paused.
        assert FakeVidLockRedis.store == {}
        await workflows.write_records(_request([
            {"id": "v1", "props": {"id": "v1", "h_index": "5"}}
        ]))
        resume.set()
        await _wait_event(finished)
        # Cancelled writer must not erase the later writer's committed column.
        assert LockProbeGraphClient.state["v1"].get("h_index") == "5"
    finally:
        resume.set()
        if not first_task.done():
            first_task.cancel()
            await asyncio.gather(first_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_lease_loss_must_stop_current_chunk_retry(vid_lock_env, monkeypatch):
    from infra.graph_db.exceptions import GraphRequestError

    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.05")
    monkeypatch.setattr(workflows, "_WATERMARK_RETRY_SLEEP_SECONDS", 0.2)
    FakeVidLockRedis.renew_ok = False
    original_write = LockProbeGraphClient.execute_write
    attempts = []

    def transient_first_write(self, query, *args, **kwargs):
        attempts.append(query)
        if len(attempts) == 1:
            raise GraphRequestError("high watermark", status_code=503)
        return original_write(self, query, *args, **kwargs)

    monkeypatch.setattr(LockProbeGraphClient, "execute_write", transient_first_write)
    with pytest.raises(RuntimeError, match="租期丢失"):
        await workflows.write_records(_request([
            {"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}
        ]))
    assert FakeVidLockRedis.renew_calls >= 1
    # Loss was observed during retry sleep, before another INSERT was dispatched.
    assert len(attempts) == 1, "INSERT retried after heartbeat had already reported lock loss"
    assert LockProbeGraphClient.write_stmts == []
