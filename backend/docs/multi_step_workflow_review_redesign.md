# 多步骤流水线人工审核重设计（post-hoc 队列）

## 背景

`backend/docs/multi_step_workflow_plan.md` 里原来设计的"signal + wait_condition" in-flight 审核模型是错的：一个 step 触发 `requireReview: true` 会让整个 workflow 暂停，等审核者 signal 才继续。对数据处理流水线这是反模式——一个低置信度 item 卡住整批 25k 条数据的下游处理。

正确模型是 post-hoc：pipeline 跑完，中间过程发现的需要审核的候选实体/关系**抛出来单独入队**，pipeline 用自动通过的部分继续下游。审核者异步处理队列，每个候选只有两个动作：accept 直接灌图，reject 丢弃。**审核决策与 workflow 完全解耦**，不重启任何 workflow。

## 设计目标

1. Step 函数能声明"这部分候选需要人审"，pipeline 不暂停
2. 候选项带齐灌图所需全部字段（kind/nodeLabel/candidate/evidence），审核者 accept 时直接拿来写图
3. 复用现有 ProductionReview 表 + UI（`ManualReviewWorkspaceView`）+ worker
4. 只有 accept / reject 两个动作，没有 retry（如果候选错了就 reject，不重新抽取）
5. 删掉 in-flight pause 相关的所有代码（requireReview / signal / inline form）

## 架构总览

```
step_extract(payload, ctx)
    ↓ returns {"entities": [...], "pendingReview": [{kind, nodeLabel, candidate, reason, evidence}, ...]}
execute_pipeline_step activity
    ↓ pop pendingReview, 逐条调 production_service.create_case
    ↓ 返回给下游的 prevOutputs[stepId] 只剩 entities
StepPipelineWorkflow
    ↓ 继续跑 step_align / step_persist，不暂停
    ↓ workflow COMPLETED

异步：
ManualReviewWorkspaceView
    ↓ 审核者看到 ReviewCase 队列
    ↓ accept → production_service.approve(case_id, approved=True)
        → graph.merge_node / create_edge 直接写图
        → case.status = RESOLVED
    ↓ reject → production_service.approve(case_id, approved=False)
        → case.status = REJECTED，无 graph 副作用
```

## Step 函数契约

`pendingReview` 字段是约定优于配置的硬编码键名。每条 item 必须带齐灌图所需字段：

```python
def step_extract(payload: dict, ctx: dict) -> dict:
    items = payload["items"]
    approved, pending = [], []
    for item in items:
        result = extract(item)
        if result["confidence"] < 0.85:
            pending.append(
                {
                    "kind": "entity",  # "entity" | "relation"
                    "nodeLabel": "Scholar",  # entity 用：图标签
                    # 关系用：edgeType / fromId / toId
                    "candidate": {  # 完整可灌图数据
                        "scholar_id": "S12345",
                        "name_zh": "张三",
                        "org": "中科院自动化所",
                    },
                    "reason": "置信度 0.78 < 0.85",
                    "confidence": 0.78,
                    "evidence": [  # 来源证据，审核者参考
                        {
                            "table": "dwd_scholar",
                            "record_id": "...",
                            "field": "name_zh",
                            "raw": "张三",
                        }
                    ],
                }
            )
        else:
            approved.append(result)
    return {
        "entities": approved,  # 下游 step_align 用这个
        "pendingReview": pending,  # activity 自动抽取，不传给下游
    }
```

**关系候选**的字段：
```python
{
    "kind": "relation",
    "edgeType": "AUTHORED_BY",  # 边类型
    "fromId": "S12345",  # 起点节点 vid
    "toId": "P67890",  # 终点节点 vid
    "candidate": {"role": "第一作者", "year": 2024},
    "reason": "...",
    "evidence": [...],
}
```

## Activity 后处理

`service/temporal_workflows.py:execute_pipeline_step` 改：用户函数返回后，pop `pendingReview`，逐条调 `production_service.create_case`：

```python
@activity.defn
async def execute_pipeline_step(request: dict[str, Any]) -> dict[str, Any]:
    output = await _run_user_function_in_subprocess(...)  # 现有逻辑
    pending = output.pop("pendingReview", [])
    if pending:
        from service.manual_review_production import manual_review_service

        for item in pending:
            manual_review_service.create_case(
                task_id=request.get("taskId"),
                execution_id=request.get("executionId"),
                step_id=request["stepId"],
                kind=item["kind"],
                node_label=item.get("nodeLabel"),
                edge_type=item.get("edgeType"),
                from_id=item.get("fromId"),
                to_id=item.get("toId"),
                candidate=item["candidate"],
                reason=item.get("reason", ""),
                confidence=item.get("confidence"),
                evidence=item.get("evidence", []),
                workflow_id=...,  # 从 ctx 取
            )
    return {"step": request["stepId"], "status": "COMPLETED", "output": output, "attempt": attempt}
```

