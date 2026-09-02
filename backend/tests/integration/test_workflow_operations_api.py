from __future__ import annotations

from pathlib import Path

import pytest

from infra.workflow_mysql import WorkflowMySQLClient
from service.temporal_runtime import temporal_runtime
from service.workflow_repository import repository

TEST_CONTROL_DB = "techkg_control_test"


@pytest.fixture(autouse=True)
def reset_workflow_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKFLOW_SCRIPT_DIR", str(tmp_path / "scripts"))
    # 控制面读写都经 infra.workflow_mysql 全局 client；指到独立测试库，
    # 绝不能 reset 真实 techkg_control（会连带 DROP schema 目录表）
    test_client = WorkflowMySQLClient(database=TEST_CONTROL_DB)
    monkeypatch.setattr("infra.workflow_mysql.workflow_mysql_client", test_client)
    monkeypatch.setattr("service.workflow_repository.workflow_mysql_client", test_client)
    monkeypatch.setenv("WORKFLOW_RESET_ALLOW_REAL", "1")  # 测试库允许 DROP 重建
    repository.reset_for_tests()
    yield
    repository.reset_for_tests()
    test_client.dispose()


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
    assert trigger.status_code == 200
    assert trigger.json()["data"]["execution"]["runId"] == "run-test-001"


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


@pytest.mark.parametrize("limit", [0, -1, "abc"])
async def test_execute_definition_rejects_invalid_limit(async_client, fake_temporal, limit):
    response = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json={"payload": {"dry_run": True, "limit": limit}},
    )
    assert response.status_code == 422
    assert response.json()["code"] == 422


async def test_list_executions_filters_by_trigger_source(async_client, fake_temporal):
    """重跑记录视图依赖 triggerSource=RERUN 过滤：只返回重跑执行，非法值 422。"""
    rerun = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json={"payload": {"triggerSource": "RERUN", "rerunCaseIds": ["CASE-1", "CASE-2"]}},
    )
    assert rerun.status_code == 200
    manual = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json={"payload": {"dry_run": True}},
    )
    assert manual.status_code == 200

    only_rerun = await async_client.get(
        "/api/v1/workflow-system/executions", params={"triggerSource": "RERUN"}
    )
    assert only_rerun.status_code == 200
    items = only_rerun.json()["data"]["items"]
    assert [e["id"] for e in items] == [rerun.json()["data"]["id"]]
    assert items[0]["triggerSource"] == "RERUN"
    assert items[0]["payload"]["rerunCaseIds"] == ["CASE-1", "CASE-2"]

    all_items = await async_client.get("/api/v1/workflow-system/executions")
    assert all_items.json()["data"]["total"] == 2

    invalid = await async_client.get(
        "/api/v1/workflow-system/executions", params={"triggerSource": "BOGUS"}
    )
    assert invalid.status_code == 422


@pytest.mark.parametrize("body", [None, {"payload": None}, {"payload": []}])
async def test_execute_definition_uses_http_422_for_invalid_body(async_client, body):
    response = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json=body,
    )
    assert response.status_code == 422
    assert response.json()["code"] == 422


async def test_execute_definition_rejects_duplicate_workflow_id(
    async_client, monkeypatch: pytest.MonkeyPatch
):
    async def duplicate(*args, **kwargs):
        raise RuntimeError("Workflow execution already started")

    monkeypatch.setattr(temporal_runtime, "start", duplicate)
    response = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json={"payload": {"dry_run": True, "limit": 1}, "workflowId": "duplicate-id"},
    )
    assert response.status_code == 409
    assert "工作流已存在" in response.json()["detail"]
