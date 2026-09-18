"""WorkflowJobService 单测：fake repo / fake temporal，覆盖创建/触发/隔离/删除。"""

from __future__ import annotations

from typing import Any

import pytest

from service.platform_access import PlatformActor
from service.workflow_jobs import (
    WorkflowJobConflictError,
    WorkflowJobError,
    WorkflowJobPermissionError,
    WorkflowJobService,
)


def _actor(user_id: str, is_admin: bool = False) -> PlatformActor:
    return PlatformActor(
        user_id=user_id,
        username=f"user{user_id}",
        display_name=f"用户{user_id}",
        email="",
        is_admin=is_admin,
    )


class FakeRepo:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.schedules: dict[str, dict[str, Any]] = {}
        # D3 后 builtin/python 定义已删：extract 定义由 fixture 的 _persist 动态写入
        self.definitions: dict[str, dict[str, Any]] = {}
        self.saved_executions: list[dict[str, Any]] = []

    def get_definition(self, definition_id: str) -> dict[str, Any] | None:
        return self.definitions.get(definition_id)

    def save_definition(self, definition: dict[str, Any]) -> None:
        self.definitions[definition["id"]] = definition

    def save_job(self, job: dict[str, Any]) -> None:
        self.jobs[job["id"]] = job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)

    def list_jobs(
        self,
        name: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        items = list(self.jobs.values())
        if name:
            items = [j for j in items if name in j["name"]]
        if status:
            items = [j for j in items if j["status"] == status]
        if task_type:
            items = [j for j in items if j["taskType"] == task_type]
        if owner:
            items = [j for j in items if j["owner"] == owner]
        return items

    def delete_job(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    def save_schedule(self, schedule: dict[str, Any]) -> None:
        self.schedules[schedule["id"]] = schedule

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        return self.schedules.get(schedule_id)

    def delete_schedule(self, schedule_id: str) -> bool:
        return self.schedules.pop(schedule_id, None) is not None

    def list_executions(
        self, limit: int = 100, definition_id=None, schedule_id=None, job_id=None
    ) -> list[dict[str, Any]]:
        items = [e for e in self.saved_executions if e.get("jobId") == job_id]
        return items[:limit]

    def save_execution(self, execution: dict[str, Any]) -> None:
        self.saved_executions.append(execution)

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        return next((e for e in self.saved_executions if e["id"] == execution_id), None)


class FakeOps:
    def __init__(self) -> None:
        self.executed: list[dict[str, Any]] = []
        self.execution_by_id: dict[str, dict[str, Any]] = {}

    async def execute_definition(self, definition, payload, workflow_id=None, persist_task=False):
        self.executed.append({"definition": definition, "payload": payload})
        execution = {
            "id": f"EXEC-{len(self.executed)}",
            "definitionId": definition["id"],
            "workflowId": "wf-1",
            "status": "RUNNING",
            "startedAt": "2026-08-30 10:00:00",
            "jobId": payload.get("jobId"),
        }
        self.execution_by_id[execution["id"]] = execution
        return execution

    async def get_execution(self, execution_id):
        return self.execution_by_id.get(execution_id)


class FakeTemporal:
    def __init__(self) -> None:
        self.schedules: dict[str, dict[str, Any]] = {}
        self.signals: list[tuple[str, str]] = []
        self._client = None

    async def signal_workflow(self, workflow_id, run_id, signal_name):
        self.signals.append((workflow_id, signal_name))

    async def create_schedule(self, definition, schedule):
        self.schedules[schedule["id"]] = schedule
        return {**schedule, "dispatchStatus": "TEMPORAL_CREATED"}

    async def pause_schedule(self, schedule_id, paused):
        assert schedule_id in self.schedules

    async def delete_schedule(self, schedule_id):
        self.schedules.pop(schedule_id, None)


@pytest.fixture
def env(monkeypatch):
    repo = FakeRepo()
    ops = FakeOps()
    temporal = FakeTemporal()
    monkeypatch.setattr("service.workflow_operations.workflow_operations_service", ops)
    monkeypatch.setattr("service.workflow_jobs.temporal_runtime", temporal)
    # extract/chain 任务走 schema_extraction 合成定义；单测里 fake 掉落库，不碰真实 Schema/S3
    import service.schema_extraction as schema_extraction

    def _fake_load(schema_id):
        if schema_id == "schema-ghost":
            raise ValueError("Schema 不存在或未上传脚本")
        # build_extract_chain_definition 真跑：info 需带 id/schema_key/name/label
        return {
            "id": schema_id,
            "schema_key": schema_id.removeprefix("schema-"),
            "name": schema_id.removeprefix("schema-").title(),
            "label": f"{schema_id.removeprefix('schema-')}标签",
            "kind": "entity",
            "sources": [{"id": "src-1"}],
            "script": {"function_name": "transform"},
            "graph_space": "dev2",
        }

    monkeypatch.setattr(schema_extraction, "load_extract_schema", _fake_load)
    # create/trigger 的 S3 脚本对象预检也 fake 掉（extract/chain 都走它，委托 _fake_load；
    # 预检缺失用例单独覆盖）
    monkeypatch.setattr(schema_extraction, "ensure_extract_script_ready", _fake_load)
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

    def _persist(definition):
        # 真实 persist_* 落控制库，trigger_job 按 definitionId 取回
        repo.definitions[definition["id"]] = definition
        return definition

    monkeypatch.setattr(schema_extraction, "persist_extract_definition", _persist)
    # build_extract_chain_definition 保持真跑（校验步序/命名），只 fake 落库
    monkeypatch.setattr(schema_extraction, "persist_extract_chain_definition", _persist)
    service = WorkflowJobService(repo=repo)
    return service, repo, ops, temporal


async def test_create_extract_job(env):
    service, repo, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "论文抽取",
            "taskType": "extract",
            "schemaId": "schema-widget",
            "schedule": {"kind": "once"},
        },
    )
    assert job["definitionId"] == "schema-extract-widget"
    assert job["definitionIds"] == ["schema-extract-widget"]
    assert job["schemaId"] == "schema-widget"
    assert job["status"] == "启用"
    assert repo.jobs[job["id"]]["name"] == "论文抽取"


