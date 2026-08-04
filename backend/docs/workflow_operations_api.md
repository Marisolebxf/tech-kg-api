# 任务中心、人工审核与工作流 API

基础路径为 `/api/v1`。所有 JSON 错误使用 `{code, success, data, msg}`，且 `code` 与 HTTP 状态码一致。

## 异步受理契约

以下接口返回 HTTP `202`：

- `POST /task-center/trigger`
- `POST /workflow-system/definitions/{id}/execute`
- `POST /workflow-system/schedules/{id}/trigger`
- `POST /schema-management/schemas/{id}/execute`

创建任务的接口返回：

```json
{
  "code": 202,
  "success": true,
  "data": {
    "taskId": "PI-20260804-ABC123",
    "executionId": "EXEC-...",
    "workflowId": "...",
    "statusUrl": "/api/v1/workflow-system/executions/EXEC-.../status",
    "task": {},
    "execution": {}
  },
  "msg": "请求已受理"
}
```

受理成功只表示记录已保存或已下发，不表示工作流完成。

## 任务中心

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/task-center/overview` | 汇总、最近批次、更新策略和数据源状态 |
| GET | `/task-center/batches` | 批次列表 |
| GET | `/task-center/tasks` | 按状态、业务域、阶段、类型、批次和时间筛选 |
| GET | `/task-center/tasks/{taskId}` | 任务输入、输出、日志、批次和 Temporal 标识 |
| GET | `/task-center/data-sources/health` | 数据源与 Temporal 健康状态 |
| GET | `/task-center/data-sources/updates` | 数据源更新记录 |
| GET/PUT | `/task-center/update-policy` | 读取或更新自动建图策略 |
| POST | `/task-center/trigger` | 立即启动图谱构建 |

立即触发会在同一请求内创建当日批次。任务类型按请求生成：仅实体为“实体”，仅关系为“关系”，两者都有为“实体与关系”；业务域由 `domains` 生成，不再固定为综合域。

## 人工审核

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/manual-reviews` | 审核任务筛选 |
| GET | `/manual-reviews/{id}` | 审核详情和关联任务 |
| GET | `/manual-reviews/{id}/flow` | 处理流程 |
| POST | `/manual-reviews/{id}/actions` | 提交裁决，可选择重跑 |
| PUT | `/manual-reviews/{id}/result` | 修改结果 |
| POST | `/manual-reviews/{id}/retry` | 重试 |
| POST | `/manual-reviews/{id}/revoke` | 撤销 |

## 工作流定义

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workflow-system/definitions` | 定义列表 |
| POST | `/workflow-system/definitions` | 创建声明式定义，成功返回 `201` |
| POST | `/workflow-system/definitions/python` | 上传包含 `workflow(payload)` 的 Python 文件 |
| GET | `/workflow-system/definitions/{id}` | 定义详情 |
| POST | `/workflow-system/definitions/{id}/execute` | 执行定义，返回 `202` |

创建接口不再覆盖同 ID 定义；冲突返回 `409`。多个声明式定义可以共享 `kg.custom.configurable` Workflow Type。当前没有定义版本历史和发布/回滚模型，修改应通过新 ID 创建新定义。

客户端传入的 `workflowId` 会先检查本地执行记录，重复 ID 返回 `409`，避免把 Temporal 的重复 ID 错误误记为本地排队。

## 执行状态

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workflow-system/executions/{id}` | 本地执行快照 |
| GET | `/workflow-system/executions/{id}/status` | 调用 Temporal Describe 获取实时状态并回写本地记录 |

状态接口在工作流完成时返回 `output`，失败时返回 `failure`。Temporal 不可用时保留本地快照，并返回 `live=false` 和 `liveError`。

所有受控根 Workflow 都携带 `_control.workflowId`。完成、失败或取消时，Worker 执行 `record_workflow_outcome` Activity，主动更新 execution、关联 task 和 batch。回写失败由 Temporal Activity 自动重试；状态接口同时保留为主动校验通道。

## Schedule

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workflow-system/schedules` | Schedule 列表 |
| POST | `/workflow-system/definitions/{id}/schedules` | 创建 Schedule |
| PUT | `/workflow-system/schedules/{id}/state` | 暂停或恢复 |
| POST | `/workflow-system/schedules/{id}/trigger` | 立即执行关联定义并返回 task/execution/workflow ID |
| DELETE | `/workflow-system/schedules/{id}` | 删除 |

“立即触发”通过关联定义创建一次独立、可追踪的执行，因此可以稳定返回 ID；定时触发仍由 Temporal Schedule 管理。

## 降级与补偿

Temporal 首次下发失败时，execution 保存为：

- `status=QUEUED`
- `dispatchMode=LOCAL_FALLBACK`

API lifespan 启动补偿下发器，按 `WORKFLOW_RETRY_INTERVAL_SECONDS`（默认 30 秒）重试。成功后更新为 `dispatchMode=TEMPORAL_RETRY`，并保留原 execution ID 和 workflow ID。

该机制保证“下发重试”，不等同于完整的消息队列：多 API 副本会同时扫描共享 SQLite 时不适用。生产多副本部署应改用共享数据库和带租约/锁的 outbox worker。

## 内置 Workflow Type

- 实体：`kg.entity.paper`、`kg.entity.scholar`、`kg.entity.patent`、`kg.entity.organization`
- 关系：`kg.relation.authorship`、`kg.relation.employment`、`kg.relation.citation`、`kg.relation.cooperation`
- 总流程：`kg.graph.build`
- Schema：`kg.schema.execute`
- 自定义：`kg.custom.configurable`、`kg.custom.python`

本地 Worker：

```bash
uv run python -m script.run_temporal_worker
```

上传脚本具备 Worker 进程权限，只应向受信任管理员开放；生产环境建议使用独立容器、只读文件系统、资源配额和网络限制。
