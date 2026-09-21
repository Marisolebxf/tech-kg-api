"""图谱构建（Job / 执行 / 调度）对抗性单测：模拟全部外部 IO，验证状态机语义。

覆盖四类可模拟输入：
- Temporal 不可用（start/create_schedule/pause_schedule 抛错 → QUEUED / LOCAL_SAVED 降级）
- Temporal 正常但状态陈旧（惰性复核链路）
- 存量 legacy 任务（D2 下线的 single/chain/upload 行）
- 调度配置输入（cron 串、update-policy 表单）

标记约定：
- 普通用例：当前语义即设计意图（有注释/文档支撑），断言现状。
- xfail 用例：当前实现缺失的守卫（期望行为），修复后应转为通过。
"""

from __future__ import annotations

from typing import Any

import pytest

from service.workflow_jobs import WorkflowJobError, WorkflowJobService
from service.workflow_operations import WorkflowOperationsService
from tests.unit.test_workflow_jobs import FakeOps, FakeRepo, FakeTemporal, _actor


class FakeOpsQueued(FakeOps):
    """模拟 Temporal 不可用：execute_definition 走 QUEUED 本地降级。"""

    async def execute_definition(self, definition, payload, workflow_id=None, persist_task=False):
        execution = await super().execute_definition(definition, payload, workflow_id, persist_task)
        execution["status"] = "QUEUED"
        execution["dispatchMode"] = "LOCAL_FALLBACK"
        self.execution_by_id[execution["id"]] = execution
        return execution


class TaskRepo(FakeRepo):
    """补齐 task 读写（FakeRepo 只覆盖 job/schedule/execution）。"""

    def __init__(self) -> None:
        super().__init__()
        self.tasks: dict[str, dict[str, Any]] = {}
        self.settings: dict[str, Any] = {}

    def get_execution(self, execution_id):
        for execution in self.saved_executions:
            if execution["id"] == execution_id:
                return execution
        return None

    def save_task(self, task: dict[str, Any]) -> None:
        self.tasks[task["id"]] = task

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def save_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value

    def get_setting(self, key: str):
        return self.settings.get(key)

    def list_schedules(self):
        return list(self.schedules.values())


@pytest.fixture
def env(monkeypatch):
    """与 test_workflow_jobs 同款 fixture，外加 legacy 定义/脚本抽取 fake。"""
    repo = TaskRepo()
    ops = FakeOps()
    temporal = FakeTemporal()
    monkeypatch.setattr("service.workflow_operations.workflow_operations_service", ops)
    monkeypatch.setattr("service.workflow_jobs.temporal_runtime", temporal)
    import service.schema_extraction as schema_extraction

    monkeypatch.setattr(
        schema_extraction, "load_extract_schema", lambda schema_id: {"schemaId": schema_id}
    )
    # create/trigger 的 S3 脚本对象预检 fake 掉（默认放行）
    monkeypatch.setattr(
        schema_extraction, "ensure_extract_script_ready", lambda schema_id: {"schemaId": schema_id}
    )
    monkeypatch.setattr(
        schema_extraction,
        "build_extract_definition",
        lambda info: {
            "id": "schema-extract-widget",
            "name": "widget 抽取",
            "workflowType": "kg.schema.extract",
            "sourceKind": "extract",
            "taskQueue": "tech-kg-workflows",
        },
    )
    monkeypatch.setattr(
        schema_extraction,
        "persist_extract_definition",
        lambda definition: repo.definitions.setdefault(definition["id"], definition),
    )
    monkeypatch.setattr(
        schema_extraction,
        "list_extract_eligible_schemas",
        lambda **_: [{"id": "schema-widget", "schema_key": "widget"}],
    )
    service = WorkflowJobService(repo=repo)
    return service, repo, ops, temporal


async def _make_job(service, **overrides):
    request = {"name": "抽取", "taskType": "extract", "schemaId": "schema-widget"}
    request.update(overrides)
    return await service.create_job(_actor("u1"), request)


# ---------------------------------------------------------------------------
# 1. Temporal 不可用：QUEUED 降级语义
# ---------------------------------------------------------------------------


async def test_queued_execution_allows_retrigger(env, monkeypatch):
    """QUEUED 不算运行中：允许重新触发（设计如此——本地待下发记录不自愈）。"""
    service, repo, _, _ = env
    queued_ops = FakeOpsQueued()
    monkeypatch.setattr("service.workflow_operations.workflow_operations_service", queued_ops)
    job = await _make_job(service)

    first = await service.trigger_job(_actor("u1"), job["id"])
    assert first["status"] == "QUEUED"
    assert repo.get_job(job["id"])["lastExecutionStatus"] == "QUEUED"

    # QUEUED 不在 _NON_TERMINAL_RUNNING 里：再次触发不被 409 拦截
    second = await service.trigger_job(_actor("u1"), job["id"])
    assert second["status"] == "QUEUED"
    assert len(queued_ops.executed) == 2


