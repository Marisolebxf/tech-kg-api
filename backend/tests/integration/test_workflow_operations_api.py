from __future__ import annotations

import pytest

from infra.workflow_mysql import WorkflowMySQLClient
from service.temporal_runtime import temporal_runtime
from service.workflow_repository import repository

TEST_CONTROL_DB = "techkg_control_test"


@pytest.fixture(autouse=True)
def reset_workflow_state(monkeypatch: pytest.MonkeyPatch):
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


@pytest.fixture
def fake_extract_schemas(monkeypatch: pytest.MonkeyPatch):
    """D3 后 trigger/update-policy 遍历可抽取 schema：测试库无 schema 数据，fake 出一个。"""
    from service import schema_extraction

    info = {
        "id": "schema-widget",
        "schema_key": "widget",
        "kind": "entity",
        "name": "widget",
        "label": "挂件",
        "graph_space": "dev2",
        "property_revision": 1,
        "captured_revision": 1,
    }
    monkeypatch.setattr(
        schema_extraction, "list_extract_eligible_schemas", lambda **_: [dict(info)]
    )


async def _seed_entity_project(client) -> None:
    """D3 删 builtin 定义 seed 后，execute 类测试自建 declarative 定义 entity-project。"""
    resp = await client.post(
        "/api/v1/workflow-system/definitions",
        json={
            "id": "entity-project",
            "name": "项目工作流",
            "category": "custom",
            "steps": ["extract"],
        },
    )
    assert resp.status_code == 200


async def test_task_center_overview_and_trigger(async_client, fake_temporal, fake_extract_schemas):
    overview = await async_client.get("/api/v1/task-center/overview")
    assert overview.status_code == 200
    data = overview.json()["data"]
    # demo seed 已删：latestBatch 为空、changeSummary 从真实 source_updates 聚合（零值）
    assert data["latestBatch"] is None
    assert data["changeSummary"] == {"total": 0, "added": 0, "updated": 0, "deleted": 0}
    assert {"summary", "statusCounts", "updatePolicy"} <= set(data)

    tasks = await async_client.get("/api/v1/task-center/tasks", params={"pageSize": 100})
    assert tasks.status_code == 200
    assert tasks.json()["data"]["total"] == 0

    updates = await async_client.get(
        "/api/v1/task-center/data-sources/updates",
        params={"domain": "论文", "since": "2026-07-14 00:00:00"},
    )
    assert updates.json()["data"]["total"] == 0

    # D3 重指向：trigger 遍历可抽取 schema 逐个启动 kg.schema.extract
    trigger = await async_client.post("/api/v1/task-center/trigger", json={})
    assert trigger.status_code == 200
    data = trigger.json()["data"]
    assert len(data["executions"]) == 1
    assert data["executions"][0]["runId"] == "run-test-001"
    assert data["skipped"] == []


async def test_update_policy_creates_temporal_schedule(
    async_client, fake_temporal, fake_extract_schemas
):
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
    # D3 重指向：每个可抽取 schema 一个 auto-extract-* Schedule
    assert len(data["schedules"]) == 1
    schedule = data["schedules"][0]
    assert schedule["id"] == "auto-extract-schema-widget"
    assert schedule["dispatchStatus"] == "TEMPORAL_CREATED"
    assert schedule["payload"]["schemaId"] == "schema-widget"


async def test_custom_definition_and_upload_endpoints_removed(async_client, fake_temporal):
    """declarative 定义入口保留（C1 范畴）；python/steps/chains 上传端点已随 D2 下线。"""
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
    for path in ("python", "steps", "chains"):
        uploaded = await async_client.post(
            f"/api/v1/workflow-system/definitions/{path}",
            data={"definition_id": "gone", "function_name": "workflow", "name": "gone"},
            files={"file": ("double.py", script, "text/x-python")},
        )
        assert uploaded.status_code in (404, 405), f"{path} 端点应已下线"


@pytest.mark.parametrize("limit", [0, -1, "abc"])
async def test_execute_definition_rejects_invalid_limit(async_client, fake_temporal, limit):
    await _seed_entity_project(async_client)
    response = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json={"payload": {"dry_run": True, "limit": limit}},
    )
    assert response.status_code == 422
    assert response.json()["code"] == 422


