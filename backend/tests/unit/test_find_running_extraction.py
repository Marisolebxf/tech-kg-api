"""find_running_extraction 单测：单 Schema 抽取与 chain 串行链两种形态都要命中。

删属性前的运行中任务拦截（schema_management.delete_property）依赖这里——
chain 执行挂 chain-{hex} 定义下、payload.schemaIds 携带全部串联 Schema，
按 payload 匹配才不会漏拦。
"""

from __future__ import annotations

from typing import Any

import pytest

import service.schema_management as schema_management
from db_model.schema_management import GraphSchemaDefinition


class _FakeRepo:
    def __init__(self, executions: list[dict[str, Any]]) -> None:
        self._executions = executions

    def list_executions(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._executions

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return {"objectName": "论文→专家串行"} if task_id == "task-1" else None


def _definition() -> GraphSchemaDefinition:
    return GraphSchemaDefinition(id="schema-scholar", label="专家（Scholar）")


def _running(payload: dict[str, Any], task_id: str | None = "task-1") -> dict[str, Any]:
    return {"id": "EXEC-1", "status": "RUNNING", "payload": payload, "taskId": task_id}


@pytest.fixture
def guard(monkeypatch: pytest.MonkeyPatch):
    def _install(executions: list[dict[str, Any]]):
        monkeypatch.setattr("service.workflow_repository.repository", _FakeRepo(executions))
        # Temporal 核实直接放行（True=确在运行），单测不碰真实集群
        monkeypatch.setattr(
            schema_management, "_execution_actually_running", lambda execution: True
        )

    return _install


async def test_matches_single_extract_execution(guard):
    guard([_running({"schemaId": "schema-scholar", "triggerSource": "MANUAL"})])
    running = schema_management.find_running_extraction(_definition())
    assert running == {"executionId": "EXEC-1", "name": "论文→专家串行"}


async def test_matches_chain_execution_via_schema_ids(guard):
    """chain 执行 payload 只有 schemaIds（无 schemaId）：包含目标 Schema 即命中。"""
    guard(
        [
            _running(
                {
                    "schemaIds": ["schema-paper", "schema-scholar"],
                    "chainDefinitionId": "chain-ab12cd34ef56",
                    "triggerSource": "MANUAL",
                }
            )
        ]
    )
    running = schema_management.find_running_extraction(_definition())
    assert running == {"executionId": "EXEC-1", "name": "论文→专家串行"}


async def test_returns_none_when_schema_not_in_any_execution(guard):
    guard(
        [
            _running(
                {
                    "schemaIds": ["schema-paper", "schema-patent"],
                    "chainDefinitionId": "chain-ab12cd34ef56",
                }
            )
        ]
    )
    assert schema_management.find_running_extraction(_definition()) is None
