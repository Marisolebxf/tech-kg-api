# 多步骤实体构建工作流设计（kg.custom.steps）

## 背景与现状

当前 Temporal 集成（`service/temporal_workflows.py`、`service/workflow_operations.py`）有三类 workflow：

- `kg.entity.*` / `kg.relation.*`：硬编码 6 步循环 `_run_domain_pipeline`（`temporal_workflows.py:139-154`），仅 project 域在 `persist` 步真正跑 ETL，其它步骤是桩。
- `kg.custom.configurable`：从 `workflow_definitions` 读 `steps` 列表逐个调 `execute_kg_step`，但 activity 是桩。
- `kg.custom.python`：上传脚本作为子进程跑 `workflow(payload)`，返回单一 JSON dict（`temporal_workflows.py:79-136`、`282-303`）。

`_sync_task_from_execution`（`workflow_operations.py:266-312`）**只在脚本返回 `stages` 列表时**才把 stages 映射到 `tasks.steps`——目前只有 `script/workflows/project_ingest_workflow.py` 这么做，其它脚本的任务详情页仍是 `workflow_repository._steps()` 的静态 demo 步骤。

**缺口**：step 不是一等 Temporal 概念——无 per-step 重试策略、无 per-step 输入输出持久化、无失败后从失败步恢复、无人工审核暂停。

## 设计目标

1. 用户能上传一个含多 step 函数的 Python 模块，并声明 step manifest
2. 每个 step 是一个 Temporal Activity，带独立的 retry policy 和 timeout
3. 任务详情页能实时看到每步状态/输入/输出，workflow 运行中也可见
4. 失败后能从失败步重试，已完成步不重跑
5. 人工审核能让 workflow 暂停在指定 step，审核者可批准/驳回/修正结果后继续

## 架构总览

**全原生 Temporal 方案**——不新增 DB 表，不重新发明 activity replay：

- Step 运行态真相放在 **workflow state**，UI 通过 `@workflow.query` 读
- `tasks`/`workflow_executions` 表不动：前者管列表/批次/审核记录，后者管 workflow_id/run_id 索引
- 接受 dev2 重置会丢暂停态（开发期偶发；生产 Temporal 稳定即可）

## 原生能力映射

| 场景 | Temporal 能力 | 入口 |
|---|---|---|
| Per-step 瞬态重试 | `RetryPolicy`（`temporalio.common`） | manifest `retryPolicy` 字段 |
| 人工审核暂停→继续 | `@workflow.signal` + `workflow.wait_condition` | `POST /tasks/{id}/review` → `handle.signal("submit_review", ...)` |
| 失败后整体重试 | `ResetWorkflowExecution` | `POST /tasks/{id}/retry` → `client.reset_workflow_execution(...)` |
| Step I/O 实时查看 | `@workflow.query` | UI 调 `handle.query("get_steps")` |
| 已完成步不重跑 | event history replay | Temporal 自动 |

## 数据模型

**不新增表**。复用现有 `workflow_definitions`（manifest 存 `payload` JSON）、`workflow_executions`（tracking）、`tasks`（任务列表）、`reviews`（审核审计日志）。

`workflow_definitions.payload` JSON 结构升级（向后兼容：`sourceKind == "python"` 旧定义仍可被 `kg.custom.python` 读）：

```json
{
  "id": "paper-pipeline",
  "name": "论文实体流水线",
  "workflowType": "kg.custom.steps",
  "category": "custom",
  "taskQueue": "tech-kg-workflows",
  "active": true,
  "sourceKind": "python",
  "scriptPath": "/var/lib/tech-kg/scripts/paper_pipeline.py",
  "steps": [
    {"id": "load",    "name": "增量加载", "functionName": "step_load",
     "timeoutSeconds": 600,  "retryPolicy": {"maximumAttempts": 3, "initialIntervalSeconds": 5}},
    {"id": "extract", "name": "实体抽取", "functionName": "step_extract",
     "timeoutSeconds": 1200, "retryPolicy": {"maximumAttempts": 3}, "requireReview": true},
    {"id": "align",   "name": "对齐",     "functionName": "step_align",
     "timeoutSeconds": 600,  "retryPolicy": {"maximumAttempts": 3}, "requireReview": true},
    {"id": "persist", "name": "落库",     "functionName": "step_persist",
     "timeoutSeconds": 1800, "retryPolicy": {"maximumAttempts": 1}}
  ],
  "createdAt": "2026-08-25 10:00:00"
}
```

## Workflow: `kg.custom.steps`

新增到 `service/temporal_workflows.py`：