async def test_create_rejects_legacy_task_types(env):
    """single/upload 已随 D2 下线（chain 已按 Schema 串行形态恢复，单独测试）。"""
    service, _, _, _ = env
    for task_type in ("single", "upload"):
        with pytest.raises(WorkflowJobError, match="extract"):
            await service.create_job(
                _actor("u1"), {"name": "x", "taskType": task_type, "schemaId": "schema-widget"}
            )


async def test_create_rejects_when_script_object_missing(env, monkeypatch):
    """脚本对象在 S3 不存在（系统 Schema 种子占位）时，建任务即报清晰错误。

    不预检的话任务能建成功，但要等 worker 下载脚本重试耗尽（约 100 秒）
    才 FAILED，报错只剩一句 "Workflow execution failed"。
    """
    service, _, _, _ = env
    import service.schema_extraction as schema_extraction

    def _missing(schema_id):
        raise schema_extraction.SchemaConflictError(
            "脚本对象 tech-kg-schema-scripts/paper/transform_papers.py 在对象存储中不存在"
        )

    monkeypatch.setattr(schema_extraction, "ensure_extract_script_ready", _missing)
    with pytest.raises(WorkflowJobError, match="对象存储中不存在"):
        await service.create_job(
            _actor("u1"), {"name": "x", "taskType": "extract", "schemaId": "schema-paper"}
        )


async def test_trigger_rejects_when_script_object_missing(env, monkeypatch):
    """脚本对象缺失的任务触发时被预检拦截，不下发必失败的执行。"""
    service, _, ops, _ = env
    import service.schema_extraction as schema_extraction

    job = await service.create_job(
        _actor("u1"), {"name": "x", "taskType": "extract", "schemaId": "schema-widget"}
    )

    def _missing(schema_id):
        raise schema_extraction.SchemaConflictError(
            "脚本对象 tech-kg-schema-scripts/paper/transform_papers.py 在对象存储中不存在"
        )

    monkeypatch.setattr(schema_extraction, "ensure_extract_script_ready", _missing)
    with pytest.raises(WorkflowJobError, match="对象存储中不存在"):
        await service.trigger_job(_actor("u1"), job["id"])
    assert not ops.executed, "预检失败不应下发执行"


