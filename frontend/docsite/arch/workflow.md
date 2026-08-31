# Temporal 工作流系统

> 来源：`CLAUDE.md` 工作流系统节 · `backend/docs/multi_step_workflow_plan.md` · `backend/docs/workflow_operations_api.md`

路由 `/api/v1/workflow-system`（admin 鉴权）。用户定义的工作流组合已注册的算子，由 **Temporal** 引擎执行，配一个 **SQLite 控制面**（`service/workflow_repository.py`，路径 `WORKFLOW_DATABASE_PATH`）。

## 执行模型

| 部件 | 说明 |
|---|---|
| Temporal server | `TEMPORAL_ADDRESS`；dev2 栈自带 `temporal-dev2` + `temporal-mysql-dev2` |
| api 进程内 worker | `main.py` 同时启动一个进程内 Temporal worker |
| 独立 worker | `script/run_temporal_worker.py` 长进程；dev2 栈有 `tech-kg-temporal-worker-dev2` 容器 |
| 用户脚本 | 以子进程运行；`KG_SCRIPT_CTX` 注入连接参数、`KG_ACCESS_LOG` 注入溯源 sidecar 路径 |

::: warning 并发与重试封顶
worker 的并发与重试被刻意**封顶**——历史上曾因重试风暴打穿 trs-graph session 池。调整这两项参数前先评估图服务的承载。
:::

## 两种用户工作流

| 类型 | 形态 | 说明 |
|---|---|---|
| `kg.custom.python` | 单函数 `workflow(payload) -> dict` | 旧形态；SDK 经 `current_context()` 取上下文 |
| `kg.custom.steps` | 多步流水线 `step_xxx(payload, ctx) -> dict` | **推荐**；前一步输出自动进 `ctx.prev_outputs`，每步独立水位/超时/重试（manifest 定义） |

多步流水线的完整设计与审核耦合见 `backend/docs/multi_step_workflow_plan.md` 与 `multi_step_workflow_review_redesign.md`。

## 设计取向

- **Temporal 原生机制优先**：signal / reset / query / event history replay，**不引入**自建 DB checkpoint 表；
- **审核是事后队列**：抽取流水线跑完后进人工审核队列，审核员 accept/reject——不是运行中暂停等待（详见[人工审核](/arch/review)）；
- 失败恢复：失败 step 走 reset 重读上次成功水位，重处理同一窗口（幂等 upsert 保证不重不漏）。

## 触发

`POST /api/v1/workflow-system/definitions/{id}/execute`，可选携带资源选择器（`mysqlDatasourceId` / `graphSpace` / `llmConfigId` 等，见 [Context 触发端字段](/sdk/context#触发端字段名)）。