async def test_queued_execution_leaves_phantom_running_task(env):
    """Temporal 不可用触发时仍会落一条「执行中」task 行，且永不自愈（现状记录）。

    execute_definition(persist_task=True) 在 QUEUED 降级下照建 task（taskStatus=执行中）；
    get_execution 只复核 RUNNING，QUEUED 行永远停在「执行中」——任务中心会出现
    永远不结束的幻影任务，只能靠人工重触发产生新行来"掩盖"。
    """
    repo = TaskRepo()
    real_ops = WorkflowOperationsService(repo=repo)
    definition = {
        "id": "schema-extract-widget",
        "name": "widget 抽取",
        "workflowType": "kg.schema.extract",
        "taskQueue": "tech-kg-workflows",
    }

    async def dead_start(*_args, **_kwargs):
        raise ConnectionError("temporal down")

    import service.temporal_runtime as rt

    orig_start = rt.temporal_runtime.start
    rt.temporal_runtime.start = dead_start  # noqa: SLF001 — 单测替换运行时方法
    try:
        execution = await real_ops.execute_definition(
            definition, {"schemaId": "schema-widget"}, persist_task=True
        )
    finally:
        rt.temporal_runtime.start = orig_start  # type: ignore[method-assign]

    assert execution["status"] == "QUEUED"
    assert execution["dispatchMode"] == "LOCAL_FALLBACK"
    task = repo.get_task(execution["taskId"])
    assert task is not None
    assert task["taskStatus"] == "执行中"

    # 反复 get_execution 也救不回来：QUEUED 不触发 Temporal 复核
    refreshed = await real_ops.get_execution(execution["id"])
    assert refreshed["status"] == "QUEUED"
    assert repo.get_task(execution["taskId"])["taskStatus"] == "执行中"


# ---------------------------------------------------------------------------
# 2. 存量 legacy 任务（D2 下线的 single/chain/upload）
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="trigger_job 未校验 legacy taskType/workflowType：D2 注销 worker 后触发会卡 RUNNING",
    strict=False,
)
async def test_trigger_legacy_tasktype_should_be_rejected(env):
    """期望：legacy 任务触发被显式拒绝；现状：直接下发已注销的 workflowType。

    D2 删掉了 kg.custom.* worker 端 workflow 类，但 trigger_job 只校验 definition
    行存在，不校验 workflowType 是否还有 worker 消费。Temporal start 不会因
    未注册而拒绝，任务会卡在 RUNNING（无 worker 拉起），前端显示「运行中」
    且再触发被 409——僵尸执行。修复：trigger 时拒绝 taskType != extract 或
    workflowType 前缀 kg.custom.。
    """
    service, repo, _, _ = env
    legacy_definition = {
        "id": "def-legacy",
        "name": "旧链",
        "workflowType": "kg.custom.chain",
        "taskQueue": "tech-kg-workflows",
    }
    repo.definitions["def-legacy"] = legacy_definition
    job = {
        "id": "job-legacy000001",
        "name": "存量旧任务",
        "taskType": "chain",
        "definitionId": "def-legacy",
        "definitionIds": ["def-legacy"],
        "schedule": {"kind": "once"},
        "owner": "u1",
        "status": "启用",
        "lastRunAt": "2026-08-01 10:00:00",
        "lastExecutionId": "EXEC-OLD",
        "lastExecutionStatus": "FAILED",
    }
    repo.save_job(job)

    with pytest.raises(WorkflowJobError, match="已下线|extract|legacy"):
        await service.trigger_job(_actor("u1"), job["id"])


async def test_trigger_missing_definition_is_clean_400(env):
    """定义行丢失（如 D2 清理后残留引用）触发 → 明确报错而非半路异常。"""
    service, repo, _, _ = env
    job = await _make_job(service)
    repo.definitions.pop(job["definitionId"])
    with pytest.raises(WorkflowJobError, match="已丢失"):
        await service.trigger_job(_actor("u1"), job["id"])


