"""kg.schema.extract 工作流编排测试（Temporal 测试服务 + 假 activity）。

覆盖：批次并发窗口、游标一次推进、逐行失败 → record_extract_failures、
重跑模式（recordIds）→ resolve_failure_cases 必调、批次失败 → workflow FAILED、
索引构建失败 → workflow FAILED（不再降级成警告，2026-09-29 口径）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from service.temporal_workflows import SchemaExtractChainWorkflow, SchemaExtractWorkflow

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
    # 单步脚本的转换步用中性名（relay 假 activity 按 fn 分发：step_clean/resolve/emit
    # 是多步链专用语义，单步走通用出实体分支）
    "steps": [{"id": "main", "fn": "step_main"}],
    "timeoutSeconds": 60,
    "maxInflight": 2,
    "failureCaseCap": 10,
    "indexTimeoutSeconds": 60,
}

# chain（kg.schema.extract.chain）两环测试计划：alpha 实体全好行；beta 关系带毒行
CHAIN_PLANS = {
    "schema-alpha": {
        **PLAN,
        "schemaId": "schema-alpha",
        "schemaKey": "alpha",
        "name": "Alpha",
        "label": "甲实体",
        "sources": [{**PLAN["sources"][0], "id": "bind-a", "tableName": "dwd_alpha"}],
    },
    "schema-beta": {
        **PLAN,
        "schemaId": "schema-beta",
        "schemaKey": "beta",
        "kind": "relation",
        "name": "Beta",
        "label": "乙关系",
        "sources": [{**PLAN["sources"][0], "id": "bind-b", "tableName": "dwd_beta"}],
    },
}
CHAIN_ROWS = {
    "schema-extract-alpha": [
        {"id": "a1", "name": "甲1", "update_time": "2026-09-01 00:00:00"},
        {"id": "a2", "name": "甲2", "update_time": "2026-09-01 00:01:00"},
    ],
    "schema-extract-beta": [
        {"id": "b1", "name": "乙1", "update_time": "2026-09-01 00:00:00"},
        {"id": "bad", "name": "毒", "update_time": "2026-09-01 00:01:00"},
    ],
}

MULTI_STEP_PLAN = {
    **PLAN,
    "kind": "relation",
    "steps": [
        {"id": "clean", "fn": "step_clean"},
        {"id": "resolve", "fn": "step_resolve"},
        {"id": "emit", "fn": "step_emit"},
    ],
}


def _make_activities(
    state: dict[str, Any],
    *,
    rows_per_batch=3,
    batches=2,
    fail_batch=None,
    fail_plan=False,
    fail_index=False,
    upload_vids=True,
    plan=None,
    pending_review=False,
    pending_response=None,
    fail_pending=False,
):
    """假 activity 集：读按游标吐批次；转换对毒行（id=bad）报 failures；记录调用。

    gray-gate-v2 接线观测：plan 可覆写（如关系计划）、pending_review 让转换吐
    挂起项（走 resolve_pending_entities 双流，pending_response 可定制其响应）；
    完整请求记入 transform_requests/resolve_requests/write_requests/pending_resolved。
    """

    @activity.defn(name="load_schema_extract_plan")
    async def load_plan(schema_id: str | dict[str, Any]) -> dict[str, Any]:
        # business-rbac-context-v1 补丁后 workflow 送的是 {**request, schemaId}（真实
        # activity 签名同为 str | dict），假 activity 同步收编
        if isinstance(schema_id, dict):
            schema_id = schema_id["schemaId"]
        state["load_plan"] = state.get("load_plan", 0) + 1
        if fail_plan:
            raise ValueError("下载 Schema 脚本失败: NoSuchKey")
        return plan or PLAN

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
        state.setdefault("transform_requests", []).append(dict(request))
        records: list[dict[str, Any]] = []
        failures = []
        for row in request.get("rows") or []:
            if row["id"] == "bad":
                failures.append({"recordId": "bad", "error": "ValueError: 毒行"})
            elif request.get("kind") == "relation":
                records.append(
                    {"fromId": f"widget_{row['id']}", "toId": "org_9", "props": {"weight": 1}}
                )
            else:
                records.append({"id": f"widget_{row['id']}", "props": {"name": row["name"]}})
        if fail_batch is not None and len(state["transforms"]) >= fail_batch:
            raise RuntimeError("批次脚本崩溃")
        result: dict[str, Any] = {
            "edges" if request.get("kind") == "relation" else "entities": records,
            "failures": failures,
        }
        if pending_review:
            result["pendingReview"] = [
                {
                    "kind": "entity",
                    "nodeLabel": "Widget",
                    "objectId": "pending_1",
                    "objectName": "待定甲",
                    "candidate": {"name": "待定甲", "props": {"name": "待定甲"}},
                    "sourceTable": "gkx.dwd_widget",
                    "sourceRecordId": "2:inventors:0",
                }
            ]
        return result

    @activity.defn(name="write_records")
    async def write_records(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("writes", []).append(len(request.get("records") or []))
        state.setdefault("write_requests", []).append(dict(request))
        result: dict[str, Any] = {"written": len(request.get("records") or [])}
        if upload_vids and request.get("indexVids"):
            # 模拟真实 activity：vid 清单上传 S3 后只回传 key（增量索引 claim-check）
            result["vidsKey"] = (
                f"runs/mock/{request.get('stepId')}/{request.get('batchIdx')}-"
                f"{request.get('chunkIdx')}/vids.json.gz"
            )
        return result

    @activity.defn(name="resolve_entity_batch")
    async def resolve_entities(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("resolve_requests", []).append(dict(request))
        records = request.get("records") or []
        return {"records": records, "merged": 0, "withheld": 0, "deduped": 0, "new": len(records)}

    @activity.defn(name="resolve_pending_entities")
    async def resolve_pending(request: dict[str, Any]) -> dict[str, Any]:
        # gray-gate-v2 双流：转换带 pendingMode=resolve 时挂起项交本 activity
        # 真实灰区门控处置（假实现只记账，响应可注入 invalid/rewrite 观测下游）
        state.setdefault("pending_resolved", []).append(dict(request))
        if fail_pending:
            # R1 复核收口口径：门控内技术故障（如 DESCRIBE TAG 传输失败）失败
            # 关闭上抛——activity 失败而非记 invalid 静默放行
            raise RuntimeError("DESCRIBE TAG 响应无列（label 存在且 ddl=succeeded）")
        return pending_response or {
            "written": 0,
            "grayCases": 0,
            "skippedInvalidPending": 0,
            "invalidEndpointVids": [],
            "rewriteMap": {},
        }

    @activity.defn(name="record_schema_script_run")
    async def record_script_run(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("script_runs", []).append(request)
        return {"ok": True}

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

    @activity.defn(name="refresh_graph_stats")
    async def refresh_stats(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("stats_jobs", []).append(request)
        return {"submitted": True, "jobId": 99}

    @activity.defn(name="build_entity_index")
    async def build_index(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("index", []).append(request)
        if fail_index:
            raise RuntimeError("实体索引重建失败: Milvus 不可达")
        return {"reindexed": {"entityTypes": request.get("entityTypes")}}

    @activity.defn(name="revert_rerun_failure_cases")
    async def revert_rerun(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("reverts", []).append(request)
        return {"reverted": len(request.get("rerunCaseIds") or [])}

    @activity.defn(name="resolve_execution_llm")
    async def resolve_llm(request: dict[str, Any]) -> dict[str, Any]:
        # business-llm-default-v1 后链首会调真实 LLM 选型 activity，假实现
        # 返回空覆盖（请求原样透传），只记调用次数
        state["resolve_llm"] = state.get("resolve_llm", 0) + 1
        return {}

    @activity.defn(name="finalize_scheduled_execution")
    async def finalize_exec(request: dict[str, Any]) -> dict[str, Any]:
        # MR-SYNC：手动 RERUN 收尾也走 finalize_scheduled_execution（假实现只记账）
        state.setdefault("finalize", []).append(request)
        return {"ok": True, "status": "COMPLETED"}

    return [
        load_plan,
        read_batch,
        transform,
        resolve_entities,
        resolve_pending,
        record_script_run,
        write_records,
        advance,
        collisions,
        record_failures,
        resolve,
        revert_rerun,
        build_index,
        refresh_stats,
        resolve_llm,
        finalize_exec,
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
        # 手动 MANUAL（无 _scheduleId、非 RERUN 载荷）不收尾——执行行由
        # 触发它的 API 请求侧落状态（MR-SYNC 边界）
        assert state.get("finalize") in (None, [])
        # 游标只推进一次（全部批次成功后）
        assert len(state.get("advances", [])) == 1
        # 实体环随环增量索引（方案②a）：索引 activity 收 vid 工件 key 集，不再全量重建
        index_calls = state.get("index") or []
        assert len(index_calls) == 1
        assert index_calls[0]["space"] == "dev2"
        assert sorted(index_calls[0]["vidsKeys"]) == [
            "runs/mock/source:bind-1#main/0-0/vids.json.gz",
            "runs/mock/source:bind-1#main/1-0/vids.json.gz",
        ]
        # gray-gate-v2 新 run 退出 v1 碰撞检测：detect 不再被调（消歧前置判定接管）
        assert state.get("collisions_calls") in (None, [])

    async def test_gray_gate_v2_wiring_policy_and_no_detect(self):
        """gray-gate-v2 接线：新 run（patched 恒 True）下转换带 pendingMode=resolve、
        消歧/写图请求带冻结 decisionPolicy（autoMergeEnabled 恒 false）、detect 不被调。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-gg2",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=3, batches=1),
            ):
                result = await _run(
                    env.client,
                    "t-gg2",
                    {
                        "schemaId": "schema-e2e",
                        "graphSpace": "dev2",
                        "batchSize": 3,
                        "triggerSource": "MANUAL",
                    },
                )
        assert result["status"] == "completed"
        # 转换请求带 pendingMode=resolve（双流：挂起项交 workflow 侧真实门控）
        assert state["transform_requests"] and all(
            r.get("pendingMode") == "resolve" for r in state["transform_requests"]
        )
        # 消歧请求带冻结策略（activity 不读环境改行为，重放确定）
        assert state["resolve_requests"] and all(
            r["decisionPolicy"]["version"] == "gray-gate-v2"
            and r["decisionPolicy"]["autoMergeEnabled"] is False
            for r in state["resolve_requests"]
        )
        # 写图请求同带策略；实体路径不携带关系端点覆写字段
        assert state["write_requests"] and all(
            r.get("decisionPolicy", {}).get("version") == "gray-gate-v2"
            for r in state["write_requests"]
        )
        assert all("invalidEndpointVids" not in r for r in state["write_requests"])
        # 转换未吐挂起项 → resolve_pending_entities 不被调
        assert state.get("pending_resolved") in (None, [])

    async def test_gray_gate_v2_pending_overrides_flow_to_relation_write(self):
        """pending 旁路聚合随写边请求下发：resolve_pending_entities 的端点处置
        （invalid 过滤 / canonical 改写映射）进关系 write_request。"""
        state: dict[str, Any] = {}
        relation_plan = {
            **PLAN,
            "kind": "relation",
            "name": "AuthoredBy",
            "label": "署名",
            "activeProps": ["weight"],
        }
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-gg2-pending",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(
                    state,
                    rows_per_batch=3,
                    batches=1,
                    plan=relation_plan,
                    pending_review=True,
                    pending_response={
                        "written": 0,
                        "grayCases": 0,
                        "skippedInvalidPending": 1,
                        "invalidEndpointVids": ["pending_1"],
                        "rewriteMap": {"pending_2": "org_9"},
                    },
                ),
            ):
                result = await _run(
                    env.client,
                    "t-gg2-pending",
                    {
                        "schemaId": "schema-e2e",
                        "graphSpace": "dev2",
                        "batchSize": 3,
                        "triggerSource": "MANUAL",
                    },
                )
        assert result["status"] == "completed"
        # 挂起项交真实门控 activity（带冻结策略），不再 activity 内强制送审
        assert len(state["pending_resolved"]) == 1
        assert state["pending_resolved"][0]["decisionPolicy"]["version"] == "gray-gate-v2"
        assert [i["objectId"] for i in state["pending_resolved"][0]["pending"]] == ["pending_1"]
        # 聚合的端点处置随关系写边请求下发（write_records 内做三步失败关闭链）
        write_req = state["write_requests"][-1]
        assert write_req["kind"] == "relation"
        assert write_req["decisionPolicy"]["version"] == "gray-gate-v2"
        assert write_req["invalidEndpointVids"] == ["pending_1"]
        assert write_req["rewriteMap"] == {"pending_2": "org_9"}

    async def test_pending_gate_failure_fails_workflow_and_skips_advance(self):
        """R1 复核收口：挂起项门控 activity 技术故障（DESCRIBE TAG 传输失败/
        响应无列）→ 失败关闭上抛 → workflow FAILED、游标不推进——不得记
        invalid 静默放行后继续推水位（假 activity 抛错模拟真实门控上抛）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-gg2-gate",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(
                    state,
                    rows_per_batch=3,
                    batches=1,
                    pending_review=True,
                    fail_pending=True,
                ),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-gg2-gate",
                        {
                            "schemaId": "schema-e2e",
                            "graphSpace": "dev2",
                            "batchSize": 3,
                            "triggerSource": "MANUAL",
                        },
                    )
        assert state["pending_resolved"]  # 门控 activity 确实被调并上抛
        assert state.get("advances") in (None, [])  # 水位不推进
        assert state.get("index") in (None, [])  # 不重建索引

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
        # MR-SYNC：手动 RERUN 收尾必发——执行行终态由 workflow 自报回写，
        # 否则滞留 RUNNING 会被审核队列误报成 RERUN_FAILED
        finalize_calls = state.get("finalize") or []
        assert len(finalize_calls) == 1
        assert finalize_calls[0]["runId"]
        assert finalize_calls[0]["result"]["status"] == "completed"
        # 重跑不推游标、不重建索引
        assert state.get("advances") in (None, [])
        assert state.get("index") in (None, [])

    async def test_rerun_crash_finalizes_execution_as_failed(self):
        """MR-SYNC 失败分支：重跑 workflow 抛错时收尾也必须发出（带 error），不能静默。

        用 load_plan 失败制造真异常（重跑模式的批次失败按设计不炸 workflow——
        整批记失败记录后正常收尾，见 test_poison_rows_go_to_failure_cases）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-2-crash",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=1, batches=1, fail_plan=True),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-2-crash",
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
        finalize_calls = state.get("finalize") or []
        assert len(finalize_calls) == 1
        assert finalize_calls[0]["runId"]
        # workflow 侧拿到的 ActivityError 文案是通用的（真实原因在 cause 里，
        # error 截断后仍非空即可证明失败分支收尾已发出）
        assert finalize_calls[0]["error"]
        # 崩溃路径同时回滚 case 为 OPEN（可再次重跑）
        assert state.get("reverts")

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

    async def test_index_build_failure_fails_workflow(self):
        """索引构建失败不再降级为警告（2026-09-29 用户口径）：重试耗尽后整链 FAILED。

        此前索引 activity 抛错被捕获成 {"degraded": True} 警告、执行仍算成功；
        现在写图完成后索引失败同样把任务打成 FAILED，失败原因带索引报错。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-3-idx",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=2, batches=1, fail_index=True),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-3-idx",
                        {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 2},
                    )
        # 抽取与写图已发生，索引失败把执行打成 FAILED（而非成功+警告）
        assert state.get("writes")
        assert state.get("index")

    async def test_index_incremental_failure_fails_workflow(self):
        """增量路径同口径：vid 工件在、索引 activity 抛错 → 整链 FAILED
        （索引失败即任务 FAILED，不因增量而放松）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-3-idx-inc",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=2, batches=1, fail_index=True),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-3-idx-inc",
                        {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 2},
                    )
        assert state.get("index") and state["index"][0].get("vidsKeys")

    async def test_index_skipped_when_vid_manifest_missing(self):
        """S3 中转未开的栈：write_records 无 vidsKey 回传 → 索引步计划内跳过
        （不触发全量重建、链不失败），摘要给可区分原因。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-3-idx-skip",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=2, batches=1, upload_vids=False),
            ):
                result = await _run(
                    env.client,
                    "t-3-idx-skip",
                    {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 2},
                )
        assert result["status"] == "completed"
        assert state.get("writes")
        assert state.get("index") in (None, [])
        assert result["index"]["mode"] == "skip"
        assert "未留档" in result["index"]["reason"]

    async def test_index_skipped_when_no_new_entities(self):
        """0 写入环不再白跑全量重建：无 vid 工件 → 跳过并给原因，链照常完成。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-3-idx-empty",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=2, batches=0),
            ):
                result = await _run(
                    env.client,
                    "t-3-idx-empty",
                    {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 2},
                )
        assert result["status"] == "completed"
        assert state.get("index") in (None, [])
        assert result["index"]["mode"] == "skip"
        assert result["index"]["reason"] == "本环无新增实体"

    async def test_rerun_crash_reverts_rerunning_cases(self):
        """重跑执行中途崩溃（如脚本对象丢失）：case 回滚 OPEN，不滞留 RERUNING。

        resolve_failure_cases 只在正常结尾调用；崩溃路径必须有人把
        mark_extract_rerun 标记的 RERUNING case 回滚，否则队列不可见、无法重跑。
        """
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-4",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=1, batches=1, fail_plan=True),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-4",
                        {
                            "schemaId": "schema-e2e",
                            "graphSpace": "dev2",
                            "batchSize": 5,
                            "recordIdsBySource": {"bind-1": ["bad"]},
                            "rerunCaseIds": ["MR-1", "MR-2"],
                            "rerunOfExecutionId": "EXEC-1",
                            "triggerSource": "RERUN",
                        },
                    )
        assert state["reverts"][0]["rerunCaseIds"] == ["MR-1", "MR-2"]
        # ActivityError 的 str 不带 cause 链（NoSuchKey 在 __cause__ 里），只断言前缀
        assert state["reverts"][0]["reason"].startswith("重跑执行失败")
        # 崩溃在读取之前：没读批次、也没走到 resolve
        assert state.get("resolve") in (None, [])

    async def test_normal_crash_does_not_touch_rerun_revert(self):
        """正常模式（非重跑）崩溃：不应调用重跑回滚 activity。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-5",
                workflows=[SchemaExtractWorkflow],
                activities=_make_activities(state, rows_per_batch=2, batches=3, fail_plan=True),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-5",
                        {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 2},
                    )
        assert state.get("reverts") in (None, [])


def _make_step_activities(state: dict[str, Any], *, fail_on=None, block_on=None, gate=None):
    """多步链假 activity：step_clean 只出中转数据，step_resolve 出 pending+failures，
    step_emit 出边；记录每次 execute_transform 的请求形状供链路断言。

    block_on + gate：指定步的 transform 阻塞在 gate 事件上（暂停语义测试用）。
    """

    @activity.defn(name="load_schema_extract_plan")
    async def load_plan(schema_id: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(schema_id, dict):
            schema_id = schema_id["schemaId"]
        return MULTI_STEP_PLAN

    @activity.defn(name="read_source_batch")
    async def read_batch(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("read_seq", 0)
        batch_no = state["read_seq"]
        state["read_seq"] = batch_no + 1
        if batch_no >= 1:
            return {"rows": [], "recordIds": [], "maxTime": None, "maxPk": None}
        rows = [
            {"id": "1", "name": "甲", "org": "浙江大学"},
            {"id": "2", "name": "乙", "org": ""},
            {"id": "bad", "name": "毒", "org": "浙江大学"},
        ]
        return {
            "rows": rows,
            "recordIds": [str(r["id"]) for r in rows],
            "maxTime": "2026-09-01 00:05:00",
            "maxPk": "bad",
        }

    @activity.defn(name="execute_transform")
    async def transform(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("transform_calls", []).append(
            {
                "functionName": request["functionName"],
                "stepId": request.get("stepId"),
                "ctxStepId": request.get("ctxStepId"),
                "hasRows": "rows" in request,
                "hasInput": "input" in request,
                "input": request.get("input"),
                "prevOutputs": request.get("prevOutputs"),
            }
        )
        fn = request["functionName"]
        if block_on and gate and fn == block_on:
            state.setdefault("gate_reached", []).append(fn)
        if block_on and gate and fn == block_on:
            gate_sync = gate
            while not gate_sync.is_set():
                await asyncio.sleep(0.05)
        if fail_on == fn:
            raise RuntimeError(f"step {fn} 崩溃")
        if fn == "step_clean":
            # 毒行（id=bad）在这一步报逐行失败
            failures = [{"recordId": "bad", "error": "ValueError: 毒行"}]
            return {
                "cleaned": [r for r in request["rows"] if r["id"] != "bad"],
                "failures": failures,
                "stats": {"cleaned": 2},
            }
        if fn == "step_resolve":
            cleaned = request["input"]["cleaned"]
            resolved = [r for r in cleaned if r["org"]]
            pending = [
                {
                    "kind": "relation",
                    "objectName": r["id"],
                    "reason": "机构名为空",
                    "sourceTable": "gkx.dwd_widget",
                    "sourceRecordId": r["id"],
                }
                for r in cleaned
                if not r["org"]
            ]
            return {"resolved": resolved, "pendingReview": pending}
        # step_emit：从 input 取已解析行出边
        edges = [
            {"fromId": "w_" + r["id"], "toId": "org_x", "props": {"name": r["name"]}}
            for r in request["input"]["resolved"]
        ]
        return {"edges": edges}

    @activity.defn(name="write_records")
    async def write_records(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("writes", []).append(request["records"])
        return {"written": len(request["records"])}

    @activity.defn(name="advance_schema_extract_watermark")
    async def advance(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("advances", []).append(request)
        return {"ok": True}

    @activity.defn(name="detect_extract_collisions")
    async def collisions(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("collisions_calls", []).append(request.get("stepId"))
        return {"collisions": 0}

    @activity.defn(name="record_extract_failures")
    async def record_failures(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("record_failures", []).extend(request.get("failures") or [])
        return {"recorded": len(request.get("failures") or [])}

    @activity.defn(name="resolve_failure_cases")
    async def resolve(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("resolve", []).append(request)
        return {"resolved": 1, "refailed": 0, "recreated": 0}

    @activity.defn(name="resolve_pending_entities")
    async def resolve_pending(request: dict[str, Any]) -> dict[str, Any]:
        # gray-gate-v2 双流：step_resolve 吐的挂起项（机构名为空行）交本 activity
        # 真实灰区门控处置，不再 activity 内强制送审（关系项在真实现中丢弃告警）
        state.setdefault("resolve_pending", []).append(request)
        return {
            "written": 0,
            "grayCases": 0,
            "skippedInvalidPending": 0,
            "invalidEndpointVids": [],
            "rewriteMap": {},
        }

    @activity.defn(name="record_schema_script_run")
    async def record_script_run(request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    @activity.defn(name="refresh_graph_stats")
    async def refresh_stats(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("stats_jobs", []).append(request)
        return {"submitted": True, "jobId": 99}

    @activity.defn(name="build_entity_index")
    async def build_index(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("index", []).append(request)
        return {"reindexed": {}}

    @activity.defn(name="resolve_execution_llm")
    async def resolve_llm(request: dict[str, Any]) -> dict[str, Any]:
        # business-llm-default-v1 链首选型 activity 的假实现：空覆盖原样透传
        return {}

    return [
        load_plan,
        read_batch,
        transform,
        write_records,
        advance,
        collisions,
        record_failures,
        resolve,
        resolve_pending,
        record_script_run,
        build_index,
        refresh_stats,
        resolve_llm,
    ]


@pytest.mark.asyncio
class TestSchemaExtractMultiStep:
    async def test_step_chain_order_payload_and_stats(self):
        """多步链：步序执行、input/prevOutputs 链、任意步出记录、failures 跨步聚合、水位整链推进。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-multi-1",
                workflows=[SchemaExtractWorkflow],
                activities=_make_step_activities(state),
            ):
                result = await _run(
                    env.client,
                    "t-multi-1",
                    {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 5},
                )
        assert result["status"] == "completed"
        calls = state["transform_calls"]
        # 步序执行：clean → resolve → emit，各一次（单批）
        assert [c["functionName"] for c in calls] == ["step_clean", "step_resolve", "step_emit"]
        # 第 1 步带 rows 无 input；第 2/3 步带 input 无 rows
        assert calls[0]["hasRows"] and not calls[0]["hasInput"]
        assert calls[1]["input"]["cleaned"] == [
            {"id": "1", "name": "甲", "org": "浙江大学"},
            {"id": "2", "name": "乙", "org": ""},
        ]
        assert not calls[1]["hasRows"] and calls[2]["input"]["resolved"] == [
            {"id": "1", "name": "甲", "org": "浙江大学"}
        ]
        # ctxStepId：来源级 stepId 不变（水位键），观测 id 带 #stepId
        assert {c["stepId"] for c in calls} == {"source:bind-1"}
        assert [c["ctxStepId"] for c in calls] == [
            "source:bind-1#clean",
            "source:bind-1#resolve",
            "source:bind-1#emit",
        ]
        # prevOutputs 链：第 2 步只看到 clean，第 3 步看到 clean+resolve
        assert set(calls[1]["prevOutputs"]) == {"clean"}
        assert set(calls[2]["prevOutputs"]) == {"clean", "resolve"}
        assert calls[2]["prevOutputs"]["clean"]["stats"] == {"cleaned": 2}
        # 只有 emit 步出了 edges → write_records 只拿到那一步的记录
        assert len(state["writes"]) == 1
        assert [e["fromId"] for e in state["writes"][0]] == ["w_1"]
        # gray-gate-v2 双流：resolve 步的挂起项（机构名为空行）交
        # resolve_pending_entities 真实灰区门控处置，不再 activity 内强制送审
        assert len(state.get("resolve_pending") or []) == 1
        # 分步统计：聚合计数 + COMPLETED 状态 + 步序/起止时间（详情页排序与耗时列）
        for sid, pos, failed in (("clean", 1, 1), ("resolve", 2, 0), ("emit", 3, 0)):
            stat = result["steps"][sid]
            assert stat["position"] == pos
            assert stat["failed"] == failed
            assert stat["status"] == "COMPLETED"
            assert stat["startedAt"] and stat["finishedAt"]
        source_steps = result["sources"][0]["steps"]
        # 核心计数（startedAt/finishedAt 是耗时列展示字段，另行断言存在）
        assert {
            sid: {k: stat[k] for k in ("records", "written", "failed")}
            for sid, stat in source_steps.items()
        } == {
            "clean": {"records": 0, "written": 0, "failed": 1},
            "resolve": {"records": 0, "written": 0, "failed": 0},
            "emit": {"records": 1, "written": 1, "failed": 0},
        }
        assert all(
            stat.get("startedAt") and stat.get("finishedAt") for stat in source_steps.values()
        )
        # 毒行失败（clean 步）经聚合进 T_EXTRACT_FAIL；关系不重建索引
        assert result["failures"]["count"] == 1
        assert state["record_failures"][0]["recordId"] == "bad"
        assert state.get("index") in (None, [])
        # 水位仍整链推进一次
        assert len(state["advances"]) == 1

    async def test_middle_step_crash_fails_workflow_and_skips_advance(self):
        """中间步失败 → workflow FAILED、游标不推进（第 k 步由 Temporal 只重试第 k 步）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-multi-2",
                workflows=[SchemaExtractWorkflow],
                activities=_make_step_activities(state, fail_on="step_resolve"),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run(
                        env.client,
                        "t-multi-2",
                        {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 5},
                    )
        assert state.get("advances") in (None, [])
        # clean 步已执行过（重试只发生在 resolve 步）
        assert [c["functionName"] for c in state["transform_calls"][:2]] == [
            "step_clean",
            "step_resolve",
        ]


def _make_chain_activities(state: dict[str, Any], *, fail_schema: str | None = None):
    """chain 假 activity 集：load_plan 按 schemaId 分发计划，读/转换按 definitionId
    （schema-extract-{schemaKey}）区分两环；fail_schema 传 schemaId（如 schema-alpha），
    其转换批次崩溃。注意 definitionId 用 schemaKey（去 schema- 前缀）拼键，别双拼前缀。"""
    fail_definition = (
        "schema-extract-" + fail_schema.removeprefix("schema-") if fail_schema else None
    )

    @activity.defn(name="load_schema_extract_plan")
    async def load_plan(schema_id: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(schema_id, dict):
            schema_id = str(schema_id["schemaId"])
        state.setdefault("plan_order", []).append(schema_id)
        return CHAIN_PLANS[schema_id]

    @activity.defn(name="read_source_batch")
    async def read_batch(request: dict[str, Any]) -> dict[str, Any]:
        definition_id = request["definitionId"]
        seq = state.setdefault("read_seq", {}).get(definition_id, 0)
        state["read_seq"][definition_id] = seq + 1
        if seq >= 1:
            return {"rows": [], "recordIds": [], "maxTime": None, "maxPk": None}
        rows = CHAIN_ROWS[definition_id]
        return {
            "rows": rows,
            "recordIds": [str(r["id"]) for r in rows],
            "maxTime": "2026-09-01 00:05:00",
            "maxPk": rows[-1]["id"],
        }

    @activity.defn(name="execute_transform")
    async def transform(request: dict[str, Any]) -> dict[str, Any]:
        definition_id = request["definitionId"]
        if fail_definition is not None and definition_id == fail_definition:
            raise RuntimeError(f"{fail_schema} 批次脚本崩溃")
        records, failures = [], []
        for row in request.get("rows") or []:
            if row["id"] == "bad":
                failures.append({"recordId": "bad", "error": "ValueError: 毒行"})
            else:
                records.append({"id": f"rec_{row['id']}", "props": {"name": row["name"]}})
        if request.get("kind") == "relation":
            return {"edges": records, "failures": failures}
        return {"entities": records, "failures": failures}

    @activity.defn(name="write_records")
    async def write_records(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("writes", []).append(request["name"])
        result: dict[str, Any] = {"written": len(request.get("records") or [])}
        if request.get("indexVids"):
            result["vidsKey"] = (
                f"runs/mock/{request.get('stepId')}/{request.get('batchIdx')}-"
                f"{request.get('chunkIdx')}/vids.json.gz"
            )
        return result

    @activity.defn(name="resolve_entity_batch")
    async def resolve_entities(request: dict[str, Any]) -> dict[str, Any]:
        records = request.get("records") or []
        return {"records": records, "merged": 0, "withheld": 0, "deduped": 0, "new": len(records)}

    @activity.defn(name="record_schema_script_run")
    async def record_script_run(request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    @activity.defn(name="advance_schema_extract_watermark")
    async def advance(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("advances", []).append(request["definitionId"])
        return {"ok": True}

    @activity.defn(name="detect_extract_collisions")
    async def collisions(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("collisions_calls", []).append(request.get("stepId"))
        return {"collisions": 0}

    @activity.defn(name="record_extract_failures")
    async def record_failures(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("record_failures", []).extend(request.get("failures") or [])
        return {"recorded": len(request.get("failures") or [])}

    @activity.defn(name="resolve_failure_cases")
    async def resolve(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("resolve", []).append(request)
        return {"resolved": 1, "refailed": 0, "recreated": 0}

    @activity.defn(name="refresh_graph_stats")
    async def refresh_stats(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("stats_jobs", []).append(request)
        return {"submitted": True, "jobId": 99}

    @activity.defn(name="build_entity_index")
    async def build_index(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("index", []).append(request)
        return {"reindexed": {}}

    @activity.defn(name="resolve_execution_llm")
    async def resolve_llm(request: dict[str, Any]) -> dict[str, Any]:
        # business-llm-default-v1 链首选型 activity 的假实现：空覆盖原样透传
        return {}

    return [
        load_plan,
        read_batch,
        transform,
        resolve_entities,
        record_script_run,
        write_records,
        advance,
        collisions,
        record_failures,
        resolve,
        build_index,
        refresh_stats,
        resolve_llm,
    ]


async def _run_chain(client, task_queue, request):
    return await client.execute_workflow(
        SchemaExtractChainWorkflow.run,
        request,
        id=f"chain-{activity.__name__}-{id(request):x}",
        task_queue=task_queue,
    )


@pytest.mark.asyncio
class TestSchemaExtractChain:
    async def test_chain_runs_schemas_sequentially(self):
        """两环串行：顺序执行、每环独立水位/索引、单 transform 也聚合 activities、失败跨环汇总。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-chain-1",
                workflows=[SchemaExtractChainWorkflow],
                activities=_make_chain_activities(state),
            ):
                result = await _run_chain(
                    env.client,
                    "t-chain-1",
                    {
                        "schemaIds": ["schema-alpha", "schema-beta"],
                        "chainDefinitionId": "chain-test000001",
                        "graphSpace": "dev2",
                        "batchSize": 5,
                        "triggerSource": "MANUAL",
                    },
                )
        assert result["status"] == "completed"
        assert result["chain"] is True
        assert result["schemaIds"] == ["schema-alpha", "schema-beta"]
        assert result["definitionId"] == "chain-test000001"
        # 严格串行：alpha 全部跑完才轮到 beta
        assert state["plan_order"] == ["schema-alpha", "schema-beta"]
        # 每环水位各自推进一次（键仍是 schema-extract-{schemaKey}）
        assert state["advances"] == ["schema-extract-alpha", "schema-extract-beta"]
        # 实体环重建索引；关系环不重建。gray-gate-v2 下 detect（v1 碰撞检测）退出
        assert len(state.get("index", [])) == 1
        assert state.get("collisions_calls") in (None, [])
        steps = result["steps"]
        assert list(steps) == ["schema:schema-alpha", "schema:schema-beta"]
        alpha = steps["schema:schema-alpha"]
        assert alpha["status"] == "COMPLETED"
        assert alpha["name"] == "甲实体"
        assert alpha["records"] == 2
        assert alpha["written"] == 2
        assert alpha["failed"] == 0
        # chain 模式 activities：该 Schema 脚本各 @step 转换步（PLAN 单步 main）
        assert alpha["activities"] == {
            "main": {
                "status": "COMPLETED",
                "name": "main",
                "position": 1,
                "records": 2,
                "written": 2,
                "failed": 0,
            }
        }
        beta = steps["schema:schema-beta"]
        assert beta["status"] == "COMPLETED"
        assert beta["records"] == 2
        assert beta["written"] == 1
        assert beta["failed"] == 1
        assert beta["activities"]["main"]["failed"] == 1
        # 毒行失败跨环汇总；写图两环各一次（noRecordId 如实汇报，见 03efe8f7 口径）
        assert result["failures"] == {
            "count": 1,
            "recorded": 1,
            "noRecordId": 0,
            "truncated": False,
        }
        assert state["writes"] == ["Alpha", "Beta"]
        assert state["record_failures"][0]["recordId"] == "bad"

    async def test_pause_signal_suspends_between_steps_and_resume_continues(self):
        """暂停信号：当前步正常结束后挂起（不再执行下一步），恢复后从断点继续。

        Temporal 无原生 pause：workflow 用 signal + wait_condition 在步边界挂起。
        门控第二步：clean 完成 → resolve 阻塞在事件上 → 发暂停 → 放行 resolve →
        resolve 结束后 workflow 应挂在 emit 之前，直到恢复信号。
        """
        state: dict[str, Any] = {}
        gate = asyncio.Event()
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-pause",
                workflows=[SchemaExtractWorkflow],
                activities=_make_step_activities(state, block_on="step_resolve", gate=gate),
            ):
                handle = await env.client.start_workflow(
                    SchemaExtractWorkflow.run,
                    {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 5},
                    id="wf-pause-1",
                    task_queue="t-pause",
                )
                # 等 resolve 步进入阻塞（clean 已完成）
                for _ in range(50):
                    if state.get("gate_reached"):
                        break
                    await asyncio.sleep(0.1)
                assert state.get("gate_reached"), "第二步未进入"

                await handle.signal("pause_extraction")
                gate.set()  # 放行 resolve：它正常结束后 workflow 应挂在 emit 之前
                await asyncio.sleep(1.5)
                described = await handle.describe()
                assert described.status.name == "RUNNING", "挂起期间 workflow 不应结束"
                calls_when_paused = len(state["transform_calls"])
                assert calls_when_paused == 2, (
                    f"挂起点应在 resolve 之后 emit 之前（实际 {calls_when_paused}）"
                )

                await asyncio.sleep(1.0)
                assert len(state["transform_calls"]) == calls_when_paused, (
                    "挂起期间不应有新的转换步执行"
                )

                await handle.signal("resume_extraction")
                result = await asyncio.wait_for(handle.result(), timeout=30)
                assert result["status"] == "completed"
                assert len(state["transform_calls"]) == 3, "恢复后 emit 步应继续执行"

    async def test_chain_aborts_on_first_schema_failure(self):
        """第一环批次崩溃 → workflow FAILED、后续环不再执行、水位全部不推进。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-chain-2",
                workflows=[SchemaExtractChainWorkflow],
                activities=_make_chain_activities(state, fail_schema="schema-alpha"),
            ):
                with pytest.raises(WorkflowFailureError):
                    await _run_chain(
                        env.client,
                        "t-chain-2",
                        {
                            "schemaIds": ["schema-alpha", "schema-beta"],
                            "graphSpace": "dev2",
                            "batchSize": 5,
                        },
                    )
        # 中止语义：beta 从未加载，无写图、无水位推进
        assert state["plan_order"] == ["schema-alpha"]
        assert state.get("writes") in (None, [])
        assert state.get("advances") in (None, [])

    async def test_chain_rejects_rerun_payload(self):
        """chain 拒绝失败记录重跑 payload（重跑只支持单 Schema）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-chain-3",
                workflows=[SchemaExtractChainWorkflow],
                activities=_make_chain_activities(state),
            ):
                with pytest.raises(WorkflowFailureError) as excinfo:
                    await _run_chain(
                        env.client,
                        "t-chain-3",
                        {
                            "schemaIds": ["schema-alpha", "schema-beta"],
                            "recordIdsBySource": {"bind-a": ["a1"]},
                            "rerunCaseIds": ["MR-1"],
                            "triggerSource": "RERUN",
                        },
                    )
        # WorkflowFailureError 的 str 是笼统的 "Workflow execution failed"，
        # 业务错误信息在 cause（ApplicationError.message）
        assert "不支持失败记录重跑" in str(excinfo.value.cause)
        # 入口直接拒绝：任何 activity 都没跑
        assert state.get("plan_order") in (None, [])


