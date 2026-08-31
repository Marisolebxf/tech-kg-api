# 人工审核与修正中心

> 来源：`CLAUDE.md` · `backend/docs/manual_review_page_redesign.md` · `backend/docs/multi_step_workflow_review_redesign.md`

## 人工审核（Manual Review）

生产化审核服务（`service/manual_review_production.py`），路由 `/api/v1/manual-review`（admin 鉴权）+ `/api/v1/manual-review-internal`（**无鉴权**，供审核 worker 回调）。数据模型在 `db_model/manual_review.py`：cases（待审案例）/ drafts（草稿）/ decisions（决定）/ audit（审计）。

- **边界**：审核服务与「图构建」之间有明确的 handoff 边界——审核通过的结果按约定交给图构建侧落图，审核系统本身不直接写图；
- **worker**：`script/run_manual_review_worker.py` 长进程消费队列，调用 internal 端点回写结果；
- **设计原则**：审核是**事后队列**——抽取流水线完整跑完后，结果整批进审核队列，审核员 accept / reject；不做运行中暂停等待（不使用 Temporal signal/wait_condition 挂起工作流）。

## 前端

`views/platform/ManualReviewWorkspaceView.vue`：审核工作台（案例列表、草稿编辑、通过/驳回、审计追踪）；流程实例详情页（`ProcessInstanceDetailView.vue`）可下钻单个执行。

## 修正中心

数据已落图后的**人工修正**走修正中心（`/api/v1/corrections`）——ledger + 状态机 + 可靠 MySQL/图同步，详见[权限边界与治理](/arch/admin#修正中心-api-v1-corrections)。
