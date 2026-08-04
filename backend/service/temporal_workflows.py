"""科技图谱 Temporal 工作流与 Activity 定义。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Awaitable
from datetime import timedelta
from pathlib import Path
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

ACTIVITY_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
SCRIPT_RETRY_POLICY = RetryPolicy(maximum_attempts=1)
OUTCOME_RETRY_POLICY = RetryPolicy(maximum_attempts=5)


@activity.defn
async def execute_kg_step(request: dict[str, Any]) -> dict[str, Any]:
    """领域步骤执行入口；真实 ETL/抽取模块可按 step 和 domain 在此注册。"""
    await asyncio.sleep(float(request.get("delaySeconds", 0)))
    payload = request.get("payload", {})
    return {
        "step": request["step"],
        "domain": request.get("domain"),
        "kind": request.get("kind"),
        "status": "completed",
        "input": payload,
        "output": payload,
    }


@activity.defn
async def load_workflow_definition(definition_id: str) -> dict[str, Any]:
    # 延迟导入避免 Workflow sandbox 在模块加载阶段访问 SQLite。
    from service.workflow_repository import repository

    definition = repository.get_definition(definition_id)
    if definition is None:
        raise ValueError(f"工作流定义不存在: {definition_id}")
    return definition


@activity.defn
async def execute_python_script(request: dict[str, Any]) -> Any:
    """Run an uploaded workflow script in an isolated child process."""
    return await _execute_script_path(
        Path(request["scriptPath"]),
        function_name=request.get("functionName", "workflow"),
        payload=request.get("payload", {}),
        timeout_seconds=float(request.get("timeoutSeconds", 60)),
    )


async def _execute_script_path(
    script_path: Path,
    *,
    function_name: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Any:
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    runner = """
import asyncio
import importlib.util
import inspect
import json
import sys

path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("uploaded_workflow", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.loads(sys.stdin.read() or "{}")
result = function(payload)
if inspect.isawaitable(result):
    result = asyncio.run(result)
print(json.dumps(result, ensure_ascii=False))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        runner,
        str(script_path),
        function_name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"PATH": os.getenv("PATH", ""), "PYTHONPATH": str(script_path.parent)},
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps(payload, ensure_ascii=False).encode()),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("上传脚本执行超时") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    return json.loads(stdout.decode() or "null")


@activity.defn
async def execute_schema_script(request: dict[str, Any]) -> Any:
    """Download a Schema script from S3 and execute transform(payload)."""
    from infra.s3 import get_schema_s3_storage

    storage = get_schema_s3_storage()

    def download() -> bytes:
        body = storage.get_object(request["bucket"], request["objectKey"])
        try:
            return body.read()
        finally:
            body.close()

    script_data = await asyncio.to_thread(download)
    actual_sha256 = hashlib.sha256(script_data).hexdigest()
    expected_sha256 = request.get("sha256")
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise ValueError("Schema 脚本校验失败: sha256 不匹配")
    with tempfile.TemporaryDirectory(prefix="tech-kg-schema-") as directory:
        script_path = Path(directory) / "schema.py"
        await asyncio.to_thread(script_path.write_bytes, script_data)
        return await _execute_script_path(
            script_path,
            function_name=request.get("functionName", "transform"),
            payload=request.get("payload", {}),
            timeout_seconds=float(request.get("timeoutSeconds", 60)),
        )


@activity.defn
async def persist_schema_result(request: dict[str, Any]) -> dict[str, Any]:
    """Validate transformed data against its Schema kind and persist through graph APIs."""
    return await asyncio.to_thread(_persist_schema_result_sync, request)


