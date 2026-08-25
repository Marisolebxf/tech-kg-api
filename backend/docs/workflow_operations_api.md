# 任务中心、人工审核与工作流 API

统一前缀为 `/api/v1`，响应结构为 `{ code, success, data, msg }`。

## 任务中心

- `GET /task-center/overview`：页面汇总、最近批次、变更汇总、更新策略、数据源状态。
- `GET /task-center/batches`：更新批次列表。
- `GET /task-center/tasks`：任务筛选。支持 `status`（执行中/执行出错/等待人工审核/执行完成）、`domain`、`stage`、`kind`、`batchId`、`startTime`、`endTime`、`keyword`、分页。
- `GET /task-center/tasks/{taskId}`：任务输入、输出、日志、Temporal 标识和完整步骤。
- `GET /task-center/data-sources/health`：数据源健康状态。
- `GET /task-center/data-sources/updates`：按业务域和 `since`/`until` 获取源数据更新。
- `GET /task-center/update-policy`：读取自动建图策略。
- `PUT /task-center/update-policy`：保存策略并创建或更新 Temporal Schedule。
- `POST /task-center/trigger`：立即启动图谱构建总工作流。

## 人工审核

- `GET /manual-reviews`：按状态、业务域、分类、批次、时间和关键字筛选。
- `GET /manual-reviews/{id}`：审核对象、证据、原结果、处置结果和关联任务。
- `GET /manual-reviews/{id}/flow`：查看人工处理详细流程。
- `POST /manual-reviews/{id}/actions`：提交裁决，可通过 `rerun=true` 从阻断节点重跑。
- `PUT /manual-reviews/{id}/result`：修改任务结果但不结束审核。
- `POST /manual-reviews/{id}/retry`：重试任务。
- `POST /manual-reviews/{id}/revoke`：撤销人工任务。

## 工作流定义、执行和调度

- `GET/POST /workflow-system/definitions`：查询或创建声明式自定义工作流。
- `POST /workflow-system/definitions/python`：上传 Python 脚本。脚本必须提供同步或异步的 `workflow(payload)` 函数。
- `POST /workflow-system/definitions/{id}/execute`：客户端直接执行指定工作流。
- `GET /workflow-system/executions/{id}`：查看执行下发记录。
- `POST /workflow-system/definitions/{id}/schedules`：创建 Temporal Schedule。
- `GET /workflow-system/schedules`：查询 Schedule。
- `PUT /workflow-system/schedules/{id}/state`：暂停或恢复 Schedule。
- `POST /workflow-system/schedules/{id}/trigger`：立即触发 Schedule。
- `DELETE /workflow-system/schedules/{id}`：删除 Schedule。
- `GET /workflow-system/health`：Temporal 连接状态。

内置工作流类型包括：

- 实体：`kg.entity.paper`、`kg.entity.scholar`、`kg.entity.patent`、`kg.entity.organization`、`kg.entity.project`
- 关系：`kg.relation.authorship`、`kg.relation.employment`、`kg.relation.citation`、`kg.relation.cooperation`
- 总流程：`kg.graph.build`
- 自定义：`kg.custom.configurable`、`kg.custom.python`、`kg.custom.steps`

`kg.entity.project` 在 Activity 中真实执行国内外项目 ETL：`ensure_schema` → `load_project_graph` → `align_project_relations` → `cleanup_project_stubs`（可通过 payload 的 `limit`/`dry_run`/`skip_*` 控制）。其它实体域步骤目前仍为轻量完成桩。

`kg.graph.build` 会为请求中的每一种实体和关系启动独立子工作流。上传的 Python 函数由 `kg.custom.python` 包装，并在 Activity 隔离子进程执行，避免破坏 Temporal Workflow 的确定性重放。

### `kg.custom.steps` 多步骤流水线

多步骤实体构建工作流。每步是一个 Temporal Activity（独立 retry policy + timeout），状态由 workflow state 持有，UI 通过 `@workflow.query get_steps` 实时读取。失败后用 `ResetWorkflowExecution` 回放，已完成步不重跑（event history replay）；人工审核用 `@workflow.signal submit_review` 暂停-恢复。

- `POST /workflow-system/definitions/steps`：上传 step pipeline 定义。Form 字段：`file`（Python 脚本，含多个 step 函数）、`steps`（JSON 编码的 manifest 列表）、可选 `definition_id`/`name`。AST 校验所有 `functionName` 都在脚本里、`id` 唯一。返回 `workflowType: "kg.custom.steps"` 的定义。
- `POST /workflow-system/definitions/{id}/execute`：触发执行（同 `kg.custom.python`）。payload 透传给每个 step 函数。
- `POST /task-center/tasks/{taskId}/retry`：失败重试。body `{reason?}`。调 Temporal `ResetWorkflowExecution`，回放到最近一个 workflow task，新 `run_id` 回写 `workflow_executions`/`tasks`。
- `POST /task-center/tasks/{taskId}/review`：人工审核。body `{decision: "approve"|"reject", modifiedResult?, note?, reviewer?}`。向 workflow 发 `submit_review` signal，恢复暂停在 `PENDING_REVIEW` 的 step。`modifiedResult` 覆盖下游 `prevOutputs[stepId]`。

#### Step 函数契约

```python
def step_xxx(payload: dict, ctx: dict) -> dict: ...
```

`ctx` 含 `stepId`/`attempt`/`prevOutputs`/`executionId`/`taskId`/`definitionId`。返回 JSON-able dict。`prevOutputs` 是上游 step 的输出，按 step_id 索引。

#### Manifest 字段

```json
{
  "id": "extract", "name": "实体抽取", "functionName": "step_extract",
  "timeoutSeconds": 1200,
  "retryPolicy": {"maximumAttempts": 3, "initialIntervalSeconds": 5, "maximumIntervalSeconds": 100, "nonRetryableErrorTypes": ["ValueError"]},
  "requireReview": true
}
```

- `id`：step 唯一标识，`^[a-z0-9][a-z0-9_-]{0,63}$`
- `functionName`：脚本里的函数名
- `timeoutSeconds`：默认 600
- `retryPolicy.maximumAttempts`：默认 1（不重试）；stateful 步骤如 `persist` 应保持 1 避免重复写入
- `requireReview`：默认 `false`；为 `true` 时该步完成后 workflow 暂停等待 `submit_review` signal

#### 示例

参考 `backend/script/workflows/sample_step_pipeline.py`：4 步流水线 `load → extract → align → persist`，每步读 `ctx.prevOutputs`，`payload.fail_at` 可触发指定 step 失败用于验证 reset 重试。

完整设计文档：[`backend/docs/multi_step_workflow_plan.md`](multi_step_workflow_plan.md)。

## 启动

```bash
docker compose up -d temporal-postgresql temporal temporal-ui temporal-worker api web
```

Temporal UI 默认地址为 `http://localhost:8233`。本地直接启动 Worker：

```bash
cd backend
uv run python -m script.run_temporal_worker
```

Python 脚本执行具备服务器进程权限，只应向受信任的管理员开放；生产环境应进一步使用独立容器、资源配额和签名校验。
