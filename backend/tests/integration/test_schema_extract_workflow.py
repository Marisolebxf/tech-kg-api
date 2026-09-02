"""kg.schema.extract 工作流编排测试（Temporal 测试服务 + 假 activity）。

覆盖：批次并发窗口、游标一次推进、逐行失败 → record_extract_failures、
重跑模式（recordIds）→ resolve_failure_cases 必调、批次失败 → workflow FAILED。
"""

from __future__ import annotations

from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from service.temporal_workflows import SchemaExtractWorkflow

pytestmark = pytest.mark.external

PLAN = {
    "schemaId": "schema-e2e",
    "schemaKey": "e2e",
    "kind": "entity",
    "name": "Widget",
    "label": "Widget",
    "activeProps": ["id", "name"],
    "sources": [
        {
            "id": "bind-1",
            "datasourceId": "ds-1",
            "databaseName": "gkx",
            "tableName": "dwd_widget",
            "pkColumn": "id",
            "timeColumn": "update_time",
            "querySql": None,
        }
    ],
    "scriptPath": "/tmp/fake.py",
    "functionName": "transform",
    "timeoutSeconds": 60,
    "maxInflight": 2,
    "failureCaseCap": 10,
    "indexTimeoutSeconds": 60,
}


def _make_activities(state: dict[str, Any], *, rows_per_batch=3, batches=2, fail_batch=None):
    """假 activity 集：读按游标吐批次；转换对毒行（id=bad）报 failures；记录调用。"""

    @activity.defn(name="load_schema_extract_plan")
    async def load_plan(schema_id: str) -> dict[str, Any]:
        state["load_plan"] = state.get("load_plan", 0) + 1
        return PLAN

    @activity.defn(name="read_source_batch")
    async def read_batch(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("reads", []).append(request)
        if "recordIds" in request:
            rows = [
                {"id": str(rid), "name": f"w{rid}", "update_time": "2026-09-01 00:00:00"}
                for rid in request["recordIds"]
            ]
        else:
            batch_no = state.setdefault("read_seq", 0)
            state["read_seq"] = batch_no + 1
            if batch_no >= batches:
                return {"rows": [], "recordIds": [], "maxTime": None, "maxPk": None}
            rows = [
                {
                    "id": str(batch_no * rows_per_batch + i),
                    "name": f"w{batch_no}_{i}",
                    "update_time": f"2026-09-01 00:0{batch_no}:00",
                }
                for i in range(rows_per_batch)
            ]
        return {
            "rows": rows,
            "recordIds": [str(r["id"]) for r in rows],
            "maxTime": "2026-09-01 00:05:00",
            "maxPk": rows[-1]["id"] if rows else None,
        }

    @activity.defn(name="execute_transform")
    async def transform(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("transforms", []).append(len(request.get("rows") or []))
        entities = []
        failures = []
        for row in request.get("rows") or []:
            if row["id"] == "bad":
                failures.append({"recordId": "bad", "error": "ValueError: 毒行"})
            else:
                entities.append({"id": f"widget_{row['id']}", "props": {"name": row["name"]}})
        if fail_batch is not None and len(state["transforms"]) >= fail_batch:
            raise RuntimeError("批次脚本崩溃")
        return {"entities": entities, "failures": failures}

    @activity.defn(name="write_records")
    async def write_records(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("writes", []).append(len(request.get("records") or []))
        return {"written": len(request.get("records") or [])}

    @activity.defn(name="advance_schema_extract_watermark")
    async def advance(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("advances", []).append(request)
        return {"ok": True}

    @activity.defn(name="detect_extract_collisions")
    async def collisions(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("collisions_calls", []).append(len(request.get("records") or []))
        return {"collisions": 0}

    @activity.defn(name="record_extract_failures")
    async def record_failures(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("record_failures", []).extend(request.get("failures") or [])
        return {"recorded": len(request.get("failures") or [])}

    @activity.defn(name="resolve_failure_cases")
    async def resolve(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("resolve", []).append(request)
        return {"resolved": 1, "refailed": 0, "recreated": 0}

    @activity.defn(name="build_entity_index")
    async def build_index(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("index", []).append(request)
        return {"reindexed": {"entityTypes": request.get("entityTypes")}}

    return [
        load_plan,
        read_batch,
        transform,
        write_records,
        advance,
        collisions,
        record_failures,
        resolve,
        build_index,
    ]


async def _run(client, task_queue, request):
    return await client.execute_workflow(
        SchemaExtractWorkflow.run,
        request,
        id=f"extract-{activity.__name__}-{id(request):x}",
        task_queue=task_queue,
    )


@pytest.mark.asyncio
class TestSchemaExtractOrchestration:
    async def test_batches_watermark_and_failure_cases(self):
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-1",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=3, batches=2),
            ):
                result = await _run(
                    env.client,
                    "t-1",
                    {
                        "schemaId": "schema-e2e",
                        "graphSpace": "dev2",
                        "batchSize": 3,
                        "triggerSource": "MANUAL",
                    },
                )
        assert result["status"] == "completed"
        assert result["failures"]["count"] == 0
        # 2 批 × 3 行 = 6 行；写图按行数累计
        assert sum(state["writes"]) == 6
        # 游标只推进一次（全部批次成功后）
        assert len(state.get("advances", [])) == 1
        # 实体默认重建索引 + 冲突检测按批调用
        assert state.get("index")
        assert len(state.get("collisions_calls", [])) >= 2

    async def test_poison_rows_go_to_failure_cases(self):
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-2",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=1, batches=1),
            ):
                # 直接注入毒行：读 activity 吐一行 id=bad
                result = await _run(
                    env.client,
                    "t-2",
                    {
                        "schemaId": "schema-e2e",
                        "graphSpace": "dev2",
                        "batchSize": 5,
                        "recordIdsBySource": {"bind-1": ["bad"]},
                        "rerunCaseIds": ["MR-1"],
                        "rerunOfExecutionId": "EXEC-1",
                        "triggerSource": "RERUN",
                    },
                )
        assert result["status"] == "completed"
        assert result["failures"]["count"] == 1
        # 重跑模式：resolve 必调且拿到失败键
        assert state["resolve"]
        assert state["resolve"][0]["failures"][0]["recordId"] == "bad"
        # 重跑不推游标、不重建索引
        assert state.get("advances") in (None, [])
        assert state.get("index") in (None, [])

    async def test_batch_crash_fails_workflow_and_skips_advance(self):
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-3",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=2, batches=3, fail_batch=2),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-3",
                        {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 2},
                    )
        # 正常模式批次崩溃 → workflow FAILED，游标不推进
        assert state.get("advances") in (None, [])
        assert state.get("record_failures") in (None, [])
