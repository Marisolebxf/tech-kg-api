"""query_step_state 终态短路与 2s 短超时（任务详情 30s 挂死修复）的行为单测。

背景：GET /task-center/tasks/{id} 对已结束 chain/extract workflow 无条件发
Temporal query，无人应答挂满 SDK 默认 30s RPC 超时，前端 axios 20s 中止后
任务详情整页空白。修复后：终态任务一次 RPC 都不发；「执行中」也先 describe
（服务端直答、不经 worker）确认 RUNNING 才 query，且 describe/query 均带
2s rpc_timeout，超时回退落库 steps。
"""

from types import SimpleNamespace

from temporalio.client import WorkflowExecutionStatus

from service import workflow_operations
from service.workflow_operations import STEP_STATE_RPC_TIMEOUT, WorkflowOperationsService


class _FakeHandle:
    """记录调用的 workflow handle 桩：describe 可配状态，query 可配结果/抛错。"""

    def __init__(
        self, *, status=WorkflowExecutionStatus.RUNNING, query_result=None, query_error=None
    ):
        self._status = status
        self._query_result = query_result
        self._query_error = query_error
        self.calls: list[tuple] = []

    async def describe(self, *, rpc_timeout=None):
        self.calls.append(("describe", rpc_timeout))
        return SimpleNamespace(status=self._status)

    async def query(self, name, *, rpc_timeout=None):
        self.calls.append(("query", name, rpc_timeout))
        if self._query_error is not None:
            raise self._query_error
        return self._query_result


class _FakeRuntime:
    def __init__(self, handle: _FakeHandle):
        self._handle = handle

    async def client(self):
        return SimpleNamespace(get_workflow_handle=lambda _workflow_id: self._handle)


def _service_with(handle: _FakeHandle, monkeypatch) -> WorkflowOperationsService:
    monkeypatch.setattr(workflow_operations, "temporal_runtime", _FakeRuntime(handle))
    return WorkflowOperationsService.__new__(WorkflowOperationsService)


def _task(status: str = "执行中", workflow_type: str = "kg.schema.extract.chain") -> dict:
    return {"workflowId": "wf-1", "workflowType": workflow_type, "taskStatus": status}


async def test_terminal_task_skips_temporal_entirely(monkeypatch):
    handle = _FakeHandle()
    service = _service_with(handle, monkeypatch)
    assert await service.query_step_state(_task(status="执行完成")) is None
    assert handle.calls == []  # 终态一次 RPC 都不发，直接走落库 steps 回退


async def test_terminal_error_status_skips_temporal(monkeypatch):
    handle = _FakeHandle()
    service = _service_with(handle, monkeypatch)
    assert await service.query_step_state(_task(status="执行出错")) is None
    assert handle.calls == []


async def test_running_ledger_short_circuits_when_workflow_finished(monkeypatch):
    # 台账卡「执行中」但 workflow 实际已终态（历史超限 TERMINATED/孤儿）：只 describe
    # （服务端直答），不再发注定无人应答的 query
    handle = _FakeHandle(status=WorkflowExecutionStatus.COMPLETED)
    service = _service_with(handle, monkeypatch)
    assert await service.query_step_state(_task()) is None
    assert [call[0] for call in handle.calls] == ["describe"]


async def test_running_task_queries_with_short_timeout(monkeypatch):
    handle = _FakeHandle(query_result={"steps": [{"id": "job-setup", "status": "COMPLETED"}]})
    service = _service_with(handle, monkeypatch)
    state = await service.query_step_state(_task())
    assert state is not None
    assert state["steps"][0]["id"] == "job-setup"
    assert handle.calls == [
        ("describe", STEP_STATE_RPC_TIMEOUT),
        ("query", "get_steps", STEP_STATE_RPC_TIMEOUT),
    ]


async def test_query_timeout_falls_back_to_none(monkeypatch):
    handle = _FakeHandle(query_error=TimeoutError("RPC disconnected"))
    service = _service_with(handle, monkeypatch)
    assert await service.query_step_state(_task()) is None


async def test_single_schema_returns_paused(monkeypatch):
    handle = _FakeHandle(query_result={"paused": True})
    service = _service_with(handle, monkeypatch)
    result = await service.query_step_state(_task(workflow_type="kg.schema.extract"))
    assert result == {"paused": True}
    assert handle.calls[-1] == ("query", "get_progress", STEP_STATE_RPC_TIMEOUT)


async def test_non_extract_task_ignored(monkeypatch):
    handle = _FakeHandle()
    service = _service_with(handle, monkeypatch)
    assert await service.query_step_state(_task(workflow_type="kg.custom.python")) is None
    assert handle.calls == []