下游 step 拿到的 `ctx.prevOutputs[stepId]` 已经不含 `pendingReview`，只有 `entities` 等自动通过字段。

## ReviewCase schema 需要

复用 `db_model/manual_review.py:ReviewCase` 表。检查现有字段是否够：

| 字段 | 是否已有 | 用途 |
|---|---|---|
| `id` | 已有 | case_id |
| `status` | 已有 | OPEN/CLAIMED/RESOLVED/REJECTED |
| `assignee_id`/`assignee_name` | 已有 | 审核者 |
| `version` | 已有 | 乐观锁 |
| `sla_claim_at`/`sla_resolve_at` | 已有 | SLA |
| `workflow_id`/`workflow_run_id` | 已有 | 来源 workflow |
| `domain`/`category`/`batch_id` | 已有 | 分类 |
| `candidate` | **可能要加** | JSON 列，存候选实体/关系数据 |
| `kind` | **可能要加** | "entity" / "relation" |
| `node_label`/`edge_type`/`from_id`/`to_id` | **可能要加** | 灌图所需元信息 |
| `reason`/`confidence`/`evidence` | **可能要加** | 审核者参考信息 |
| `step_id`/`task_id`/`execution_id` | **可能要加** | 来源定位 |

**实施时先 read `db_model/manual_review.py` 确认现有 schema，按需 add column（用 alembic 或 SQLAlchemy `alter table`）。**

## `production_service` 改造

### 新增 `create_case`（activity 调用）

```python
def create_case(self, *, task_id, execution_id, step_id, kind, candidate,
                node_label=None, edge_type=None, from_id=None, to_id=None,
                reason="", confidence=None, evidence=None, workflow_id=None):
    """从 pipeline pendingReview 项创建一个 ReviewCase，入队等待审核。"""
    case = ReviewCase(
        id=f"CASE-{uuid4().hex[:16].upper()}",
        status="OPEN",
        workflow_id=workflow_id,
        candidate=dump(candidate),
        kind=kind,
        node_label=node_label,
        edge_type=edge_type,
        from_id=from_id,
        to_id=to_id,
        reason=reason,
        confidence=confidence,
        evidence=dump(evidence or []),
        task_id=task_id,
        execution_id=execution_id,
        step_id=step_id,
        domain=...,  # 从 workflow context 取
        ...
    )
    session.add(case)
    session.add(ReviewOutbox(...))  # 触发 worker 处理
    return case
```

### `approve` 改造：accept 时直接写图

```python
def approve(self, case_id, version, approved, note, identity):
    case = self._load_case_for_update(case_id, version)  # 现有乐观锁
    require_role(identity, "reviewer")
    
    if approved:
        graph = get_trs_graph_client()   # infra/graph_db 单例
        if case.kind == "entity":
            graph.merge_node(case.node_label, json.loads(case.candidate))
        elif case.kind == "relation":
            graph.create_edge(
                case.edge_type, case.from_id, case.to_id,
                json.loads(case.candidate),
            )
        case.status = "RESOLVED"
    else:
        case.status = "REJECTED"
    
    case.decision_note = note
    case.decided_by = identity.user_id
    case.decided_at = now()
    session.merge(case)
    session.add(ReviewAuditLog(case_id=case_id, action="approve" if approved else "reject", ...))
```

**重要**：approve 不调 `execute_definition`、不重启 workflow、不调 reset。审核决策与 workflow 完全解耦。

## 要删的代码清单

| 文件 | 删除内容 |
|---|---|
| `service/temporal_workflows.py:StepPipelineWorkflow` | `if step.get("requireReview"):` 整块 + `wait_condition` + `@workflow.signal submit_review` + `@workflow.query get_steps` 里 PENDING_REVIEW 相关逻辑 |
| `service/workflow_operations.py` | `submit_review` 方法（整个） |
| `biz/handler/task_center.py` | `POST /tasks/{task_id}/review` 端点 |
| `biz/schemas/workflow_operations.py` | `TaskReviewRequest` 模型 + `StepManifest.require_review` 字段 |
| `frontend/src/views/platform/ProcessInstanceDetailView.vue` | inline 审核表单段（`<section v-if="isPipelineTask && pendingReviewStep">`）+ `handlePipelineReview` + reviewReviewer/reviewNote/reviewModifiedJson/reviewSubmitting 等 ref + review-actions CSS |
| `frontend/src/api/workflowOperations.ts` | `submitTaskReview` 函数 + `PipelineStepInfo.status` 里的 PENDING_REVIEW/REVIEWED/REJECTED 枚举值（保留 COMPLETED/RUNNING/FAILED） |

