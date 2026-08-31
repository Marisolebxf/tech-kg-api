from __future__ import annotations

from uuid import uuid4

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from infra.workflow_mysql import WorkflowMySQLClient
from service.temporal_workflows import ACTIVITIES, WORKFLOW_CLASSES
from service.workflow_operations import workflow_operations_service
from service.workflow_repository import repository


@pytest.mark.external
async def test_worker_runs_entity_relation_and_uploaded_python_workflows(tmp_path, monkeypatch):
    """启动 Temporal 测试服务与真实 Worker，覆盖内置工作流和上传脚本工作流。"""
    monkeypatch.setenv("WORKFLOW_SCRIPT_DIR", str(tmp_path / "scripts"))
    # 控制面读写都经 infra.workflow_mysql 全局 client；指到独立测试库
    test_client = WorkflowMySQLClient(database="techkg_control_test")
    monkeypatch.setattr("infra.workflow_mysql.workflow_mysql_client", test_client)
    monkeypatch.setattr("service.workflow_repository.workflow_mysql_client", test_client)
    monkeypatch.setenv("WORKFLOW_RESET_ALLOW_REAL", "1")
    repository.reset_for_tests()
    python_definition = workflow_operations_service.create_python_definition(
        "triple.py",
        b"def workflow(payload):\n    return {'value': payload['value'] * 3}\n",
        "workflow",
        "python-triple",
        "Python 三倍工作流",
    )
    task_queue = f"tech-kg-test-{uuid4().hex}"
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=WORKFLOW_CLASSES,
            activities=ACTIVITIES,
        ):
            paper_result = await environment.client.execute_workflow(
                "kg.entity.paper",
                {"recordId": "P-001"},
                id=f"paper-{uuid4().hex}",
                task_queue=task_queue,
            )
            assert paper_result["domain"] == "paper"
            assert len(paper_result["steps"]) == 5

            relation_result = await environment.client.execute_workflow(
                "kg.relation.cooperation",
                {"recordId": "REL-001"},
                id=f"relation-{uuid4().hex}",
                task_queue=task_queue,
            )
            assert relation_result["kind"] == "relation"
            assert relation_result["domain"] == "cooperation"

            graph_result = await environment.client.execute_workflow(
                "kg.graph.build",
                {
                    "batchId": "TEST-BATCH-001",
                    "entities": ["paper"],
                    "relations": ["authorship"],
                },
                id=f"graph-{uuid4().hex}",
                task_queue=task_queue,
            )
            assert [child["domain"] for child in graph_result["children"]] == [
                "paper",
                "authorship",
            ]

            python_result = await environment.client.execute_workflow(
                "kg.custom.python",
                {"definitionId": python_definition["id"], "payload": {"value": 7}},
                id=f"python-{uuid4().hex}",
                task_queue=task_queue,
            )
            assert python_result == {"value": 21}


@pytest.mark.external
async def test_chain_workflow_records_activity_steps_per_script(tmp_path, monkeypatch):
    """kg.custom.chain：每个脚本一个 step，脚本内 activity steps 落 workflow state。

    - 普通 python 脚本：单个「脚本执行」activity（带真实输入输出）；
    - steps 型脚本（kg.custom.steps 定义进链）：manifest 每步一个 activity，
      输出链式传递，修复 steps 型脚本进链后找不到 workflow() 入口的缺陷。
    """
    monkeypatch.setenv("WORKFLOW_SCRIPT_DIR", str(tmp_path / "scripts"))
    test_client = WorkflowMySQLClient(database="techkg_control_test")
    monkeypatch.setattr("infra.workflow_mysql.workflow_mysql_client", test_client)
    monkeypatch.setattr("service.workflow_repository.workflow_mysql_client", test_client)
    monkeypatch.setenv("WORKFLOW_RESET_ALLOW_REAL", "1")
    repository.reset_for_tests()

    plain = workflow_operations_service.create_python_definition(
        "plain_echo.py",
        b"def workflow(payload):\n    return {'echo': payload.get('value')}\n",
        "workflow",
        "plain-echo",
        "普通脚本",
    )
    steps_definition = workflow_operations_service.create_step_pipeline_definition(
        "mini_pipeline.py",
        b"def step_a(payload, ctx):\n"
        b"    return {'a': payload.get('value')}\n\n"
        b"def step_b(payload, ctx):\n"
        b"    prev = ctx.prev_outputs.get('step_a', {})\n"
        b"    return {'b': prev.get('a')}\n",
        [
            {"id": "step_a", "name": "步骤A", "functionName": "step_a", "timeoutSeconds": 30},
            {"id": "step_b", "name": "步骤B", "functionName": "step_b", "timeoutSeconds": 30},
        ],
        "mini-pipeline",
        "两步流水线",
    )
    chain = workflow_operations_service.create_chain_definition(
        "混合链", [plain["id"], steps_definition["id"]], "chain-mixed-test"
    )

    task_queue = f"tech-kg-test-{uuid4().hex}"
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=WORKFLOW_CLASSES,
            activities=ACTIVITIES,
        ):
            result = await environment.client.execute_workflow(
                "kg.custom.chain",
                {"definitionId": chain["id"], "payload": {"value": 7}},
                id=f"chain-{uuid4().hex}",
                task_queue=task_queue,
            )

    assert result["status"] == "completed"
    steps = result["steps"]

    # 普通脚本：单 activity「脚本执行」，带真实输入输出（access 溯源报告会合并进输出）
    plain_state = steps[plain["id"]]
    assert plain_state["status"] == "COMPLETED"
    plain_activities = plain_state["activities"]
    assert set(plain_activities) == {"execute"}
    assert plain_activities["execute"]["name"] == "脚本执行"
    assert plain_activities["execute"]["output"]["echo"] == 7
    assert "access" in plain_activities["execute"]["output"]
    assert plain_activities["execute"]["input"]["value"] == 7

    # steps 型脚本：manifest 两步各一个 activity，输出链式传递
    pipeline_state = steps[steps_definition["id"]]
    assert pipeline_state["status"] == "COMPLETED"
    pipeline_activities = pipeline_state["activities"]
    assert set(pipeline_activities) == {"step_a", "step_b"}
    assert pipeline_activities["step_a"]["status"] == "COMPLETED"
    assert pipeline_activities["step_a"]["name"] == "步骤A"
    assert pipeline_activities["step_a"]["output"] == {"a": 7}
    assert pipeline_activities["step_a"]["attempt"] == 1
    assert pipeline_activities["step_b"]["output"] == {"b": 7}
    # 脚本级输出 = 各 activity 输出汇总（作为 _prevOutputs 传给链上下一脚本）
    assert pipeline_state["output"]["step_a"] == {"a": 7}
    assert pipeline_state["output"]["step_b"] == {"b": 7}
    # 链级 prevOutputs：steps 脚本拿到普通脚本的输出（含 access 报告）
    assert pipeline_activities["step_a"]["input"]["_prevOutputs"][plain["id"]]["echo"] == 7