# ---------------------------------------------------------------------------
# S3 中转（claim-check）形状：activity 间只传 key，载荷进共享 state["objects"]
# ---------------------------------------------------------------------------


def _make_relay_activities(
    state: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    rows_per_batch=3,
    batches=2,
    fail_on=None,
    poison_last=False,
):
    """S3 中转形状的假 activity 集：state["objects"] 充当载荷存储（key → JSON 值）。

    read 返回 chunks 元数据、transform 返回 outKey 元数据、resolve/write 收
    recordsKey、失败清单以 failureRefs 引用——与真实 activity 的中转返回形状一致，
    断言 workflow 在「只有 key」的事件历史里仍数得对、推进得对。
    """

    def _put(key: str, value: Any) -> str:
        state.setdefault("objects", {})[key] = value
        return key

    @activity.defn(name="load_schema_extract_plan")
    async def load_plan(schema_id: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(schema_id, dict):
            schema_id = schema_id["schemaId"]
        return plan or PLAN

    @activity.defn(name="read_source_batch")
    async def read_batch(request: dict[str, Any]) -> dict[str, Any]:
        if "recordIds" in request:
            rows = [
                {"id": str(rid), "name": f"w{rid}", "update_time": "2026-09-01 00:00:00"}
                for rid in request["recordIds"]
            ]
            key = _put("rows-rerun-c0", rows)
            return {
                "chunks": [
                    {"key": key, "rowCount": len(rows), "recordIds": [r["id"] for r in rows]}
                ],
                "totalRows": len(rows),
                "maxTime": "2026-09-01 00:05:00",
                "maxPk": rows[-1]["id"] if rows else None,
                "effectiveBatchSize": int(request.get("batchSize") or 500),
            }
        batch_no = state.setdefault("read_seq", 0)
        state["read_seq"] = batch_no + 1
        if batch_no >= batches:
            return {
                "chunks": [],
                "totalRows": 0,
                "maxTime": None,
                "maxPk": None,
                "effectiveBatchSize": 1,
            }
        rows = [
            {
                "id": str(batch_no * rows_per_batch + i),
                "name": f"w{batch_no}_{i}",
                "update_time": f"2026-09-01 00:0{batch_no}:00",
            }
            for i in range(rows_per_batch)
        ]
        if poison_last and batch_no == 0:
            rows[-1]["id"] = "bad"  # 毒行：transform 报 failures（多步则 clean 步报）
        key = _put(f"rows-b{batch_no}-c0", rows)
        return {
            "chunks": [{"key": key, "rowCount": len(rows)}],
            "totalRows": len(rows),
            "maxTime": "2026-09-01 00:05:00",
            "maxPk": rows[-1]["id"],
            "effectiveBatchSize": int(request.get("batchSize") or 500),
        }

    @activity.defn(name="execute_transform")
    async def transform(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("transform_requests", []).append(
            {
                "functionName": request["functionName"],
                "hasInlineRows": "rows" in request,
                "rowsKey": request.get("rowsKey"),
                "inputKey": request.get("inputKey"),
                "prevKeys": request.get("prevKeys"),
                "batchIdx": request.get("batchIdx"),
                "chunkIdx": request.get("chunkIdx"),
            }
        )
        fn = request["functionName"]
        if fail_on is not None and fn == fail_on:
            raise RuntimeError("批次脚本崩溃")
        if fn == "step_clean":
            rows = state["objects"][request["rowsKey"]]
            failures = (
                [{"recordId": "bad", "error": "ValueError: 毒行"}]
                if any(r["id"] == "bad" for r in rows)
                else []
            )
            output = {
                "cleaned": [r for r in rows if r["id"] != "bad"],
                "failures": failures,
                "stats": {"cleaned": len(rows) - len(failures)},
            }
        elif fn in ("step_resolve", "step_emit"):
            # 第 N>1 步：input 从 inputKey 下载（无内联 input/prevOutputs）
            input_value = state["objects"][request["inputKey"]]
            for sid, key in (request.get("prevKeys") or {}).items():
                assert sid in ("clean", "resolve")
                assert state["objects"][key], "prevKeys 下载不应为空"
            if fn == "step_resolve":
                output = {"resolved": list(input_value["cleaned"])}
            else:
                output = {
                    "edges": [
                        {"fromId": "w_" + r["id"], "toId": "org_x", "props": {"name": r["name"]}}
                        for r in input_value["resolved"]
                    ]
                }
        else:
            rows = state["objects"][request["rowsKey"]]
            entities = []
            failures = []
            for row in rows:
                if row["id"] == "bad":
                    failures.append({"recordId": "bad", "error": "ValueError: 毒行"})
                else:
                    entities.append({"id": f"widget_{row['id']}", "props": {"name": row["name"]}})
            output = {"entities": entities, "failures": failures}
        tag = f"{fn}-{request.get('batchIdx')}-{request.get('chunkIdx')}"
        out_key = _put(f"out-{tag}", output)
        result: dict[str, Any] = {
            "outKey": out_key,
            "hasRecords": bool(output.get("entities") or output.get("edges")),
            "entityCount": len(output.get("entities") or []),
            "edgeCount": len(output.get("edges") or []),
            "failureCount": len(output.get("failures") or []),
        }
        if output.get("failures"):
            result["failuresKey"] = _put(
                f"failures-{tag}",
                [
                    {
                        "sourceBindingId": "bind-1",
                        "sourceTable": "gkx.dwd_widget",
                        "recordId": f["recordId"],
                        "error": f["error"],
                    }
                    for f in output["failures"]
                ],
            )
        return result

    @activity.defn(name="resolve_entity_batch")
    async def resolve_entities(request: dict[str, Any]) -> dict[str, Any]:
        assert request.get("recordsKey"), "中转形状下 resolve 应收 recordsKey"
        records = state["objects"][request["recordsKey"]]
        if isinstance(records, dict):
            records = records.get("entities") or []
        out_key = _put(f"resolved-{request.get('stepId')}-{request.get('batchIdx')}", records)
        return {
            "outKey": out_key,
            "keptCount": len(records),
            "merged": 0,
            "withheld": 0,
            "deduped": 0,
            "new": len(records),
        }

    @activity.defn(name="write_records")
    async def write_records(request: dict[str, Any]) -> dict[str, Any]:
        assert request.get("recordsKey"), "中转形状下写图应收 recordsKey"
        data = state["objects"][request["recordsKey"]]
        records = (
            (data.get("entities") or data.get("edges") or []) if isinstance(data, dict) else data
        )
        state.setdefault("writes", []).append(len(records))
        result: dict[str, Any] = {"written": len(records)}
        if request.get("indexVids"):
            result["vidsKey"] = (
                f"runs/mock/{request.get('stepId')}/{request.get('batchIdx')}-"
                f"{request.get('chunkIdx')}/vids.json.gz"
            )
        return result

    @activity.defn(name="advance_schema_extract_watermark")
    async def advance(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("advances", []).append(request)
        return {"ok": True}

    @activity.defn(name="detect_extract_collisions")
    async def collisions(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("collisions_calls", []).append(bool(request.get("recordsKey")))
        return {"collisions": 0}

    @activity.defn(name="record_extract_failures")
    async def record_failures(request: dict[str, Any]) -> dict[str, Any]:
        inline = request.get("failures") or []
        refs = request.get("failureRefs") or []
        state.setdefault("record_failure_requests", []).append(
            {"inline": inline, "refs": refs, "cap": request.get("cap")}
        )
        return {"recorded": len(inline) + sum(int(r.get("count") or 0) for r in refs)}

    @activity.defn(name="resolve_failure_cases")
    async def resolve_cases(request: dict[str, Any]) -> dict[str, Any]:
        inline = request.get("failures") or []
        refs = request.get("failureRefs") or []
        state.setdefault("resolve", []).append({"inline": inline, "refs": refs})
        return {"resolved": 1, "refailed": 0, "recreated": 0}

    @activity.defn(name="refresh_graph_stats")
    async def refresh_stats(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("stats_jobs", []).append(request)
        return {"submitted": True, "jobId": 99}

    @activity.defn(name="build_entity_index")
    async def build_index(request: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("index", []).append(request)
        return {"reindexed": {"entityTypes": request.get("entityTypes")}}

    @activity.defn(name="record_schema_script_run")
    async def record_script_run(request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    @activity.defn(name="resolve_execution_llm")
    async def resolve_llm(request: dict[str, Any]) -> dict[str, Any]:
        # business-llm-default-v1 链首选型 activity 的假实现：空覆盖原样透传
        return {}

    return [
        load_plan,
        read_batch,
        transform,
        resolve_entities,
        write_records,
        advance,
        collisions,
        record_failures,
        resolve_cases,
        record_script_run,
        build_index,
        refresh_stats,
        resolve_llm,
    ]


@pytest.mark.asyncio
class TestSchemaExtractS3Relay:
    async def test_relay_batches_flow_with_rows_keys(self):
        """中转主链路：read chunks → transform rowsKey/outKey → resolve recordsKey → 写图。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-relay-1",
                workflows=[SchemaExtractWorkflow],
                activities=_make_relay_activities(state, rows_per_batch=3, batches=2),
            ):
                result = await _run(
                    env.client,
                    "t-relay-1",
                    {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 3},
                )
        assert result["status"] == "completed"
        assert result["failures"]["count"] == 0
        # 批计数按 totalRows/chunk rowCount 累计：2 批 × 3 行
        assert result["sources"][0]["rows"] == 6
        assert result["sources"][0]["batches"] == 2
        assert result["sources"][0]["written"] == 6
        # transform 全部经 rowsKey（无内联 rows），batchIdx/chunkIdx 确定性派生
        reqs = state["transform_requests"]
        assert len(reqs) == 2
        assert all(not r["hasInlineRows"] and r["rowsKey"] for r in reqs)
        assert {(r["batchIdx"], r["chunkIdx"]) for r in reqs} == {(0, 0), (1, 0)}
        assert reqs[0]["rowsKey"] == "rows-b0-c0" and reqs[1]["rowsKey"] == "rows-b1-c0"
        # 写图收 recordsKey（resolve 中转产物）；gray-gate-v2 下 detect 退出不收
        assert sum(state["writes"]) == 6
        assert state.get("collisions_calls") in (None, [])
        # 载荷对象确实落在共享存储（rows/out/resolved 三类）；resolve 的 stepId
        # 带 #stepId 后缀（ctxStepId 语义）
        assert "rows-b0-c0" in state["objects"] and "rows-b1-c0" in state["objects"]
        assert any(k.startswith("out-step_main-") for k in state["objects"])
        assert any(k.startswith("resolved-source:bind-1#") for k in state["objects"])
        # 无失败：不建 case；游标整链推进一次；实体默认重建索引
        assert state.get("record_failure_requests") in (None, [])
        assert len(state["advances"]) == 1
        assert state.get("index")

    async def test_relay_rerun_chunk_crash_synthesizes_inline_failures(self):
        """重跑 + 中转：批次崩溃用 chunk 元数据里的 recordIds 合成内联失败（无行数据可数）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-relay-2",
                workflows=[SchemaExtractWorkflow],
                activities=_make_relay_activities(state, fail_on="step_main"),
            ):
                result = await _run(
                    env.client,
                    "t-relay-2",
                    {
                        "schemaId": "schema-e2e",
                        "graphSpace": "dev2",
                        "batchSize": 5,
                        "recordIdsBySource": {"bind-1": ["w1", "bad"]},
                        "rerunCaseIds": ["MR-1"],
                        "rerunOfExecutionId": "EXEC-1",
                        "triggerSource": "RERUN",
                    },
                )
        assert result["status"] == "completed"
        assert result["failures"]["count"] == 2
        # 整批失败按步归因：失败行计入 activity 崩溃所在的步（步级 failed>0 →
        # 任务详情/审核日志弹窗的阶段显示「异常」，与执行概要 ABNORMAL 对齐；
        # 此前步级恒零骨架恒显成功——2026-10-11 用例 MR-20261009-A2DBE6074880）
        main_stat = result["steps"]["main"]
        assert main_stat["failed"] == 2
        assert main_stat["records"] == 0 and main_stat["written"] == 0
        assert result["sources"][0]["steps"]["main"]["failed"] == 2
        # resolve 必调：拿到按 chunk recordIds 合成的内联失败
        inline = state["resolve"][0]["inline"]
        assert [f["recordId"] for f in inline] == ["w1", "bad"]
        assert state["resolve"][0]["refs"] == []
        # 重跑不推游标、不重建索引
        assert state.get("advances") in (None, [])
        assert state.get("index") in (None, [])

    async def test_relay_rerun_script_failures_pass_refs_to_resolve(self):
        """重跑 + 中转：脚本自报 failures 走 failuresKey 引用，resolve 展开（无 cap 截断）。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-relay-3",
                workflows=[SchemaExtractWorkflow],
                activities=_make_relay_activities(state),
            ):
                result = await _run(
                    env.client,
                    "t-relay-3",
                    {
                        "schemaId": "schema-e2e",
                        "graphSpace": "dev2",
                        "batchSize": 5,
                        "recordIdsBySource": {"bind-1": ["w1", "bad"]},
                        "rerunCaseIds": ["MR-1"],
                        "triggerSource": "RERUN",
                    },
                )
        assert result["status"] == "completed"
        assert result["failures"]["count"] == 1
        refs = state["resolve"][0]["refs"]
        assert len(refs) == 1 and refs[0]["count"] == 1
        assert state["objects"][refs[0]["failuresKey"]][0]["recordId"] == "bad"
        assert state["resolve"][0]["inline"] == []
        # 好行照写
        assert state["writes"] == [1]

    async def test_relay_multistep_input_prev_keys_no_truncation(self):
        """中转 + 多步：第 N>1 步收 inputKey/prevKeys（无内联 input），统计照常聚合。"""
        state: dict[str, Any] = {}
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="t-relay-4",
                workflows=[SchemaExtractWorkflow],
                activities=_make_relay_activities(
                    state, plan=MULTI_STEP_PLAN, rows_per_batch=3, batches=1, poison_last=True
                ),
            ):
                result = await _run(
                    env.client,
                    "t-relay-4",
                    {"schemaId": "schema-e2e", "graphSpace": "dev2", "batchSize": 5},
                )
        assert result["status"] == "completed"
        reqs = state["transform_requests"]
        assert [r["functionName"] for r in reqs] == ["step_clean", "step_resolve", "step_emit"]
        # 第 1 步经 rowsKey；第 2/3 步经 inputKey+prevKeys，均无内联载荷
        assert reqs[0]["rowsKey"] == "rows-b0-c0" and not reqs[0]["inputKey"]
        assert reqs[1]["inputKey"] == "out-step_clean-0-0"
        assert set(reqs[1]["prevKeys"]) == {"clean"}
        assert reqs[2]["inputKey"] == "out-step_resolve-0-0"
        assert set(reqs[2]["prevKeys"]) == {"clean", "resolve"}
        # 步间透传无截断：第 2 步下载到的 input = 第 1 步归档的全量输出
        # （3 行含 1 毒行 → clean 步 failures 1、cleaned 2）
        assert state["objects"]["out-step_clean-0-0"]["stats"] == {"cleaned": 2}
        assert len(state["objects"]["out-step_clean-0-0"]["cleaned"]) == 2
        assert len(state["objects"]["out-step_resolve-0-0"]["resolved"]) == 2
        # 关系链只写 emit 步的边；分步统计聚合
        assert state["writes"] == [2]
        emit_stat = result["steps"]["emit"]
        assert emit_stat["records"] == 2
        assert emit_stat["written"] == 2
        assert emit_stat["failed"] == 0
        assert emit_stat["status"] == "COMPLETED"
        assert emit_stat["position"] == 3
        # clean 步毒行失败以 failuresKey 引用聚合，终态建 case 交 refs 展开
        assert result["failures"]["count"] == 1
        recorded = state["record_failure_requests"][0]
        assert recorded["refs"][0]["count"] == 1
        assert recorded["inline"] == []
