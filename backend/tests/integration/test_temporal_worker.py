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
