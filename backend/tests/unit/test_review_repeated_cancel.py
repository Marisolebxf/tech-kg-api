"""排空期间二次取消的子进程隔离探针（Codex 三轮探针吸收，语义不变）。

失败模式是事件循环被无让出点忙等冻结——进程内断言会让整个测试进程挂死，
故用 `-m` 子进程 + 2 秒 watchdog（退出码 42）隔离；探针全用假图库/Redis。
文件名必须保持 test_review_repeated_cancel（子进程按 tests.unit 模块路径启动）。
"""

import asyncio
import os
import subprocess
import sys
import threading

import pytest


def _child():
    from service import temporal_workflows as workflows
    from tests.unit.test_write_records_vid_lock import (
        FakeVidLockRedis,
        LockProbeGraphClient,
        _request,
        _wait_event,
        vid_lock_env,
    )

    patches = pytest.MonkeyPatch()
    vid_lock_env.__wrapped__(patches)
    fetched = threading.Event()
    resume = threading.Event()
    original_read = LockProbeGraphClient.execute_read

    def delayed_read(self, query, *args, **kwargs):
        result = original_read(self, query, *args, **kwargs)
        if query.startswith("FETCH PROP ON"):
            fetched.set()
            assert resume.wait(5)
        return result

    patches.setattr(LockProbeGraphClient, "execute_read", delayed_read)

    async def scenario():
        task = asyncio.create_task(
            workflows.write_records(
                _request([{"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}])
            )
        )
        await _wait_event(fetched)
        task.cancel()
        await asyncio.sleep(0.05)
        assert FakeVidLockRedis.store, "first cancellation released the lock"
        print("first cancel entered drain; lock retained", flush=True)

        def watchdog():
            resume.set()
            print("WATCHDOG: loop did not recover after second cancel", flush=True)
            os._exit(42)

        timer = threading.Timer(2, watchdog)
        timer.daemon = True
        timer.start()
        task.cancel()
        print("second cancel sent", flush=True)
        # Correct drain logic must keep the loop responsive and finish cancellation.
        await asyncio.sleep(0.05)
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert FakeVidLockRedis.store == {}
        assert LockProbeGraphClient.write_stmts == []
        timer.cancel()
        print("PASS: second cancellation drained and released safely", flush=True)

    asyncio.run(scenario())
    patches.undo()


def test_repeated_cancel_must_not_spin_or_starve_heartbeat():
    result = subprocess.run(
        [sys.executable, "-m", "tests.unit.test_review_repeated_cancel", "--child"],
        capture_output=True,
        text=True,
        timeout=12,
    )
    assert result.returncode == 0, (
        f"child exit={result.returncode}; repeated cancellation did not drain safely\n"
        f"{result.stdout}\n{result.stderr}"
    )


if __name__ == "__main__" and "--child" in sys.argv:
    _child()