```python
@workflow.defn(name="kg.custom.steps")
class StepPipelineWorkflow:
    def __init__(self) -> None:
        self._steps: dict[str, dict] = {}  # step_id → {status, output, error, attempt}
        self._current_step: str | None = None
        self._review_signal: dict | None = None

    @workflow.run
    async def run(self, request: dict[str, Any]) -> dict[str, Any]:
        definition = await workflow.execute_activity(
            load_workflow_definition,
            request["definitionId"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        prev_outputs: dict[str, Any] = {}
        for step in definition.get("steps", []):
            self._current_step = step["id"]
            while True:
                try:
                    result = await workflow.execute_activity(
                        execute_pipeline_step,
                        {
                            "taskId": request["taskId"],
                            "executionId": request["executionId"],
                            "definitionId": request["definitionId"],
                            "stepId": step["id"],
                            "functionName": step["functionName"],
                            "scriptPath": definition["scriptPath"],
                            "payload": request.get("payload", {}),
                            "prevOutputs": prev_outputs,
                            "timeoutSeconds": step.get("timeoutSeconds", 600),
                        },
                        start_to_close_timeout=timedelta(
                            seconds=step.get("timeoutSeconds", 600) + 30
                        ),
                        retry_policy=_retry_policy(step.get("retryPolicy", {})),
                    )
                    self._steps[step["id"]] = {
                        "status": "COMPLETED",
                        "output": result["output"],
                        "attempt": result["attempt"],
                    }
                    prev_outputs[step["id"]] = result["output"]
                    break
                except Exception as exc:
                    self._steps[step["id"]] = {"status": "FAILED", "error": str(exc)}
                    raise  # workflow 失败；用户走 reset 回放重试
            # 人工审核暂停
            if step.get("requireReview"):
                self._steps[step["id"]]["status"] = "PENDING_REVIEW"
                await workflow.wait_condition(lambda: self._review_signal is not None)
                review = self._review_signal
                self._review_signal = None
                if review["decision"] == "reject":
                    self._steps[step["id"]]["status"] = "REJECTED"
                    return {"status": "rejected", "step": step["id"], "steps": self._steps}
                if review.get("modifiedResult"):
                    prev_outputs[step["id"]] = review["modifiedResult"]  # 审核者修正，下游用修正值
                self._steps[step["id"]]["status"] = "REVIEWED"
        return {"status": "completed", "steps": self._steps}

    @workflow.signal
    def submit_review(self, review: dict[str, Any]) -> None:
        self._review_signal = review

    @workflow.query
    def get_steps(self) -> dict[str, Any]:
        return {"current": self._current_step, "steps": self._steps}


def _retry_policy(config: dict[str, Any]) -> RetryPolicy:
    from temporalio.common import RetryPolicy
    from datetime import timedelta

    return RetryPolicy(
        maximum_attempts=int(config.get("maximumAttempts", 1)),
        initial_interval=timedelta(seconds=int(config.get("initialIntervalSeconds", 1))),
        maximum_interval=timedelta(seconds=int(config.get("maximumIntervalSeconds", 100))),
        non_retryable_error_types=config.get("nonRetryableErrorTypes") or None,
    )
```

注册到 `WORKFLOW_CLASSES` 和 `ACTIVITIES`（`temporal_workflows.py:306-321`）。

## Activity: `execute_pipeline_step`

新增到 `service/temporal_workflows.py`。基于现有 `execute_python_script`（`temporal_workflows.py:79-136`）的子进程 runner，**独立一份**（不与 `kg.custom.python` 共享 runner，避免 arity 检测魔法）：

```python
@activity.defn
async def execute_pipeline_step(request: dict[str, Any]) -> dict[str, Any]:
    """运行 manifest 中某个 step 的用户函数 fn(payload, ctx)；不写 DB，状态由 workflow state 管。"""
    script_path = Path(request["scriptPath"])
    if not script_path.is_file():
        raise ValueError(f"脚本不存在: {script_path}")
    function_name = request["functionName"]
    attempt = activity.info().attempt
    ctx = {
        "stepId": request["stepId"],
        "attempt": attempt,
        "prevOutputs": request.get("prevOutputs", {}),
        "executionId": request["executionId"],
        "taskId": request["taskId"],
        "definitionId": request["definitionId"],
    }
    runner = """
import asyncio
import importlib.util
import inspect
import json
import sys

path, function_name = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("uploaded_step_module", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
function = getattr(module, function_name)
payload = json.loads(sys.stdin.read() or "{}")
result = function(payload) if len(inspect.signature(function).parameters) == 1 else function(payload, ctx)
if inspect.isawaitable(result):
    result = asyncio.run(result)
print(json.dumps(result, ensure_ascii=False))
"""
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    pythonpath = os.pathsep.join(filter(None, [str(backend_dir), str(script_path.parent)]))
    sub_env = {
        **os.environ,
        "PYTHONPATH": pythonpath,
        "KG_STEP_CTX": json.dumps(ctx, ensure_ascii=False),
    }  # ctx 经 env 传，避免 stdin 双用
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
            timeout=float(request.get("timeoutSeconds", 600)),
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"step {request['stepId']} 执行超时") from None
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace")[-4000:])
    output = json.loads(stdout.decode() or "null")
    return {"step": request["stepId"], "status": "COMPLETED", "output": output, "attempt": attempt}
```