# ---------------------------------------------------------------------------
# 3. 调度输入校验
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="service 层无 cron 格式校验，垃圾 cron 会建成永不触发的任务", strict=False
)
async def test_create_job_should_reject_invalid_cron(env):
    """期望：cron 格式校验；现状：任意 ≥5 字符的串都能建任务。

    schema 层只有 min_length=5/max_length=100（biz/schemas/workflow_operations.py:150），
    service 层无格式校验。Temporal 可用时 create_schedule 抛错降级 LOCAL_SAVED
    （调度永不触发，仅 dispatchStatus 可见）；Temporal 不可用时同样 LOCAL_SAVED。
    API 直接调用（绕过前端下拉）即可造出永不运行的「周期任务」。
    """
    service, _, _, _ = env
    with pytest.raises(WorkflowJobError):
        await _make_job(service, schedule={"kind": "cron", "cron": "not-a-cron"}, name="坏cron")


async def test_update_job_cron_change_recreates_same_schedule(env):
    """改 cron：同 id 重建 Schedule（真实现是先 delete 后 create），active 保持。"""
    service, repo, _, temporal = env
    job = await _make_job(service, schedule={"kind": "cron", "cron": "0 2 * * *"})
    schedule_id = job["scheduleId"]
    assert temporal.schedules[schedule_id]["cron"] == "0 2 * * *"

    updated = await service.update_job(
        _actor("u1"),
        job["id"],
        {"schedule": {"kind": "cron", "cron": "30 3 * * *"}},
    )
    assert updated["schedule"]["cron"] == "30 3 * * *"
    assert repo.get_schedule(schedule_id)["cron"] == "30 3 * * *"
    assert temporal.schedules[schedule_id]["cron"] == "30 3 * * *"


async def test_update_job_rejects_schedule_kind_switch(env):
    service, _, _, _ = env
    job = await _make_job(service, schedule={"kind": "cron", "cron": "0 2 * * *"})
    with pytest.raises(WorkflowJobError, match="切换调度方式"):
        await service.update_job(_actor("u1"), job["id"], {"schedule": {"kind": "once"}})


# ---------------------------------------------------------------------------
# 4. 惰性复核边界
# ---------------------------------------------------------------------------


async def test_list_jobs_refresh_caps_at_10(env):
    """列表惰性复核上限 10 个 job：>10 个陈旧 RUNNING 时其余保持陈旧（现状记录）。"""
    service, repo, ops, _ = env
    for index in range(12):
        job = await _make_job(service, name=f"任务{index:02d}")
        await service.trigger_job(_actor("u1"), job["id"])
        # Temporal 上其实已全部完成
        ops.execution_by_id[repo.jobs[job["id"]]["lastExecutionId"]]["status"] = "COMPLETED"

    items = await service.list_jobs(_actor("u1"))
    statuses = [item["lastExecutionStatus"] for item in items]
    assert statuses.count("COMPLETED") == 10
    assert statuses.count("RUNNING") == 2  # 超出复核上限，保持陈旧


async def test_pause_with_temporal_down_only_flips_local_flag(env):
    """Temporal 挂掉时暂停 cron 任务：本地标「暂停」，Temporal Schedule 实际未暂停（现状记录）。

    Temporal 恢复后该 Schedule 仍会按 cron 触发（register_scheduled_execution 照常
    落执行行），与界面「已暂停」矛盾。dispatchStatus=LOCAL_SAVED 是唯一线索。
    """
    service, _, _, temporal = env
    job = await _make_job(service, schedule={"kind": "cron", "cron": "0 2 * * *"})

    async def dead_pause(_schedule_id, paused):
        raise ConnectionError("temporal down")

    temporal.pause_schedule = dead_pause  # type: ignore[method-assign]
    paused = await service.set_job_state(_actor("u1"), job["id"], False)

    assert paused["status"] == "暂停"
    assert paused["dispatchStatus"] == "LOCAL_SAVED"
    assert paused["message"]


# ---------------------------------------------------------------------------
# 5. 自动更新策略（task-center /update-policy）的 cron 拼装
# ---------------------------------------------------------------------------


async def test_update_policy_cron_builder_drops_minute_for_interval(env, monkeypatch):
    """每天/每周保留分钟；每12/每6小时丢弃分钟位（现状记录，与任务弹窗的 cron 生成器不一致）。"""
    _, repo, _, temporal = env
    real_ops = WorkflowOperationsService(repo=repo)

    async def fake_create_schedule(_definition, schedule):
        return {**schedule, "dispatchStatus": "TEMPORAL_CREATED"}

    monkeypatch.setattr(
        "service.temporal_runtime.temporal_runtime.create_schedule", fake_create_schedule
    )

    daily = await real_ops.save_update_policy(
        {
            "enabled": True,
            "frequency": "每天",
            "execution_time": "08:30",
            "timezone": "Asia/Shanghai",
            "skip_when_no_changes": False,
        }
    )
    assert daily["policy"]["cron"] == "30 8 * * *"

    every12h = await real_ops.save_update_policy(
        {
            "enabled": True,
            "frequency": "每12小时",
            "execution_time": "08:30",
            "timezone": "Asia/Shanghai",
            "skip_when_no_changes": False,
        }
    )
    # 分钟 30 被丢掉、锚点小时也被丢掉：与前端 JobLaunchDialog 的 cron 语义不一致
    assert every12h["policy"]["cron"] == "0 */12 * * *"
    # nextRunAt 是写死的占位文案，不是时间
    assert every12h["policy"]["nextRunAt"] == "由 Temporal Schedule 计算"
    assert temporal.schedules or repo.schedules  # Schedule 行照常落库


