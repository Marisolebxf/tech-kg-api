"""科技图谱 Temporal 工作流与 Activity 定义。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from temporalio import activity, workflow


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
async def execute_python_script(request: dict[str, Any]) -> dict[str, Any]:
    """在隔离子进程中调用上传脚本的 workflow(payload) 函数。"""
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    function_name = request.get("functionName", "workflow")
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
    # 上传脚本需要 backend 模块（infra/dao/script）与凭据（MySQL/TRSGraph）。
    # worker 进程不 import infra，故这里显式加载 backend/.env，并把 backend 目录加入 PYTHONPATH。
    # 平台已声明上传脚本具备服务器进程权限（见 docs/workflow_operations_api.md），透传 env 不降低安全面。
    # BACKEND_DIR 在 activity 内计算（workflow sandbox 禁止模块顶层 Path.resolve）。
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    pythonpath = os.pathsep.join(filter(None, [str(backend_dir), str(script_path.parent)]))
    sub_env = {**os.environ, "PYTHONPATH": pythonpath}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        runner,
        str(script_path),
        function_name,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sub_env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(
                json.dumps(request.get("payload", {}), ensure_ascii=False).encode()
            ),
            timeout=float(request.get("timeoutSeconds", 60)),
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("上传脚本执行超时") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    return json.loads(stdout.decode() or "null")


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
            )
        )
    return {"kind": kind, "domain": domain, "status": "completed", "steps": results}


@workflow.defn(name="kg.entity.paper")
class PaperEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "paper")


@workflow.defn(name="kg.entity.scholar")
class ScholarEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "scholar")


@workflow.defn(name="kg.entity.patent")
class PatentEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "patent")


@workflow.defn(name="kg.entity.organization")
class OrganizationEntityWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "entity", "organization")


@workflow.defn(name="kg.relation.authorship")
class AuthorshipRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "authorship")


@workflow.defn(name="kg.relation.employment")
class EmploymentRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "employment")


@workflow.defn(name="kg.relation.citation")
class CitationRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "citation")


@workflow.defn(name="kg.relation.cooperation")
class CooperationRelationWorkflow:
    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        return await _run_domain_pipeline(request, "relation", "cooperation")


@workflow.defn(name="kg.graph.build")
class GraphBuildWorkflow:
    """总工作流；按请求为每类实体和关系启动各自的子工作流。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
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
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
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
                )
            )
        return {"definitionId": definition["id"], "status": "completed", "steps": results}


@workflow.defn(name="kg.custom.python")
class PythonScriptWorkflow:
    """上传脚本工作流包装器，脚本函数在 Activity 子进程中运行以保证 Workflow 可重放。"""

    @workflow.run
    async def run(self, request: dict[str, Any]) -> Any:
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
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
        )


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
]

ACTIVITIES = [execute_kg_step, load_workflow_definition, execute_python_script]