> 注：runner 内 `ctx` 从 `os.environ["KG_STEP_CTX"]` 读，需要 runner 字符串加 `import os; ctx = json.loads(os.environ.get("KG_STEP_CTX", "{}"))`。上面 runner 是示意，实施时补全。

**用户函数契约**：`def step_xxx(payload: dict, ctx: dict) -> dict`。`ctx` 含 `stepId`/`attempt`/`prevOutputs`/`executionId`/`taskId`/`definitionId`。返回 JSON-able dict。

## Manifest 上传与 AST 校验

新增 `WorkflowOperationsService.create_step_pipeline_definition`（参照 `create_python_definition` `workflow_operations.py:419-468`）：

- 接受 `filename` + `content` + `steps` manifest + 可选 `definition_id`/`name`
- `ast.parse` 后收集所有 `FunctionDef`/`AsyncFunctionDef` 名字
- 校验 manifest 里每个 `step.functionName` 都在脚本函数集合里
- `timeoutSeconds` 默认 600，每个 step 的 `retryPolicy.maximumAttempts` 默认 1（stateful 步骤如 persist 不重试）
- `workflowType = "kg.custom.steps"`，`sourceKind = "python"`
- 落盘脚本到 `WORKFLOW_SCRIPT_DIR`（默认 `backend/var/workflow-scripts`，dev2 `/var/lib/tech-kg/scripts`）

## Backend 改动清单（按文件）

### `service/temporal_workflows.py`
- 新增 `StepPipelineWorkflow` 类（见上）
- 新增 `execute_pipeline_step` activity（见上）
- 新增 `_retry_policy(config)` helper
- `WORKFLOW_CLASSES` 追加 `StepPipelineWorkflow`
- `ACTIVITIES` 追加 `execute_pipeline_step`

### `service/workflow_operations.py`
- 新增 `create_step_pipeline_definition(...)` 方法
- 新增 `submit_review(task_id, decision, modified_result=None, reviewer=None)`：写 `reviews` 表做审计 → `handle.signal("submit_review", {"decision", "modifiedResult"})`
- 新增 `retry_task(task_id)`：调 `temporal_runtime.reset_workflow(workflow_id, run_id, reason=...)`；新 run_id 回写 `workflow_executions.run_id`；task 状态置回"执行中"
- 修改 `get_task`（`workflow_operations.py:79-85`）：当 `task["workflowType"] == "kg.custom.steps"` 时调 `handle.query("get_steps")`，把结果塞进 `task["steps"]`（覆盖静态 `_steps()`）；workflow 已终态时 query 失败则回退到静态
- 修改 `handle_review`（`workflow_operations.py:121-142`）：把 `retry_review` 的"重新执行"分支替换为"signal 恢复"——workflow 仍在 RUNNING 时调 `submit_review`，否则 fallback 到现有 `execute_definition` 重跑

### `service/temporal_runtime.py`
- 新增 `reset_workflow(workflow_id, run_id, reason)` 方法：调 Temporal client 的 reset API（SDK 方法名实施时确认；Python SDK 一般是 `client.reset_workflow_execution(workflow_id=..., run_id=..., task_id=..., reason=...)` 或 `WorkflowHandle.reset(...)`）。返回新 run_id。

### `biz/handler/workflow_system.py`
- 新增 `POST /workflow-system/definitions/steps`：上传 step pipeline 定义（脚本 + manifest）
- 复用 `POST /workflow-system/definitions/{id}/execute`（已有）触发 `kg.custom.steps`

### `biz/handler/task_center.py`
- 新增 `POST /task-center/tasks/{taskId}/review`：body `{decision: "approve"|"reject", modifiedResult?: dict, note?: str}` → `workflow_operations.submit_review`
- 新增 `POST /task-center/tasks/{taskId}/retry`：→ `workflow_operations.retry_task`
- `GET /task-center/tasks/{taskId}` 已有；改动在 service 层 `get_task`

### `biz/schema/workflow_system.py` 或新文件
- 新增 `StepPipelineDefinitionCreate` Pydantic 请求模型（filename, content_base64, steps, definitionId?, name?）
- 新增 `StepManifest` 子模型（id, name, functionName, timeoutSeconds?, retryPolicy?, requireReview?）
- 新增 `RetryPolicyConfig` 子模型
- 新增 `TaskReviewRequest` / `TaskRetryRequest` 请求模型

## 待确认决策（4 点，默认已选）

