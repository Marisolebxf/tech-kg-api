"""WorkflowJobService 单测：fake repo / fake temporal，覆盖创建/触发/隔离/删除。"""

from __future__ import annotations

from typing import Any

import pytest

from service.platform_access import PlatformActor
from service.workflow_jobs import (
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
        self.definitions: dict[str, dict[str, Any]] = {
            "entity-paper": {
                "id": "entity-paper",
                "name": "论文实体抽取",
                "workflowType": "kg.custom.python",
                "sourceKind": "python",
                "taskQueue": "tech-kg-workflows",
            },
            "relation-authored": {
                "id": "relation-authored",
                "name": "撰写关系抽取",
                "workflowType": "kg.custom.python",
                "sourceKind": "python",
                "taskQueue": "tech-kg-workflows",
            },
            "graph-build": {
                "id": "graph-build",
                "name": "图谱构建",
                "workflowType": "kg.graph.build",
                "sourceKind": "builtin",
                "taskQueue": "tech-kg-workflows",
            },
        }
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


class FakeOps:
    def __init__(self) -> None:
        self.chain_calls: list[tuple[str, list[str], str | None]] = []
        self.executed: list[dict[str, Any]] = []

    def create_chain_definition(self, name, definition_ids, definition_id=None):
        self.chain_calls.append((name, definition_ids, definition_id))
        return {
            "id": definition_id or "chain-x",
            "name": name,
            "workflowType": "kg.custom.chain",
            "sourceKind": "chain",
            "taskQueue": "tech-kg-workflows",
        }

    async def execute_definition(self, definition, payload, workflow_id=None, persist_task=False):
        self.executed.append({"definition": definition, "payload": payload})
        return {
            "id": "EXEC-1",
            "definitionId": definition["id"],
            "workflowId": "wf-1",
            "status": "RUNNING",
            "startedAt": "2026-08-30 10:00:00",
            "jobId": payload.get("jobId"),
        }


class FakeTemporal:
    def __init__(self) -> None:
        self.schedules: dict[str, dict[str, Any]] = {}
        self._client = None

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
    service = WorkflowJobService(repo=repo)
    return service, repo, ops, temporal


async def test_create_single_job(env):
    service, repo, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "论文抽取",
            "taskType": "single",
            "definitionId": "entity-paper",
            "schedule": {"kind": "once"},
        },
    )
    assert job["definitionId"] == "entity-paper"
    assert job["definitionIds"] == ["entity-paper"]
    assert job["status"] == "启用"
    assert repo.jobs[job["id"]]["name"] == "论文抽取"


async def test_create_single_requires_python_definition(env):
    service, _, _, _ = env
    with pytest.raises(Exception, match="python"):
        await service.create_job(
            _actor("u1"),
            {"name": "x", "taskType": "single", "definitionId": "graph-build"},
        )


async def test_create_chain_job_creates_chain_definition(env):
    service, repo, ops, _ = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "两步链",
            "taskType": "chain",
            "definitionIds": ["entity-paper", "relation-authored"],
            "schedule": {"kind": "once"},
        },
    )
    assert job["definitionId"].startswith("chain-")
    assert job["definitionIds"] == ["entity-paper", "relation-authored"]
    assert ops.chain_calls[0][1] == ["entity-paper", "relation-authored"]


async def test_create_chain_requires_two_scripts(env):
    service, _, _, _ = env
    with pytest.raises(Exception, match="2 个脚本"):
        await service.create_job(
            _actor("u1"),
            {"name": "x", "taskType": "chain", "definitionIds": ["entity-paper"]},
        )


async def test_create_cron_job_saves_schedule_with_job_id(env):
    service, repo, _, temporal = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "每日抽取",
            "taskType": "single",
            "definitionId": "entity-paper",
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
            "taskType": "single",
            "definitionId": "entity-paper",
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
        {"name": "我的任务", "taskType": "single", "definitionId": "entity-paper"},
    )
    with pytest.raises(WorkflowJobPermissionError):
        service.get_job(_actor("u2"), job["id"])
    with pytest.raises(WorkflowJobPermissionError):
        await service.trigger_job(_actor("u2"), job["id"])
    # 非管理员列表只见自己的
    assert service.list_jobs(_actor("u2")) == []
    assert len(service.list_jobs(_actor("u1"))) == 1
    # 管理员可见全部
    assert len(service.list_jobs(_actor("admin", is_admin=True))) == 1


async def test_delete_job_removes_schedule(env):
    service, repo, _, temporal = env
    job = await service.create_job(
        _actor("u1"),
        {
            "name": "周期",
            "taskType": "single",
            "definitionId": "entity-paper",
            "schedule": {"kind": "cron", "cron": "0 2 * * *"},
        },
    )
    schedule_id = job["scheduleId"]
    assert await service.delete_job(_actor("u1"), job["id"]) is True
    assert repo.get_job(job["id"]) is None
    assert schedule_id not in temporal.schedules
    assert repo.get_schedule(schedule_id) is None


async def test_set_job_state_only_for_cron(env):
    service, _, _, _ = env
    job = await service.create_job(
        _actor("u1"),
        {"name": "一次性", "taskType": "single", "definitionId": "entity-paper"},
    )
    with pytest.raises(Exception, match="暂停"):
        await service.set_job_state(_actor("u1"), job["id"], False)

    cron_job = await service.create_job(
        _actor("u1"),
        {
            "name": "周期",
            "taskType": "single",
            "definitionId": "entity-paper",
            "schedule": {"kind": "cron", "cron": "0 2 * * *"},
        },
    )
    paused = await service.set_job_state(_actor("u1"), cron_job["id"], False)
    assert paused["status"] == "暂停"
