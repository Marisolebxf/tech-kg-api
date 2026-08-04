from __future__ import annotations

from pathlib import Path

import pytest

from service.temporal_runtime import temporal_runtime
from service.temporal_workflows import record_workflow_outcome
from service.workflow_operations import workflow_operations_service
from service.workflow_repository import repository


@pytest.fixture(autouse=True)
def reset_workflow_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKFLOW_SCRIPT_DIR", str(tmp_path / "scripts"))
    repository.reset_for_tests()
    yield
    repository.reset_for_tests()


@pytest.fixture
def fake_temporal(monkeypatch: pytest.MonkeyPatch):
    async def start(definition, payload, workflow_id=None):
        return {
            "workflowId": workflow_id or f"test-{definition['id']}",
            "runId": "run-test-001",
            "status": "RUNNING",
        }

    async def create_schedule(definition, schedule):
        return {**schedule, "dispatchStatus": "TEMPORAL_CREATED"}

    monkeypatch.setattr(temporal_runtime, "start", start)
    monkeypatch.setattr(temporal_runtime, "create_schedule", create_schedule)


async def test_task_center_supports_health_updates_filters_and_trigger(async_client, fake_temporal):
    overview = await async_client.get("/api/v1/task-center/overview")
    assert overview.status_code == 200
    assert overview.json()["data"]["latestBatch"]["id"] == "UPD-20260714"

    tasks = await async_client.get(
        "/api/v1/task-center/tasks",
        params={"status": "等待人工审核", "domain": "论文域", "pageSize": 100},
    )
    assert tasks.status_code == 200
    assert tasks.json()["data"]["total"] >= 1
    assert all(item["taskStatus"] == "等待人工审核" for item in tasks.json()["data"]["items"])

    health = await async_client.get("/api/v1/task-center/data-sources/health")
    assert health.json()["data"]["total"] >= 3

    updates = await async_client.get(
        "/api/v1/task-center/data-sources/updates",
        params={"domain": "论文", "since": "2026-07-14 00:00:00"},
    )
    assert updates.json()["data"]["total"] == 1

    trigger = await async_client.post(
        "/api/v1/task-center/trigger",
        json={"domains": ["论文"], "entities": ["paper"], "relations": ["authorship"]},
    )
    assert trigger.status_code == 202
    data = trigger.json()["data"]
    assert data["execution"]["runId"] == "run-test-001"
    assert data["taskId"] == data["task"]["id"]
    assert data["executionId"] == data["execution"]["id"]
    assert data["statusUrl"].endswith(f"/{data['executionId']}/status")
    assert data["task"]["kind"] == "实体与关系"
    assert data["task"]["dataDomain"] == "论文域"
    assert repository.get_batch(data["task"]["batchId"]) is not None


