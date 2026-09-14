# Temporal 工作流系统

> 来源：`docs/工作流系统模块.md`（权威文档）· `CLAUDE.md` 工作流系统节

路由 `/api/v1/workflow-system`（admin 鉴权）；任务中心 `/api/v1/task-center` 读同一套控制面表。Temporal 引擎执行，配 **MySQL 控制面** `techkg_control`（`service/workflow_repository.py` + `infra/workflow_mysql.py`，env `WORKFLOW_MYSQL_*`，跑在 temporal-mysql 实例——旧 SQLite / `WORKFLOW_DATABASE_PATH` 路径已不存在）。

## 执行模型

| 部件 | 说明 |
|---|---|
| Temporal server | `TEMPORAL_ADDRESS`；dev2 栈自带 `temporal-dev2` + `temporal-mysql-dev2` |
| temporal-worker 容器 | **唯一 worker**（`script/run_temporal_worker.py` 长进程）；api 进程内 worker 已删除 |
| 控制面 MySQL | `techkg_control`：定义 / 执行 / Schedule / Job / tasks 等七表 |
| 用户脚本 | Schema 抽取的 `transform` 以隔离子进程运行；`KG_SCRIPT_CTX` 注入连接参数、`KG_ACCESS_LOG` 注入溯源 sidecar 路径 |

全部 workflow 注册到唯一队列 `TEMPORAL_TASK_QUEUE`（默认 `tech-kg-workflows`）。

::: warning 并发与重试封顶
worker 的并发与重试被刻意**封顶**——历史上曾因重试风暴打穿 trs-graph session 池。调整这两项参数前先评估图服务的承载。
:::

## 两类工作流定义

| workflowType | 来源 | 说明 |
|---|---|---|
| `kg.schema.extract` | Schema 目录合成（`schema-extract-{id}`） | **主通道**：平台按来源绑定分批读源 → 用户 `transform(payload)` 转换 → 平台写图 / 消歧 / 索引 / 推水位（详见 [Schema 管理](/arch/schema)） |
| `kg.custom.configurable` | `POST /definitions` 手工创建 | declarative 记账定义，steps 跑 workflow 内联纯记账 stub（不引用真实 ETL） |

::: info 2026-09-14 收敛
独立脚本上传通道（`kg.custom.python` / `kg.custom.steps` / `kg.custom.chain`）、builtin 域 stub 族（`kg.entity.*` / `kg.relation.*` / `kg.graph.build`）与算子注册表已全部下线——**用户代码唯一入口是 Schema 管理上传，唯一执行引擎是 `kg.schema.extract`**；Job 只剩 `extract` 一种任务类型。
:::

## 设计取向

- **Temporal 原生机制优先**：signal / reset / query / event history replay，**不引入**自建 DB checkpoint 表；
- **审核是事后队列**：抽取跑完后低置信 / 消歧候选进人工审核队列（T_LINK / T_EXTRACT_FAIL），审核员 accept / reject——不是运行中暂停等待（详见[人工审核](/arch/review)）；
- 失败恢复：`POST /task-center/tasks/{id}/retry` 走 Temporal **ResetWorkflowExecution** 回放；抽取水位由平台按来源管理——该来源全部批次成功后一次性推进，失败停在上一轮，下轮断点续读。

## 触发方式

| 入口 | 说明 |
|---|---|
| Schema 抽取 | Schema 管理页触发 / 回填，或 Job 手动触发（选 schema + batchSize） |
| 任务中心全量 | `POST /task-center/trigger` 遍历可抽取 schema（已传脚本且绑定来源），逐个启动 `kg.schema.extract`，返回 `{executions, skipped}` |
| cron Job | `POST /workflow-system/jobs` 自动建 `{job_id}-sched` Schedule；启停 Job 同步 pause/resume Schedule |
| 自动策略 | 任务中心 update-policy：频率映射 cron，为每个可抽取 schema 维护 `auto-extract-{schemaId}` Schedule |
| declarative 手动 | `POST /workflow-system/definitions/{id}/execute`；Temporal 不可用降级 LOCAL_FALLBACK 落库待下发 |
