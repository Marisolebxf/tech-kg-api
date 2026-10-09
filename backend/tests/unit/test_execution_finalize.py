"""调度执行收尾回写（finalize_scheduled_execution）与状态对账（reconcile_once）单测。"""

from __future__ import annotations

from typing import Any


def _running_execution(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "exec-1",
        "workflowId": "wf-1",
        "runId": "run-1",
        "status": "RUNNING",
        "message": "周期任务自动触发",
        "startedAt": "2026-09-30 22:56:00",
        "definitionId": "schema-extract-program",
        "jobId": "job-1",
        "taskId": "task-1",
    }
    base.update(over)
    return base


class _FakeRepo:
    def __init__(self, execution: dict[str, Any] | None) -> None:
        self.execution = dict(execution) if execution else None
        self.saved: dict[str, Any] | None = None

    def get_execution_by_run(self, run_id: str) -> dict[str, Any] | None:
        if self.execution and self.execution.get("runId") == run_id:
            return dict(self.execution)
        return None

    def save_execution(self, execution: dict[str, Any]) -> None:
        self.saved = dict(execution)

    def list_stale_running_executions(
        self, started_before: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        if self.execution and self.execution.get("status") == "RUNNING":
            return [dict(self.execution)]
        return []


def _patch_common(monkeypatch, repo: _FakeRepo) -> None:
    monkeypatch.setattr("service.workflow_repository.repository", repo)
    from service.workflow_operations import WorkflowOperationsService

    monkeypatch.setattr(
        WorkflowOperationsService, "_sync_task_from_execution", lambda self, e: None
    )
    monkeypatch.setattr("service.temporal_workflows._stamp_job_latest", lambda e: None)


async def test_finalize_writes_completed(monkeypatch):
    from service.temporal_workflows import finalize_scheduled_execution

    repo = _FakeRepo(_running_execution())
    _patch_common(monkeypatch, repo)
    result = await finalize_scheduled_execution(
        {"runId": "run-1", "result": {"status": "completed", "failures": {"count": 0}}}
    )
    assert result == {"ok": True, "status": "COMPLETED"}
    assert repo.saved is not None
    assert repo.saved["status"] == "COMPLETED"
    assert repo.saved["message"] == "工作流执行完成"
    assert repo.saved["completedAt"]


async def test_finalize_failures_become_abnormal(monkeypatch):
    """输出含失败记录时沿用 ABNORMAL 口径（与详情页惰性刷新一致）。"""
    from service.temporal_workflows import finalize_scheduled_execution

    repo = _FakeRepo(_running_execution())
    _patch_common(monkeypatch, repo)
    result = await finalize_scheduled_execution(
        {"runId": "run-1", "result": {"status": "completed", "failures": {"count": 3}}}
    )
    assert result == {"ok": True, "status": "ABNORMAL"}
    assert repo.saved["status"] == "ABNORMAL"


async def test_finalize_failure_path(monkeypatch):
    from service.temporal_workflows import finalize_scheduled_execution

    repo = _FakeRepo(_running_execution())
    _patch_common(monkeypatch, repo)
    result = await finalize_scheduled_execution({"runId": "run-1", "error": "boom"})
    assert result == {"ok": True, "status": "FAILED"}
    assert repo.saved["status"] == "FAILED"
    assert "boom" in repo.saved["message"]


async def test_finalize_idempotent_on_terminal(monkeypatch):
    from service.temporal_workflows import finalize_scheduled_execution

    repo = _FakeRepo(_running_execution(status="COMPLETED"))
    _patch_common(monkeypatch, repo)
    result = await finalize_scheduled_execution({"runId": "run-1", "error": "late"})
    assert result == {"ok": True, "deduped": True}
    assert repo.saved is None


async def test_finalize_missing_execution(monkeypatch):
    from service.temporal_workflows import finalize_scheduled_execution

    repo = _FakeRepo(None)
    _patch_common(monkeypatch, repo)
    assert await finalize_scheduled_execution({"runId": "nope"}) == {
        "ok": False,
        "reason": "execution-missing",
    }


async def test_reconcile_updates_terminal_rows(monkeypatch):
    from service.execution_reconciler import reconcile_once

    repo = _FakeRepo(_running_execution())
    _patch_common(monkeypatch, repo)

    async def _fake_refresh(execution: dict[str, Any]) -> dict[str, Any]:
        return {**execution, "status": "COMPLETED", "message": "工作流执行完成"}

    monkeypatch.setattr(
        "service.temporal_runtime.temporal_runtime.refresh_execution", _fake_refresh
    )
    done = await reconcile_once()
    assert done == 1
    assert repo.saved is not None and repo.saved["status"] == "COMPLETED"


async def test_reconcile_leaves_running_alone(monkeypatch):
    """Temporal 上真在跑的执行 refresh 后仍 RUNNING，不写库。"""
    from service.execution_reconciler import reconcile_once

    repo = _FakeRepo(_running_execution())
    _patch_common(monkeypatch, repo)

    async def _fake_refresh(execution: dict[str, Any]) -> dict[str, Any]:
        return dict(execution)

    monkeypatch.setattr(
        "service.temporal_runtime.temporal_runtime.refresh_execution", _fake_refresh
    )
    assert await reconcile_once() == 0
    assert repo.saved is None
