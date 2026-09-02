# 权限边界与治理

> 来源：`backend/docs/admin_governance.md` · `CLAUDE.md`（修正中心节）

平台把「平台管理员」与普通用户的能力边界固化在路由分组上，并为人工治理提供两个子系统：**修正中心**（数据修正台账）与**人工审核**（抽取结果审核，见[人工审核](/arch/review)）。

## 权限边界

| 路由组 | 依赖 | 典型功能 |
|---|---|---|
| protected | `require_authenticated_user` | 九大图谱构建子功能、查询服务 |
| admin | + `require_platform_admin` | schema 管理、工作流系统、任务中心、人工审核工作台、修正中心、成员管理、配置管理 |
| internal | 无鉴权（内网） | `manual_review_internal`（审核 worker 回调）、operator internal |

配置类资源（语言模型 / 向量模型 / MySQL 数据源 / 向量数据空间 / 图数据空间、schema、工作流定义）**按创建者隔离**：普通用户只见自己创建的记录 + 平台预置项；admin 可见全部（详见任务中心 Job 注册表重构，2026-08-30）。

## 修正中心（`/api/v1/corrections`）

人工修正 ledger + 状态机 + MySQL/图数据库可靠同步（`service/correction.py`，模型在 `db_model/platform_governance.py`）：

- 每条修正是一个 ledger 记录，经状态机流转（草稿 → 待同步 → 已同步 / 失败……）；
- 同步走**后台 dispatcher**：每 `CORRECTION_SYNC_INTERVAL_SECONDS` 轮询到期任务，可靠地写 MySQL 与图（`CORRECTION_SYNC_WORKER_ENABLED` 门控，compose 里默认开，测试/CI 关闭）；
- 目标是把「人在界面上改的值」最终一致地落到图谱与业务库。

## 审计

认证审计日志写 Redis（带 TTL）；操作日志前端页面在 `views/auth/OperationLogsView.vue`。
