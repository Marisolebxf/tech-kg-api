from __future__ import annotations

from uuid import uuid4

import pytest
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from service.temporal_runtime import temporal_runtime
from service.temporal_workflows import ACTIVITIES, WORKFLOW_CLASSES
from service.workflow_operations import workflow_operations_service
from service.workflow_repository import repository


@pytest.mark.external
async def test_worker_runs_entity_relation_and_uploaded_python_workflows(tmp_path, monkeypatch):
    """启动 Temporal 测试服务与真实 Worker，覆盖内置工作流和上传脚本工作流。"""
    monkeypatch.setenv("WORKFLOW_SCRIPT_DIR", str(tmp_path / "scripts"))
    repository.reset_for_tests()
    python_definition = workflow_operations_service.create_python_definition(
        "triple.py",
        b"def workflow(payload):\n    return {'value': payload['value'] * 3}\n",
        "workflow",
        "python-triple",
        "Python 三倍工作流",
    )
    failing_definition = workflow_operations_service.create_python_definition(
        "failing.py",
        b"def workflow(payload):\n    raise ValueError('intentional failure')\n",
        "workflow",
        "python-failing",
        "Python 失败工作流",
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

            tracked_workflow_id = f"tracked-{uuid4().hex}"
            tracked_execution = temporal_runtime.execution_record(
                "entity-paper",
                {
                    "workflowId": tracked_workflow_id,
                    "runId": None,
                    "status": "RUNNING",
                },
                {"recordId": "P-TRACKED"},
            )
            repository.save_execution(tracked_execution)
            await environment.client.execute_workflow(
                "kg.entity.paper",
                {
                    "recordId": "P-TRACKED",
                    "_control": {"workflowId": tracked_workflow_id},
                },
                id=tracked_workflow_id,
                task_queue=task_queue,
            )
            assert repository.get_execution(tracked_execution["id"])["status"] == "COMPLETED"

            failed_workflow_id = f"failed-{uuid4().hex}"
            failed_execution = temporal_runtime.execution_record(
                failing_definition["id"],
                {
                    "workflowId": failed_workflow_id,
                    "runId": None,
                    "status": "RUNNING",
                },
                {},
            )
            repository.save_execution(failed_execution)
            with pytest.raises(WorkflowFailureError):
                await environment.client.execute_workflow(
                    "kg.custom.python",
                    {
                        "definitionId": failing_definition["id"],
                        "payload": {},
                        "_control": {"workflowId": failed_workflow_id},
                    },
                    id=failed_workflow_id,
                    task_queue=task_queue,
                )
            failed = repository.get_execution(failed_execution["id"])
            assert failed["status"] == "FAILED"
            assert "intentional failure" in failed["failure"]