### 1. Reset 的事件点选择
**默认**：`LastWorkflowTask`——回放最近一个 workflow task，适合"activity 重试耗尽失败"场景，无需解析 event history。SDK 一般支持 `reset_type` 枚举（FirstWorkflowTask / LastWorkflowTask / BuildIdBased / 指定 event ID）。倾向最简。

### 2. 审核结果修正
**默认**：允许 `modifiedResult` 覆盖 `prev_outputs[step_id]`，下游 step 用修正值。这是"人工审核"的核心价值（不仅 approve/reject，还能改值）。若产品要求"只能 approve/reject 不能改值"，把 `modifiedResult` 字段去掉即可。

### 3. manifest `requireReview` 默认
**默认**：`false`。KG 构建里 `extract`/`align` 这类易错步在示例 manifest 中显式标 `true`。由 manifest 作者按需声明，不在 workflow 里强制。

### 4. signal 鉴权
**默认**：在 backend handler 层做权限校验（`/task-center/tasks/{id}/review` 检查 reviewer 角色/权限），workflow 信任 signal 来源——和现有 `handle_review` 的鉴权位置一致。不在 workflow 内做白名单校验（避免 workflow 依赖用户管理服务）。

## 实施步骤（分阶段）

### 阶段 1：核心 workflow + activity（最小可跑）
1. `service/temporal_workflows.py`：加 `StepPipelineWorkflow` + `execute_pipeline_step` + `_retry_policy`，注册到 `WORKFLOW_CLASSES`/`ACTIVITIES`
2. 写一个示例 step pipeline 脚本（如改造 `script/workflows/project_ingest_workflow.py` 的 `schema`/`load`/`align`/`cleanup` 四个内部函数为 `step_schema(payload, ctx)` 等）
3. `service/workflow_operations.py`：加 `create_step_pipeline_definition`，手工 seed 一个 definition 跑通
4. 跑通"4 步流水线 + per-step 重试 + query get_steps"的最小闭环

### 阶段 2：失败重试（reset）
5. `service/temporal_runtime.py`：加 `reset_workflow` 方法
6. `service/workflow_operations.py`：加 `retry_task`
7. `biz/handler/task_center.py`：加 `POST /tasks/{id}/retry`
8. 故意让 step 3 失败，验证 reset 后从 step 3 重跑、step 1-2 不重跑

### 阶段 3：人工审核（signal）
9. `service/workflow_operations.py`：加 `submit_review`，改 `handle_review`
10. `biz/handler/task_center.py`：加 `POST /tasks/{id}/review`
11. manifest 标记某步 `requireReview: true`，验证 workflow 暂停在 PENDING_REVIEW，signal 后继续

### 阶段 4：UI 集成
12. `get_task` 改造：`workflowType == "kg.custom.steps"` 时 query `get_steps` 覆盖 `task["steps"]`
13. 前端任务详情页：渲染 step 时间线（status/output/duration/attempt）；PENDING_REVIEW 时显示审核按钮；FAILED 时显示重试按钮

### 阶段 5：文档与示例
14. 写一个 step pipeline 模板脚本 + manifest，放 `backend/script/workflows/` 作为参考
15. 更新 `backend/docs/workflow_operations_api.md`：加 `kg.custom.steps` 章节、新增的 review/retry 端点

## 验证清单

- [ ] 上传一个 4 步 step pipeline definition，AST 校验通过
- [ ] 触发后 workflow 跑完 4 步，`get_steps` query 返回 4 个 COMPLETED
- [ ] 故意让 step 3 抛异常，`retryPolicy.maximumAttempts=3` 下 step 3 重试 3 次后 workflow FAILED
- [ ] 调 `POST /tasks/{id}/retry`，新 run_id 写回，step 1-2 不重跑、step 3 重新执行、step 4 继续
- [ ] manifest 标 step 2 `requireReview: true`，workflow 暂停在 PENDING_REVIEW；调 `POST /tasks/{id}/review` 提交 `modifiedResult`，workflow 用修正值继续 step 3
- [ ] `GET /task-center/tasks/{id}` 在 workflow 运行中能返回当前 step 状态（非静态 demo）
- [ ] dev2 stack（`docker-compose.dev2.yml`）跑通端到端：上传→触发→query→review→retry
- [ ] 老 `kg.custom.python` 脚本仍能正常跑（回归）
- [ ] `kg.entity.project`（走 `_run_domain_pipeline`）仍能正常跑（回归）

## 不在本次范围

- `kg.entity.*` / `kg.relation.*` 硬编码 workflow 类的清理（保留，逐步迁移）
- 老 `kg.custom.python` 单函数脚本的迁移（保留，按需迁移）
- `paper_journal_chain_etl.py` 这类已有内部多函数的脚本改造为 `kg.custom.steps`（可作为示例，但不在核心实施内）
- Search Attributes / 跨 workflow 查询（暂不需要）
- Workflow retention 配置调整（依赖运维，建议 ≥30 天但不在代码范围）