async def test_update_policy_creates_temporal_schedule(async_client, fake_temporal):
    response = await async_client.put(
        "/api/v1/task-center/update-policy",
        json={
            "enabled": True,
            "frequency": "每6小时",
            "executionTime": "03:30",
            "timezone": "Asia/Shanghai",
            "skipWhenNoChanges": True,
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["policy"]["cron"] == "0 */6 * * *"
    assert data["schedule"]["dispatchStatus"] == "TEMPORAL_CREATED"


async def test_manual_review_filter_modify_retry_complete_and_revoke(async_client, fake_temporal):
    pending = await async_client.get(
        "/api/v1/manual-reviews", params={"status": "待处理", "domain": "论文", "pageSize": 100}
    )
    assert pending.json()["data"]["total"] >= 1

    review_id = "PI-20260714-0003"
    modified = await async_client.put(
        f"/api/v1/manual-reviews/{review_id}/result",
        json={"result": {"relation": "CITES", "approved": True}, "note": "补充 DOI 证据"},
    )
    assert modified.json()["data"]["modifiedResult"]["relation"] == "CITES"

    completed = await async_client.post(
        f"/api/v1/manual-reviews/{review_id}/actions",
        json={
            "actionId": "pass-rerun",
            "note": "证据充分",
            "result": {"approved": True},
            "rerun": True,
        },
    )
    assert completed.json()["data"]["review"]["status"] == "已完成"
    assert completed.json()["data"]["execution"]["status"] == "RUNNING"

    revoked = await async_client.post(
        "/api/v1/manual-reviews/PI-20260714-0004/revoke",
        json={"reason": "源记录已撤回"},
    )
    assert revoked.json()["data"]["status"] == "已撤销"


async def test_custom_definition_and_python_upload_api(async_client, fake_temporal, tmp_path: Path):
    definition = await async_client.post(
        "/api/v1/workflow-system/definitions",
        json={
            "id": "test-config-workflow",
            "name": "测试配置工作流",
            "category": "custom",
            "steps": ["prepare", "validate", "persist"],
        },
    )
    assert definition.json()["data"]["sourceKind"] == "declarative"

    execution = await async_client.post(
        "/api/v1/workflow-system/definitions/test-config-workflow/execute",
        json={"payload": {"recordId": "R-001"}},
    )
    assert execution.json()["data"]["status"] == "RUNNING"

    script = b"def workflow(payload):\n    return {'value': payload['value'] * 2}\n"
    uploaded = await async_client.post(
        "/api/v1/workflow-system/definitions/python",
        data={
            "definition_id": "python-double",
            "function_name": "workflow",
            "name": "Python 倍增工作流",
        },
        files={"file": ("double.py", script, "text/x-python")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["data"]["workflowType"] == "kg.custom.python"
    assert Path(uploaded.json()["data"]["scriptPath"]).is_file()


async def test_definition_conflicts_and_workflow_ids_are_not_overwritten(
    async_client, fake_temporal
):
    payload = {
        "id": "stable-definition",
        "name": "稳定定义",
        "category": "custom",
        "steps": ["prepare"],
    }
    created = await async_client.post("/api/v1/workflow-system/definitions", json=payload)
    assert created.status_code == 201

    duplicate = await async_client.post(
        "/api/v1/workflow-system/definitions", json={**payload, "name": "覆盖尝试"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 409
    assert repository.get_definition("stable-definition")["name"] == "稳定定义"

    execute_payload = {"payload": {"recordId": "R-001"}, "workflowId": "client-workflow-1"}
    first = await async_client.post(
        "/api/v1/workflow-system/definitions/stable-definition/execute",
        json=execute_payload,
    )
    assert first.status_code == 202
    second = await async_client.post(
        "/api/v1/workflow-system/definitions/stable-definition/execute",
        json=execute_payload,
    )
    assert second.status_code == 409


async def test_schedule_trigger_returns_execution_and_task_ids(async_client, fake_temporal):
    created = await async_client.post(
        "/api/v1/workflow-system/definitions/graph-build/schedules",
        json={
            "id": "daily-paper-build",
            "cron": "0 2 * * *",
            "payload": {
                "domains": ["论文"],
                "entities": ["paper"],
                "relations": ["authorship"],
            },
        },
    )
    assert created.status_code == 200

    triggered = await async_client.post(
        "/api/v1/workflow-system/schedules/daily-paper-build/trigger"
    )
    assert triggered.status_code == 202
    data = triggered.json()["data"]
    assert data["taskId"]
    assert data["executionId"]
    assert data["workflowId"] == "test-graph-build"
    assert data["statusUrl"].endswith(f"/{data['executionId']}/status")


async def test_execution_status_refreshes_local_snapshot(async_client, fake_temporal, monkeypatch):
    triggered = await async_client.post(
        "/api/v1/task-center/trigger",
        json={"domains": ["论文"], "entities": ["paper"]},
    )
    execution_id = triggered.json()["data"]["executionId"]

    async def describe_execution(workflow_id, run_id):
        return {"status": "COMPLETED", "output": {"count": 1}, "failure": None}

    monkeypatch.setattr(temporal_runtime, "describe_execution", describe_execution)
    status = await async_client.get(f"/api/v1/workflow-system/executions/{execution_id}/status")
    assert status.status_code == 200
    assert status.json()["data"]["status"] == "COMPLETED"
    assert status.json()["data"]["output"] == {"count": 1}
    task_id = status.json()["data"]["taskId"]
    task = repository.get_task(task_id)
    assert task["taskStatus"] == "执行完成"
    batch = repository.get_batch(task["batchId"])
    assert batch["status"] == "已完成"
    assert batch["progress"] == 100


async def test_local_fallback_is_retried(monkeypatch):
    definition = repository.get_definition("graph-build")

    async def unavailable(definition, payload, workflow_id=None):
        raise RuntimeError("offline")

    monkeypatch.setattr(temporal_runtime, "start", unavailable)
    queued = await workflow_operations_service.execute_definition(
        definition, {"entities": ["paper"]}
    )
    assert queued["status"] == "QUEUED"

    async def available(definition, payload, workflow_id=None):
        return {"workflowId": workflow_id, "runId": "retry-run", "status": "RUNNING"}

    monkeypatch.setattr(temporal_runtime, "start", available)
    assert await workflow_operations_service.retry_queued_executions() == 1
    retried = repository.get_execution(queued["id"])
    assert retried["status"] == "RUNNING"
    assert retried["dispatchMode"] == "TEMPORAL_RETRY"


async def test_worker_outcome_callback_updates_execution_task_and_batch(
    async_client, fake_temporal
):
    triggered = await async_client.post(
        "/api/v1/task-center/trigger",
        json={"domains": ["论文"], "entities": ["paper"]},
    )
    accepted = triggered.json()["data"]

    updated = await record_workflow_outcome(
        {
            "workflowId": accepted["workflowId"],
            "status": "COMPLETED",
            "output": {"persisted": 12},
        }
    )

    assert updated["status"] == "COMPLETED"
    task = repository.get_task(accepted["taskId"])
    assert task["taskStatus"] == "执行完成"
    assert task["output"] == {"persisted": 12}
    assert repository.get_batch(task["batchId"])["progress"] == 100
