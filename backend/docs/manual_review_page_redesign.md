# 人工审核详情页 A 类重设计

> 目的：把审核页收敛成"快速判断实体/关系是否入库"的高吞吐决策工作台。
> B 类（T_MAP/T_DQ_FILL/T_DQ_MERGE/T_ATTR）数据修正任务 deferred 到 TODO，不在本次范围。
> T_RUNTIME 不入审核队列（瞬态自动重试 / 永久告警，另开任务）。

## A 类范围

3 个 template，都是"判入库 yes/no"型决策：

| Template | 决策 | 动作 |
|---|---|---|
| T_DIRECT | kg.custom.steps 抛出的低置信度候选 | accept→直接写图 / reject→丢弃 |
| T_LINK | 实体对齐裁决 | merge 到已有 / 新建实体 / 驳回 |
| T_EVIDENCE | 关系证据审核 | pass→入图 / reject→丢弃 |

## 页面结构

```
┌────────────────────────────────────────┐
│ CaseHeader（固定，A 类共享）              │
│   case_id · 状态徽章 · 风险 · SLA 倒计时  │
│   候选摘要: "实体 Paper P-2 (entity-2)"   │
│   来源: workflow_id / step / task_id       │
├────────────────────────────────────────┤
│ ModeIngestDecision（按 template 切子视图）│
│                                          │
│   T_DIRECT: 候选表单 + 理由 + 置信度条      │
│            + 来源证据表                   │
│            + [入库 ✓] [驳回 ✗]              │
│                                          │
│   T_LINK:   候选 vs 已有候选并排对比        │
│            + 属性差异高亮                  │
│            + [合并到已有] [新建] [驳回]      │
│                                          │
│   T_EVIDENCE: 关系摘要 + 证据列表（带       │
│              独立来源/同源标记）            │
│              + ≥2 独立来源规则提示          │
│              + [通过·入库] [驳回]            │
├────────────────────────────────────────┤
│ EvidencePanel（固定，折叠默认）            │
│   - input_snapshot / candidate_snapshot   │
│   - audit log / 决策历史                   │
└────────────────────────────────────────┘
```

## 实施步骤（按 task #17-21）

### Phase 1 (#17): 抽共享组件
- `components/manual-review/CaseHeader.vue`：从现 rw-head（L456-472）抽出
- `components/manual-review/EvidencePanel.vue`：从 rw-sec--evidence（L473-495）抽出，折叠默认
- `components/manual-review/DecisionActions.vue`：从 rw-foot 按钮区抽出，按 mode+template 配置按钮组
- ManualReviewWorkspaceView 引用这些组件，原 section 改成 `<CaseHeader />` 等占位
- 不改 template dispatch 逻辑，B 类/T_RUNTIME section 保留（双轨渲染）

### Phase 2 (#18): ModeIngestDecision 组件
- `components/manual-review/ModeIngestDecision.vue`：A 类决策区
- 三个子视图：
  - `T_DIRECTSubView.vue`：候选表单化（实体: nodeLabel + 属性表；关系: from→to + edgeType + 属性表）+ 理由 + 置信度 + 证据表 + accept/reject
  - `T_LINKSubView.vue`：候选 vs existingCandidates 并排对比表（属性差异高亮）+ merge/create/reject
  - `T_EVIDENCESubView.vue`：关系摘要 + 证据列表（每条标"独立来源"/"同源"，≥2 独立规则）+ pass/reject
- 调 directDecideProductionReview（T_DIRECT）/ submitProductionReview（T_LINK/T_EVIDENCE 走现有 4-eyes）

### Phase 3 (#19): 主框架重构
- ManualReviewWorkspaceView.vue 1629 行 → ~200 行主框架
- template dispatch 改成 mode dispatch：
  - isModeA（template in [T_DIRECT, T_LINK, T_EVIDENCE]）→ `<ModeIngestDecision>`
  - isModeB → 显示"数据修正任务待实现，B 类 case 暂不处理"提示（不进入主决策区）
  - T_RUNTIME → 不应出现在队列（Phase 4 过滤）
- 删除原 L508-700 的 per-template section（已迁入 ModeIngestDecision + 子视图）

### Phase 4 (#20): 后端过滤
- `production_service.create_review_required`：template=T_RUNTIME 短路，不入 ReviewCase 队列，写 outbox 触发自动重试/告警
- B 类 case 仍入队（等 B 类 TODO 实现），但前端 queue 端点支持 `category=A` 过滤参数
- 默认 `/manual-review` 列表只显示 A 类 case

### Phase 5 (#21): 测试 + 部署
- vue-tsc + ruff 通过
- review-full-integration.spec.ts 跑 T_DIRECT/T_LINK/T_EVIDENCE
- dev2 rebuild + restart 全部 3 容器
- 前端 /manual-review 默认显示 A 类 case；详情页只显示入库决策按钮

## 文件改动估计

新增：
- `frontend/src/components/manual-review/CaseHeader.vue` (~150 行)
- `frontend/src/components/manual-review/EvidencePanel.vue` (~200 行)
- `frontend/src/components/manual-review/DecisionActions.vue` (~100 行)
- `frontend/src/components/manual-review/ModeIngestDecision.vue` (~80 行 主框架)
- `frontend/src/components/manual-review/T_DIRECTSubView.vue` (~250 行)
- `frontend/src/components/manual-review/T_LINKSubView.vue` (~250 行)
- `frontend/src/components/manual-review/T_EVIDENCESubView.vue` (~250 行)

修改：
- `frontend/src/views/platform/ManualReviewWorkspaceView.vue` 1629 → ~200 行
- `backend/service/manual_review_production.py` 加 T_RUNTIME 短路 + queue category 过滤
- `backend/biz/handler/manual_review.py` queue 端点加 category query param

## 不在范围

- B 类数据修正页面/自动化（TODO #16，deferred）
- T_RUNTIME 自动重试/告警机制（另开任务，本期仅过滤不入队）
- HMAC 鉴权（dev 期 fallback 已配，生产鉴权设计后面再说）