def _persist_schema_result_sync(request: dict[str, Any]) -> dict[str, Any]:
    from infra.graph_db import get_graph_client

    graph = get_graph_client(request.get("space"))
    schema_kind = request["schemaKind"]
    schema_name = request["schemaName"]
    properties = request.get("properties", [])
    ddl_fields = ", ".join(
        f"`{item['name']}` {_nebula_type(item.get('dataType'))}" for item in properties
    )
    if schema_kind == "entity":
        graph.execute_write(f"CREATE TAG IF NOT EXISTS `{schema_name}` ({ddl_fields});")
        rows = _result_items(request.get("result"))
        persisted = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("实体 Schema transform 必须返回对象或对象数组")
            identity_key = _identity_key(request.get("identityKey", ""), row)
            if identity_key is None:
                raise ValueError("实体结果缺少 identityKey、vid、id 或 name")
            node = graph.merge_node(
                [schema_name],
                {identity_key: row[identity_key]},
                {key: value for key, value in row.items() if key != identity_key},
            )
            persisted.append(str(node.id))
        return {"kind": "entity", "count": len(persisted), "nodeIds": persisted}

    if schema_kind == "relation":
        graph.execute_write(f"CREATE EDGE IF NOT EXISTS `{schema_name}` ({ddl_fields});")
        rows = _result_items(request.get("result"))
        persisted = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("关系 Schema transform 必须返回对象或对象数组")
            source = row.get("sourceId", row.get("source"))
            target = row.get("targetId", row.get("target"))
            if source in (None, "") or target in (None, ""):
                raise ValueError("关系结果必须包含 sourceId 和 targetId")
            if graph.get_node(source) is None or graph.get_node(target) is None:
                raise ValueError(f"关系端点不存在: {source} -> {target}")
            edge_properties = row.get("properties")
            if not isinstance(edge_properties, dict):
                edge_properties = {
                    key: value
                    for key, value in row.items()
                    if key not in {"sourceId", "targetId", "source", "target"}
                }
            edge = graph.create_edge(source, target, schema_name, edge_properties)
            persisted.append(str(edge.id))
        return {"kind": "relation", "count": len(persisted), "edgeIds": persisted}
    raise ValueError(f"不支持的 Schema 类型: {schema_kind}")


def _result_items(result: Any) -> list[Any]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return result["items"]
    return [result]


def _identity_key(expression: str, row: dict[str, Any]) -> str | None:
    candidates = [token for token in expression.replace("/", " ").split() if token in row]
    candidates.extend(key for key in ("vid", "id", "name") if key in row)
    return next((key for key in candidates if row.get(key) not in (None, "")), None)


def _nebula_type(data_type: Any) -> str:
    value = str(data_type or "string").casefold()
    if any(token in value for token in ("int", "integer", "long")):
        return "int"
    if any(token in value for token in ("float", "double", "decimal", "number")):
        return "double"
    if "bool" in value:
        return "bool"
    if "datetime" in value or "timestamp" in value:
        return "datetime"
    if value == "date" or "日期" in value:
        return "date"
    return "string"


@activity.defn
async def record_workflow_outcome(request: dict[str, Any]) -> dict[str, Any]:
    """Push terminal Workflow state into the control-plane repository."""
    from service.workflow_operations import workflow_operations_service

    return await asyncio.to_thread(
        workflow_operations_service.apply_execution_outcome,
        workflow_id=request["workflowId"],
        status=request["status"],
        output=request.get("output"),
        failure=request.get("failure"),
    )


def _failure_message(exc: BaseException) -> str:
    """Preserve the useful Activity/Application error chain for API consumers."""
    messages: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).strip()
        if message and message not in messages:
            messages.append(message)
        current = getattr(current, "cause", None) or current.__cause__ or current.__context__
    return " | ".join(messages)[:4000] or type(exc).__name__


async def _run_tracked(request: dict[str, Any], operation: Awaitable[Any]) -> Any:
    control = request.get("_control") or {}
    workflow_id = workflow.info().workflow_id
    tracked = control.get("workflowId") == workflow_id
    try:
        result = await operation
    except asyncio.CancelledError:
        if tracked:
            await workflow.execute_activity(
                record_workflow_outcome,
                {"workflowId": workflow_id, "status": "CANCELED", "failure": "工作流已取消"},
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=OUTCOME_RETRY_POLICY,
            )
        raise
    except Exception as exc:
        if tracked:
            await workflow.execute_activity(
                record_workflow_outcome,
                {
                    "workflowId": workflow_id,
                    "status": "FAILED",
                    "failure": _failure_message(exc),
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=OUTCOME_RETRY_POLICY,
            )
        raise
    if tracked:
        await workflow.execute_activity(
            record_workflow_outcome,
            {"workflowId": workflow_id, "status": "COMPLETED", "output": result},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=OUTCOME_RETRY_POLICY,
        )
    return result


async def _run_domain_pipeline(request: dict[str, Any], kind: str, domain: str) -> dict[str, Any]:
    results = []
    for step in ("load_increment", "normalize", "extract_align", "validate", "persist"):
        results.append(
            await workflow.execute_activity(
                execute_kg_step,
                {
                    "step": step,
                    "kind": kind,
                    "domain": domain,
                    "payload": request,
                },
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
        )
    return {"kind": kind, "domain": domain, "status": "completed", "steps": results}


@workflow.defn(name="kg.entity.paper")
class PaperEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "entity", "paper"))


@workflow.defn(name="kg.entity.scholar")
class ScholarEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "entity", "scholar"))