# ---------------------------------------------------------------------------
# 6. 失败重试边界
# ---------------------------------------------------------------------------


async def test_retry_task_on_local_fallback_execution_raises_runtime_error(env):
    """对 QUEUED/LOCAL_FALLBACK 执行点重试：直接打 Temporal reset → RuntimeError（现状记录）。

    更合理的行为是先提示「该执行从未下发，请重新触发任务」。
    """
    repo = TaskRepo()
    real_ops = WorkflowOperationsService(repo=repo)
    repo.save_task(
        {
            "id": "PI-20260916-000001",
            "batchId": "UPD-20260916",
            "taskStatus": "执行中",
            "workflowId": "queued-schema-extract-widget-abc",
            "runId": None,
        }
    )

    async def dead_reset(*_args, **_kwargs):
        raise ConnectionError("temporal down")

    import service.temporal_runtime as rt

    orig_reset = rt.temporal_runtime.reset_workflow
    rt.temporal_runtime.reset_workflow = dead_reset  # noqa: SLF001
    try:
        with pytest.raises(RuntimeError, match="Temporal reset 失败"):
            await real_ops.retry_task("PI-20260916-000001", "manual retry")
    finally:
        rt.temporal_runtime.reset_workflow = orig_reset  # type: ignore[method-assign]


def test_format_workflow_failure_expands_cause_chain():
    """refresh_execution 的失败文案必须展开 cause 链。

    最外层 WorkflowFailureError 只有一句 "Workflow execution failed"，
    activity 抛的业务错误（如脚本对象不存在）在 __cause__ 里——不展开的话
    前端详情页无从得知真实失败原因。
    """
    from service.temporal_runtime import _format_workflow_failure

    inner = ValueError("下载 Schema 脚本失败: NoSuchKey")
    outer = RuntimeError("Workflow execution failed")
    outer.__cause__ = inner
    text = _format_workflow_failure(outer)
    assert "Workflow execution failed" in text
    assert "NoSuchKey" in text
    # 三层链也全部展开，且重复文案去重
    deepest = KeyError("no such key: scripts/paper.py")
    inner.__cause__ = deepest
    text2 = _format_workflow_failure(outer)
    assert "scripts/paper.py" in text2


def test_apply_output_failure_status_maps_completed_with_failures():
    """FUNC-00901：含失败批次的执行按失败标记，output 保留（失败记录列可查）。

    逐行失败由 workflow 正常返回（Temporal COMPLETED），控制面 refresh 时按
    output.failures.count 映射为 FAILED；无失败或非抽取形状不受影响。
    """
    from service.temporal_runtime import _apply_output_failure_status

    def base(output):
        return {"status": "COMPLETED", "message": "工作流执行完成", "output": output}

    failed = {"failures": {"count": 50, "recorded": 50, "truncated": False}}
    mapped = _apply_output_failure_status(base(failed), failed)
    assert mapped["status"] == "FAILED"
    assert "50" in mapped["message"] and "人工审核" in mapped["message"]
    assert mapped["output"] is failed  # 失败记录列依赖 output 透传

    # 截断建案：计数如实（count > recorded 仍按 count 标失败）
    truncated = {"failures": {"count": 2500, "recorded": 2000, "truncated": True}}
    mapped_trunc = _apply_output_failure_status(base(truncated), truncated)
    assert mapped_trunc["status"] == "FAILED"
    assert "2500" in mapped_trunc["message"]

    # 无失败 / 非 extract 输出形状 / 计数非法：保持 COMPLETED
    clean = {"failures": {"count": 0, "recorded": 0, "truncated": False}}
    assert _apply_output_failure_status(base(clean), clean)["status"] == "COMPLETED"
    legacy = {"stages": []}
    assert _apply_output_failure_status(base(legacy), legacy)["status"] == "COMPLETED"
    broken = {"failures": {"count": "many"}}
    assert _apply_output_failure_status(base(broken), broken)["status"] == "COMPLETED"
    assert _apply_output_failure_status(base(None), None)["status"] == "COMPLETED"
