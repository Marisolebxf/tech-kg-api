# 人工审核与修正中心

> 来源：`CLAUDE.md` · `docs/人工审核模块.md`

## 人工审核（Manual Review）

生产化审核服务（`service/manual_review_production.py`），路由 `/api/v1/manual-review`（admin 鉴权，网关身份头）。数据模型在 `db_model/manual_review.py`：cases（待审案例）/ drafts（草稿）/ decisions（决定）/ evidence（附件）/ audit（审计）。

- **模板收敛**：三个产活模板——T_DIRECT（入库直判写图）/ T_LINK（同名冲突实体对齐裁决）/ T_EXTRACT_FAIL（抽取失败记录重跑）；6 个休眠模板与 graph-build 移交通道已删除（2026-09-15）；
- **边界**：审核裁决直接在本仓库内落地——T_DIRECT accept 直写图库、T_LINK 决议入库（合并执行由向量对齐合并引擎落地，后续任务）、T_EXTRACT_FAIL 触发重跑执行；不再有外部交接通道；
- **设计原则**：审核是**事后队列**——抽取流水线完整跑完后，结果整批进审核队列，审核员 accept / reject；不做运行中暂停等待（不使用 Temporal signal/wait_condition 挂起工作流）。

## 前端

`views/platform/OperationsCenterView.vue`：审核队列（A 入库决策 / C 抽取失败重跑双 tab，C 类批量重跑）；`views/platform/ManualReviewWorkspaceView.vue`：审核工作台（T_DIRECT / T_EXTRACT_FAIL / T_LINK 三套专用布局，claim + 心跳）；流程实例详情页（`ProcessInstanceDetailView.vue`）可下钻单个执行。

## 修正中心

数据已落图后的**人工修正**走修正中心（`/api/v1/corrections`）——ledger + 状态机 + 可靠 MySQL/图同步，详见[权限边界与治理](/arch/admin#修正中心-api-v1-corrections)。