@workflow.defn(name="kg.entity.patent")
class PatentEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "entity", "patent"))


@workflow.defn(name="kg.entity.organization")
class OrganizationEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "entity", "organization"))


@workflow.defn(name="kg.relation.authorship")
class AuthorshipRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "relation", "authorship"))


@workflow.defn(name="kg.relation.employment")
class EmploymentRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "relation", "employment"))


@workflow.defn(name="kg.relation.citation")
class CitationRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "relation", "citation"))


@workflow.defn(name="kg.relation.cooperation")
class CooperationRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_domain_pipeline(request, "relation", "cooperation"))


@workflow.defn(name="kg.graph.build")
class GraphBuildWorkflow:
    """总工作流；按请求为每类实体和关系启动各自的子工作流。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_graph_build(request))


async def _run_graph_build(request: dict[str, Any]) -> dict[str, Any]:
    entities = request.get("entities") or ["paper", "scholar", "patent", "organization"]
    relations = request.get("relations") or [
        "authorship",
        "employment",
        "citation",
        "cooperation",
    ]
    child_types = [
        *(f"kg.entity.{item}" for item in entities),
        *(f"kg.relation.{item}" for item in relations),
    ]
    results = []
    for index, workflow_type in enumerate(child_types):
        results.append(
            await workflow.execute_child_workflow(
                workflow_type,
                request,
                id=f"{workflow.info().workflow_id}-{index}-{workflow_type.rsplit('.', 1)[-1]}",
            )
        )
    return {"status": "completed", "children": results}


@workflow.defn(name="kg.custom.configurable")
class ConfigurableWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_tracked(request, _run_configurable(request))


async def _run_configurable(request: dict[str, Any]) -> dict[str, Any]:
    definition = await workflow.execute_activity(
        load_workflow_definition,
        request["definitionId"],
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=ACTIVITY_RETRY_POLICY,
    )
    results = []
    for step in definition.get("steps", []):
        step_name = step if isinstance(step, str) else step.get("id") or step.get("name")
        results.append(
            await workflow.execute_activity(
                execute_kg_step,
                {
                    "step": step_name,
                    "kind": "custom",
                    "domain": definition["id"],
                    "payload": request.get("payload", {}),
                },
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=ACTIVITY_RETRY_POLICY,
            )
        )
    return {"definitionId": definition["id"], "status": "completed", "steps": results}


@workflow.defn(name="kg.custom.python")
class PythonScriptWorkflow:
    """上传脚本工作流包装器，脚本函数在 Activity 子进程中运行以保证 Workflow 可重放。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> Any:
        return await _run_tracked(request, _run_python_workflow(request))


async def _run_python_workflow(request: dict[str, Any]) -> Any:
    definition = await workflow.execute_activity(
        load_workflow_definition,
        request["definitionId"],
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=ACTIVITY_RETRY_POLICY,
    )
    return await workflow.execute_activity(
        execute_python_script,
        {
            "scriptPath": definition["scriptPath"],
            "functionName": definition.get("functionName", "workflow"),
            "payload": request.get("payload", {}),
            "timeoutSeconds": definition.get("timeoutSeconds", 60),
        },
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=SCRIPT_RETRY_POLICY,
    )


@workflow.defn(name="kg.schema.execute")
class SchemaScriptWorkflow:
    """Execute the exact version of a Schema transform script referenced by the API."""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> Any:
        return await _run_tracked(request, _run_schema_workflow(request))


async def _run_schema_workflow(request: dict[str, Any]) -> Any:
    transformed = await workflow.execute_activity(
        execute_schema_script,
        request,
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=ACTIVITY_RETRY_POLICY,
    )
    persistence = await workflow.execute_activity(
        persist_schema_result,
        {**request, "result": transformed},
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=ACTIVITY_RETRY_POLICY,
    )
    return {"transformed": transformed, "persistence": persistence}


WORKFLOW_CLASSES = [
    PaperEntityWorkflow,
    ScholarEntityWorkflow,
    PatentEntityWorkflow,
    OrganizationEntityWorkflow,
    AuthorshipRelationWorkflow,
    EmploymentRelationWorkflow,
    CitationRelationWorkflow,
    CooperationRelationWorkflow,
    GraphBuildWorkflow,
    ConfigurableWorkflow,
    PythonScriptWorkflow,
    SchemaScriptWorkflow,
]

ACTIVITIES = [
    execute_kg_step,
    load_workflow_definition,
    execute_python_script,
    execute_schema_script,
    persist_schema_result,
    record_workflow_outcome,
]