async def test_create_chain_job_builds_definition_and_steps(env):
    """chain 任务：合成 kg.schema.extract.chain 定义，job 记 schemaIds/schemaLabels。"""
    service, repo, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "论文→专家串行",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-scholar"],
            "schedule": {"kind": "once"},
            "batchSize": 300,
        },
    )
    assert job["definitionId"].startswith("chain-")
    assert job["definitionIds"] == [job["definitionId"]]
    assert job["schemaIds"] == ["schema-paper", "schema-scholar"]
    assert job["schemaLabels"] == ["paper标签", "scholar标签"]
    assert job["batchSize"] == 300
    definition = repo.definitions[job["definitionId"]]
    assert definition["workflowType"] == "kg.schema.extract.chain"
    assert definition["sourceKind"] == "extract"
    assert [s["schemaId"] for s in definition["steps"]] == ["schema-paper", "schema-scholar"]
    assert definition["name"] == "paper标签 → scholar标签"


async def test_create_chain_requires_two_unique_schemas(env):
    """chain 校验：≥2 个、不重复、逐个可抽取。"""
    service, _, _, _ = env
    with pytest.raises(WorkflowJobError, match="至少选择 2 个"):
        await service.create_job(
            _actor("u1"),
            {"name": "x", "taskType": "chain", "schemaIds": ["schema-paper"]},
        )
    with pytest.raises(WorkflowJobError, match="不能包含重复"):
        await service.create_job(
            _actor("u1"),
            {"name": "x", "taskType": "chain", "schemaIds": ["schema-paper", "schema-paper"]},
        )
    with pytest.raises(WorkflowJobError, match="不可抽取"):
        await service.create_job(
            _actor("u1"),
            {"name": "x", "taskType": "chain", "schemaIds": ["schema-paper", "schema-ghost"]},
        )


async def test_trigger_chain_job_payload(env):
    """chain 触发 payload：扁平 schemaIds/chainDefinitionId，不带 schemaId。"""
    service, _, ops, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "串行",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-scholar"],
            "schedule": {"kind": "once"},
            "batchSize": 200,
        },
    )
    await service.trigger_job(_actor("u1"), job["id"])
    definition, payload = ops.executed[0]["definition"], ops.executed[0]["payload"]
    assert definition["workflowType"] == "kg.schema.extract.chain"
    assert payload["schemaIds"] == ["schema-paper", "schema-scholar"]
    assert payload["chainDefinitionId"] == job["definitionId"]
    assert payload["triggerSource"] == "MANUAL"
    assert payload["batchSize"] == 200
    assert "schemaId" not in payload


async def test_create_chain_cron_job_schedule_payload(env):
    """chain 周期任务：Schedule payload 同为扁平 schemaIds/chainDefinitionId。"""
    service, repo, _, temporal = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "每夜串行",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-scholar"],
            "schedule": {"kind": "cron", "cron": "0 3 * * *"},
        },
    )
    schedule = repo.schedules[job["scheduleId"]]
    assert schedule["payload"]["schemaIds"] == ["schema-paper", "schema-scholar"]
    assert schedule["payload"]["chainDefinitionId"] == job["definitionId"]
    assert schedule["payload"]["jobId"] == job["id"]
    assert job["scheduleId"] in temporal.schedules