## 要保留的代码

- `StepPipelineWorkflow` 主体（for 循环 + per-step activity + retry_policy）—— 不变
- `execute_pipeline_step` 子进程 runner —— 不变，只加后处理
- `POST /task-center/tasks/{id}/retry`（reset 重试，跟审核无关）—— 保留
- `RetryPolicyConfig` / `StepManifest`（除 require_review）—— 保留
- `sample_step_pipeline.py` 4 步示例 —— 保留，但可加 `pendingReview` 演示

## UI 改动

`ManualReviewWorkspaceView.vue` 复用现有，但删/隐藏 retry 按钮：

- accept 按钮 → 现有 `approveProductionReview`，后端走 `production_service.approve(approved=True)` → 直接写图
- reject 按钮 → 现有 `rejectProductionReview`，后端走 `production_service.approve(approved=False)` → 仅标记
- retry 按钮 → 隐藏（`v-if="!isPipelineCase"`）或直接删

case 详情区显示候选数据：`candidate` JSON、`reason`、`confidence`、`evidence` 表格、来源 step/workflow 链接。

## 实施步骤

### 阶段 1：数据模型
1. read `db_model/manual_review.py` 确认 ReviewCase 现有字段
2. 加 `candidate`/`kind`/`node_label`/`edge_type`/`from_id`/`to_id`/`reason`/`confidence`/`evidence`/`step_id`/`task_id`/`execution_id` 列（如果缺）
3. 写迁移脚本（或 `Base.metadata.create_all` 幂等新增列）

### 阶段 2：service 层
4. `service/manual_review_production.py`：加 `create_case` 方法
5. `service/manual_review_production.py`：改 `approve` 方法，accept 时调 `graph.merge_node`/`create_edge` 直接写图
6. `service/temporal_workflows.py:execute_pipeline_step`：加后处理 pop `pendingReview` + 逐条 `create_case`

### 阶段 3：删旧代码
7. `service/temporal_workflows.py:StepPipelineWorkflow`：删 requireReview + signal + wait_condition
8. `service/workflow_operations.py`：删 `submit_review`
9. `biz/handler/task_center.py`：删 `POST /tasks/{id}/review`
10. `biz/schemas/workflow_operations.py`：删 `TaskReviewRequest` + `StepManifest.require_review`
11. `frontend/src/views/platform/ProcessInstanceDetailView.vue`：删 inline 审核表单 + 相关 ref/handler
12. `frontend/src/api/workflowOperations.ts`：删 `submitTaskReview`

### 阶段 4：UI
13. `ManualReviewWorkspaceView.vue`：隐藏/删除 retry 按钮；case 详情区渲染 candidate/reason/confidence/evidence
14. 可选：`ProcessInstanceDetailView` 在 step 详情里显示"已抛出 N 条候选待审"摘要（读 ReviewCase by task_id）

### 阶段 5：示例与文档
15. `sample_step_pipeline.py`：加一个低置信度分支演示 `pendingReview` 字段
16. 更新 `backend/docs/workflow_operations_api.md`：step 函数契约 + pendingReview 字段说明
17. 更新 `backend/docs/multi_step_workflow_plan.md`：标注审核部分被本设计取代

## 验证清单

- [ ] sample_step_pipeline.py 加低置信度分支，触发后 pipeline 4 步 COMPLETED，不暂停
- [ ] `get_steps` query 返回 4 个 COMPLETED，无 PENDING_REVIEW
- [ ] ReviewCase 表里能看到抛出的 N 条 pending item（含 candidate/reason/evidence）
- [ ] `ManualReviewWorkspaceView` 显示这些 case，有 accept/reject 两按钮，**无 retry 按钮**
- [ ] accept 后调 `graph.get_node` 能查到候选实体（直接写图成功）
- [ ] reject 后 case 状态 REJECTED，`graph.get_node` 查不到
- [ ] 老 `kg.custom.python` workflow 仍能跑（回归）
- [ ] `POST /tasks/{id}/retry`（reset）仍工作（与审核无关，未受影响）

## 不在本次范围

- 现有 ProductionReview 的 claim/heartbeat/SLA/draft 机制 —— 全保留
- `production_service.retry` 方法 —— 保留（其它 workflow 可能用，只是 UI 不暴露给 kg.custom.steps case）
- 现有 `reviews` 表（basic manual review） —— 不动
- `CorrectionCenterView` —— 不动
