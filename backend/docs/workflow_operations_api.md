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
- 自定义：`kg.custom.configurable`、`kg.custom.python`

`kg.entity.project` 在 Activity 中真实执行国内外项目 ETL：`ensure_schema` → `load_project_graph` → `align_project_relations` → `cleanup_project_stubs`（可通过 payload 的 `limit`/`dry_run`/`skip_*` 控制）。其它实体域步骤目前仍为轻量完成桩。

`kg.graph.build` 会为请求中的每一种实体和关系启动独立子工作流。上传的 Python 函数由 `kg.custom.python` 包装，并在 Activity 隔离子进程执行，避免破坏 Temporal Workflow 的确定性重放。

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