async def test_update_chain_job_reorders_steps(env):
    """chain 编辑步序：同 definitionId 原地重建，steps 顺序刷新。"""
    service, repo, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "串行",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-scholar"],
            "schedule": {"kind": "once"},
        },
    )
    old_definition_id = job["definitionId"]
    updated = await service.update_job(
        _actor("u1"),
        job["id"],
        {"schemaIds": ["schema-scholar", "schema-paper", "schema-patent"]},
    )
    assert updated["definitionId"] == old_definition_id
    assert updated["schemaIds"] == ["schema-scholar", "schema-paper", "schema-patent"]
    definition = repo.definitions[old_definition_id]
    assert [s["schemaId"] for s in definition["steps"]] == [
        "schema-scholar",
        "schema-paper",
        "schema-patent",
    ]


async def test_trigger_legacy_chain_job_rejected(env):
    """存量旧链任务（定义 workflowType=kg.custom.chain）触发被拦截并引导重建。"""
    service, repo, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "旧链",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-scholar"],
            "schedule": {"kind": "once"},
        },
    )
    repo.definitions[job["definitionId"]]["workflowType"] = "kg.custom.chain"
    with pytest.raises(WorkflowJobError, match="旧版多脚本串行"):
        await service.trigger_job(_actor("u1"), job["id"])


async def test_create_cron_job_saves_schedule_with_job_id(env):
    service, repo, _, temporal = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "每日抽取",
            "taskType": "extract",
            "schemaId": "schema-widget",
            "schedule": {"kind": "cron", "cron": "0 2 * * *"},
            "graphSpace": "dev",
        },
    )
    assert job["scheduleId"] == f"{job['id']}-sched"
    schedule = repo.schedules[job["scheduleId"]]
    assert schedule["payload"]["jobId"] == job["id"]
    assert schedule["payload"]["graph_space"] == "dev"
    assert job["scheduleId"] in temporal.schedules


async def test_trigger_job_sends_selectors_and_job_id(env):
    service, _, ops, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "带配置",
            "taskType": "extract",
            "schemaId": "schema-widget",
            "schedule": {"kind": "once"},
            "graphSpace": "dev",
            "mysqlDatasourceId": "MYSQL-1",
        },
    )
    execution = await service.trigger_job(_actor("u1"), job["id"])
    payload = ops.executed[0]["payload"]
    assert payload["jobId"] == job["id"]
    assert payload["graph_space"] == "dev"
    assert payload["mysql_datasource_id"] == "MYSQL-1"
    assert execution["jobId"] == job["id"]
    refreshed = service.repo.get_job(job["id"])
    assert refreshed["lastExecutionId"] == "EXEC-1"


async def test_owner_isolation(env):
    service, _, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {"name": "我的任务", "taskType": "extract", "schemaId": "schema-widget"},
    )
    with pytest.raises(WorkflowJobPermissionError):
        service.get_job(_actor("u2"), job["id"])
    with pytest.raises(WorkflowJobPermissionError):
        await service.trigger_job(_actor("u2"), job["id"])
    # 非管理员列表只见自己的
    assert await service.list_jobs(_actor("u2")) == []
    assert len(await service.list_jobs(_actor("u1"))) == 1
    # 管理员可见全部
    assert len(await service.list_jobs(_actor("admin", is_admin=True))) == 1


async def test_delete_job_removes_schedule(env):
    service, repo, _, temporal = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "周期",
            "taskType": "extract",
            "schemaId": "schema-widget",
            "schedule": {"kind": "cron", "cron": "0 2 * * *"},
        },
    )
    schedule_id = job["scheduleId"]
    assert await service.delete_job(_actor("u1"), job["id"]) is True
    assert repo.get_job(job["id"]) is None
    assert schedule_id not in temporal.schedules
    assert repo.get_schedule(schedule_id) is None


