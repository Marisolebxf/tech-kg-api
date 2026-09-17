"""人工审核「失败重跑日志」数据行：任务日志应携带 payload/output 的真实数据。

背景：kg.schema.extract 无 stages/steps，_sync_task_from_execution 原先只写
通用文案（"执行状态同步：COMPLETED…"），队列页日志弹窗因此没有数据。
"""

from __future__ import annotations

import sys
from typing import Any

try:  # 容器/CI：控制面 MySQL 可达，直接 import
    from service.workflow_operations import (
        WorkflowOperationsService,
        _extract_result_log_lines,
        _rerun_scope_line,
    )
except Exception:  # noqa: BLE001 —— host 无控制面 MySQL：import 期 repository 单例连库会挂，
    # 用占位模块顶过 workflow_repository（本文件全用 FakeRepo，不触控制面）；
    # 导入成功后移除占位，不影响其它测试对真实模块的导入/跳过行为
    import types

    _fake = types.ModuleType("service.workflow_repository")
    _fake.WorkflowRepository = object
    _fake.repository = None
    sys.modules["service.workflow_repository"] = _fake
    from service.workflow_operations import (  # noqa: E402
        WorkflowOperationsService,
        _extract_result_log_lines,
        _rerun_scope_line,
    )

    sys.modules.pop("service.workflow_repository", None)


class _FakeRepo:
    def __init__(self, task: dict[str, Any] | None) -> None:
        self.task = task
        self.saved: dict[str, Any] | None = None

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self.task if self.task and self.task.get("id") == task_id else None

    def save_task(self, task: dict[str, Any]) -> None:
        self.saved = task


def _rerun_execution() -> dict[str, Any]:
    """镜像 dev2 真实重跑执行的 payload/output 形状。"""
    return {
        "id": "EXEC-RERUN1",
        "status": "COMPLETED",
        "taskId": "PI-1",
        "message": "工作流执行完成",
        "payload": {
            "recordIdsBySource": {"source:abc": ["w3", "w4"]},
            "rerunOfExecutionId": "EXEC-ORIG1",
            "triggerSource": "RERUN",
        },
        "output": {
            "sources": [
                {
                    "source": "source:abc",
                    "table": "techkg_e2e.widgets",
                    "batches": 1,
                    "rows": 2,
                    "written": 2,
                    "failed": 0,
                    "watermark": None,
                    "pkCursor": None,
                }
            ],
            "failures": {"count": 0, "recorded": 0, "truncated": False},
        },
    }


def _task(logs: list[str]) -> dict[str, Any]:
    return {"id": "PI-1", "taskStatus": "执行中", "status": "处理中", "logs": list(logs)}


def test_rerun_scope_line_from_payload():
    assert (
        _rerun_scope_line(
            {"recordIdsBySource": {"a": ["1", "2"], "b": ["3"]}, "rerunOfExecutionId": "EXEC-O"}
        )
        == "重跑范围：3 条失败记录（2 个来源），原执行 EXEC-O"
    )
    assert _rerun_scope_line({}) is None
    assert _rerun_scope_line(None) is None
    assert _rerun_scope_line({"recordIdsBySource": {}}) is None


def test_extract_result_log_lines_covers_scope_and_sources():
    lines = _extract_result_log_lines(_rerun_execution())
    assert lines == [
        "重跑范围：2 条失败记录（1 个来源），原执行 EXEC-ORIG1",
        "来源 source:abc（techkg_e2e.widgets）：1 批 / 读 2 行 / 写入 2 / 失败 0",
    ]


def test_extract_result_log_lines_failure_summary_variants():
    execution = _rerun_execution()
    execution["output"]["failures"] = {"count": 2, "recorded": 0, "truncated": False}
    # 重跑模式 recorded=0（仍失败记录由 resolve 重建 case），引导看失败队列
    assert _extract_result_log_lines(execution)[-1] == "失败汇总：2 条（详见人工审核失败队列）"
    execution["output"]["failures"] = {"count": 2, "recorded": 2, "truncated": False}
    assert _extract_result_log_lines(execution)[-1] == "失败汇总：2 条（已落审核 case 2 条）"
    # count=0 不产出失败汇总行
    assert not any("失败汇总" in line for line in _extract_result_log_lines(_rerun_execution()))


def test_sync_appends_data_lines_and_is_idempotent():
    service = WorkflowOperationsService(repo=_FakeRepo(_task([])))
    service._sync_task_from_execution(_rerun_execution())
    logs = service.repo.saved["logs"]
    assert "重跑范围：2 条失败记录（1 个来源），原执行 EXEC-ORIG1" in logs
    assert "来源 source:abc（techkg_e2e.widgets）：1 批 / 读 2 行 / 写入 2 / 失败 0" in logs
    assert service.repo.saved["taskStatus"] == "执行完成"

    # 再次同步（状态已一致的读取路径）不重复累积
    service.repo.task = dict(service.repo.saved)
    service._sync_task_from_execution(_rerun_execution())
    assert service.repo.saved["logs"] == logs


def test_sync_backfills_data_lines_for_already_synced_task():
    """历史执行：状态早已同步、但日志只有通用文案——读取时补数据行。"""
    legacy_logs = ["工作流已下发", "执行状态同步：COMPLETED（output 无 stages，仅回写状态）"]
    service = WorkflowOperationsService(repo=_FakeRepo(_task(legacy_logs)))
    service.repo.task["taskStatus"] = "执行完成"
    service.repo.task["status"] = "已完成"
    service._sync_task_from_execution(_rerun_execution())
    assert service.repo.saved["logs"][:2] == legacy_logs
    assert "重跑范围：2 条失败记录（1 个来源），原执行 EXEC-ORIG1" in service.repo.saved["logs"]


def test_create_task_for_execution_includes_rerun_scope():
    definition = {"id": "extract-x", "name": "抽取", "workflowType": "kg.schema.extract"}
    execution = {"workflowId": "wf-1", "status": "COMPLETED", "message": "工作流已下发"}
    payload = {"recordIdsBySource": {"source:abc": ["w3"]}, "rerunOfExecutionId": "EXEC-O"}
    task = WorkflowOperationsService.create_task_for_execution(definition, execution, payload)
    assert task["logs"] == ["工作流已下发", "重跑范围：1 条失败记录（1 个来源），原执行 EXEC-O"]

    plain = WorkflowOperationsService.create_task_for_execution(
        definition, execution, {"schemaId": "x"}
    )
    assert plain["logs"] == ["工作流已下发"]