async def test_list_executions_filters_by_trigger_source(async_client, fake_temporal):
    """重跑记录视图依赖 triggerSource=RERUN 过滤：只返回重跑执行，非法值 422。"""
    await _seed_entity_project(async_client)
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
    await _seed_entity_project(async_client)

    async def duplicate(*args, **kwargs):
        raise RuntimeError("Workflow execution already started")

    monkeypatch.setattr(temporal_runtime, "start", duplicate)
    response = await async_client.post(
        "/api/v1/workflow-system/definitions/entity-project/execute",
        json={"payload": {"dry_run": True, "limit": 1}, "workflowId": "duplicate-id"},
    )
    assert response.status_code == 409
    assert "工作流已存在" in response.json()["detail"]


@pytest.fixture
def fake_chain_schemas(monkeypatch: pytest.MonkeyPatch):
    """chain 任务创建逐个预检 schema：测试库无 schema/脚本对象，fake 出两个可抽取 schema。

    extract/chain 建任务都走 ensure_extract_script_ready（目录校验 + S3 脚本对象
    存在性探测），一并 fake 掉 S3 探测，委托同一个 _load。
    """
    from service import schema_extraction

    def _load(schema_id):
        return {
            "id": schema_id,
            "schema_key": schema_id.removeprefix("schema-"),
            "name": schema_id.removeprefix("schema-").title(),
            "label": f"{schema_id.removeprefix('schema-')}标签",
            "kind": "entity",
            "graph_space": "dev2",
            "property_revision": 1,
            "captured_revision": 1,
        }

    monkeypatch.setattr(schema_extraction, "load_extract_schema", _load)
    monkeypatch.setattr(schema_extraction, "ensure_extract_script_ready", _load)


async def test_create_and_trigger_chain_job_api(async_client, fake_temporal, fake_chain_schemas):
    """chain 任务 API：创建合成 kg.schema.extract.chain 定义，触发带扁平 schemaIds payload。"""
    created = await async_client.post(
        "/api/v1/workflow-system/jobs",
        json={
            "name": "论文→专家串行",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-scholar"],
            "batchSize": 300,
        },
    )
    assert created.status_code == 200
    job = created.json()["data"]
    assert job["definitionId"].startswith("chain-")
    assert job["schemaIds"] == ["schema-paper", "schema-scholar"]
    assert job["schemaLabels"] == ["paper标签", "scholar标签"]

    definition = repository.get_definition(job["definitionId"])
    assert definition is not None
    assert definition["workflowType"] == "kg.schema.extract.chain"
    assert [s["schemaId"] for s in definition["steps"]] == ["schema-paper", "schema-scholar"]

    triggered = await async_client.post(f"/api/v1/workflow-system/jobs/{job['id']}/trigger")
    assert triggered.status_code == 200
    executions = repository.list_executions(limit=10, job_id=job["id"])
    assert executions
    payload = executions[0]["payload"]
    assert payload["schemaIds"] == ["schema-paper", "schema-scholar"]
    assert payload["chainDefinitionId"] == job["definitionId"]
    assert "schemaId" not in payload


@pytest.mark.parametrize("schema_ids", [["schema-paper"], [f"schema-s{i}" for i in range(21)]])
async def test_create_chain_validation_rejected(
    async_client, fake_temporal, fake_chain_schemas, schema_ids
):
    """chain schemaIds 长度校验（pydantic min 2 / max 20）。

    jobs 端点走平台约定：HTTP 200 + 业务 code 422（main.py 的
    RequestValidationError 包装，仅 definitions/{id}/execute 等白名单走真 422）。
    """
    response = await async_client.post(
        "/api/v1/workflow-system/jobs",
        json={"name": "非法链", "taskType": "chain", "schemaIds": schema_ids},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 422
    assert body["success"] is False
    # 确是 schemaIds 长度校验拦下，而非其他字段
    assert any("schemaIds" in str(e.get("loc")) for e in body["data"])


async def test_create_chain_duplicate_schemas_rejected(
    async_client, fake_temporal, fake_chain_schemas
):
    """chain schemaIds 重复 → 服务层拒绝（400）。"""
    response = await async_client.post(
        "/api/v1/workflow-system/jobs",
        json={
            "name": "重复链",
            "taskType": "chain",
            "schemaIds": ["schema-paper", "schema-paper"],
        },
    )
    assert response.status_code == 400
    assert "重复" in response.json()["detail"]