async def test_set_job_state_once_job_toggles_local_status(env):
    """once 任务也支持暂停/恢复：无 Schedule，纯本地标记（暂停 = 拒绝手动触发）。"""
    service, repo, _, temporal = env
    job = await service.create_job(
        _actor("u1"),
        {"name": "一次性", "taskType": "extract", "schemaId": "schema-widget"},
    )
    paused = await service.set_job_state(_actor("u1"), job["id"], False)
    assert paused["status"] == "暂停"
    assert "scheduleId" not in repo.jobs[job["id"]]
    assert temporal.schedules == {}
    resumed = await service.set_job_state(_actor("u1"), job["id"], True)
    assert resumed["status"] == "启用"

    cron_job = await service.create_job(
        _actor("u1"),
        {
            "name": "周期",
            "taskType": "extract",
            "schemaId": "schema-widget",
            "schedule": {"kind": "cron", "cron": "0 2 * * *"},
        },
    )
    paused_cron = await service.set_job_state(_actor("u1"), cron_job["id"], False)
    assert paused_cron["status"] == "暂停"
    assert paused_cron["dispatchStatus"] == "TEMPORAL_UPDATED"


async def test_trigger_rejected_while_paused(env):
    service, _, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {"name": "一次性", "taskType": "extract", "schemaId": "schema-widget"},
    )
    await service.set_job_state(_actor("u1"), job["id"], False)
    with pytest.raises(WorkflowJobConflictError, match="恢复"):
        await service.trigger_job(_actor("u1"), job["id"])


async def test_trigger_rejected_while_running_and_allowed_after_finish(env):
    service, _, ops, _ = env
    job = await service.create_job(
        _actor("u1"),
        {"name": "一次性", "taskType": "extract", "schemaId": "schema-widget"},
    )
    await service.trigger_job(_actor("u1"), job["id"])
    with pytest.raises(WorkflowJobConflictError, match="仍在进行中"):
        await service.trigger_job(_actor("u1"), job["id"])

    ops.execution_by_id["EXEC-1"]["status"] = "COMPLETED"
    execution = await service.trigger_job(_actor("u1"), job["id"])
    assert execution["id"] == "EXEC-2"
    assert service.repo.get_job(job["id"])["lastExecutionId"] == "EXEC-2"


async def test_list_jobs_refreshes_stale_running(env):
    """执行已结束但 job.lastExecutionStatus 卡在 RUNNING 时，列表做惰性刷新。"""
    service, repo, ops, _ = env
    job = await service.create_job(
        _actor("u1"),
        {"name": "一次性", "taskType": "extract", "schemaId": "schema-widget"},
    )
    await service.trigger_job(_actor("u1"), job["id"])
    assert repo.jobs[job["id"]]["lastExecutionStatus"] == "RUNNING"

    ops.execution_by_id["EXEC-1"]["status"] = "COMPLETED"
    items = await service.list_jobs(_actor("u1"))
    assert items[0]["lastExecutionStatus"] == "COMPLETED"
    assert repo.jobs[job["id"]]["lastExecutionStatus"] == "COMPLETED"


async def test_pause_running_job_signals_workflow_pause(env):
    """运行中任务点暂停：除本地状态翻转外，向运行中的执行发 pause 信号（步间挂起）。"""
    service, repo, ops, temporal = env
    job = await service.create_job(
        _actor("u1"), {"name": "x", "taskType": "extract", "schemaId": "schema-widget"}
    )
    await service.trigger_job(_actor("u1"), job["id"])
    job = repo.get_job(job["id"])
    assert job["lastExecutionStatus"] == "RUNNING"
    # 真实 execute_definition 会把 execution 落 repo；fake 不落，测试补齐
    repo.save_execution(ops.execution_by_id[job["lastExecutionId"]])

    await service.set_job_state(_actor("u1"), job["id"], False)
    assert len(temporal.signals) == 1
    workflow_id, signal_name = temporal.signals[0]
    assert signal_name == "pause_extraction"
    assert workflow_id == "wf-1"  # FakeOps 固定 workflowId

    await service.set_job_state(_actor("u1"), job["id"], True)
    assert temporal.signals[-1][1] == "resume_extraction"


async def test_pause_idle_job_sends_no_signal(env):
    """无运行中执行时暂停不发信号（没有可挂起的东西）。"""
    service, _, _, temporal = env
    job = await service.create_job(
        _actor("u1"), {"name": "x", "taskType": "extract", "schemaId": "schema-widget"}
    )
    await service.set_job_state(_actor("u1"), job["id"], False)
    assert temporal.signals == []
