# 任务：kg.schema.extract 支持用户脚本内声明多 step

## 背景与目标

本仓库的 schema 抽取主通道是 Temporal workflow `kg.schema.extract`（`backend/service/temporal_workflows.py:1252` `SchemaExtractWorkflow`）：平台按来源绑定分批读源 → 调用户上传脚本的**单个** `transform(payload)` → 平台写图/消歧/索引/推水位。

历史上曾有一条平行的多步流水线通道 `kg.custom.steps`（`StepPipelineWorkflow` + `POST /definitions/steps` + `execute_pipeline_step` activity），已于 2026-09-14 批次4-D2 下线（见 `docs/无用代码清理与合并清单.md` 第五节、commit `bf28410`）。

**本次目标**：把多步能力并入 `kg.schema.extract`——保持单一上传入口不变（Schema 管理页上传 .py → S3），但允许用户在脚本里**声明多个 step**，平台按序执行、逐步 Temporal 重试、任意步可产出实体/边。**不恢复**独立上传通道、不恢复双参 runner。

## 已拍板的设计决策（不要重新讨论，照此执行）

1. **声明方式**：脚本顶层 `STEPS` 清单（list literal），每项 `{"id": ..., "fn": ...}`：
   ```python
   STEPS = [
       {"id": "normalize", "fn": "step_normalize"},   # 第一步消费平台读的源表行
       {"id": "resolve",   "fn": "step_resolve"},     # 后续步消费上一步输出
       {"id": "emit",      "fn": "step_emit"},
   ]
   ```
2. **向后兼容**：只有顶层 `transform` 的脚本 = 单步流水线（现有九域注册脚本零改动）。`transform` 与 `STEPS` 同时存在 → 上传时拒绝（歧义）。
3. **步函数签名**：单参 `def step_x(payload)`，与今天的 `transform` 完全同构；上下文一律 `from kg_sdk import current_context`（`backend/sdk/kg_sdk.py` 的 `Context` 已有 `step_id`/`attempt`/`prev_outputs` 字段，本次把它们真正用起来）。**不复活** `_DUAL_ARG_RUNNER`。
4. **数据流**：
   - 第 1 步的 payload 与今天的 transform payload 逐字段相同（`rows`/`source`/`source_table`/`kind`）。
   - 第 N>1 步的 payload = `{"input": <上一步返回的完整 dict>, "source": ..., "source_table": ..., "kind": ...}`，且 `ctx.prev_outputs` = 本批次已完成各步的 `{stepId: 输出 dict}`。
   - 每一步的返回值都用现有契约：`{"entities"|"edges", "failures", "pendingReview"?, "stats"?}`；**任意一步**返回了 `entities`/`edges`，平台就在该步之后调 `write_records`（实体再接 `detect_extract_collisions`）；步返回值里的额外键原样流向下一步的 `input`（允许「清洗步只出中间数据、末步才出实体」和「多步都出记录」两种写法）。
5. **失败/重试/水位语义（维持现状，不做 per-step 水位）**：
   - 每个 step 是一次独立的 `execute_transform` activity 调用（带各自的 functionName/payload），沿用现有 `ACTIVITY_RETRY_POLICY`——第 k 步失败由 Temporal 只重试第 k 步，第 k-1 步的输出作为 activity 输入经事件历史重放。
   - 来源游标/水位仍只在**该来源全部批次整链成功后**推进（当前语义）；step 函数是纯转换、写图是 upsert，整链重跑幂等。`kg_script_watermark` 的 step_id 语义不动。
   - 任意步的逐行 `failures` 聚合进现有 T_EXTRACT_FAIL 链路；任意步的 `pendingReview` 进现有审核队列。重跑模式（`recordIdsBySource`）语义不变：整批失败记失败记录，`resolve_failure_cases` 必调。
6. **不新增 API 端点、不新增 DB 表/列**：`load_schema_extract_plan` 在下载脚本临时文件后用 `ast` 解析出 STEPS（上传时 `_validate_script` 提前校验清单形状、尽早报错）。

## 现状锚点（先读这些再动手）

| 位置 | 内容 |
|---|---|
| `backend/service/temporal_workflows.py:1252` | `SchemaExtractWorkflow`：来源间 gather 并行；来源内 1 reader + N worker 经 `asyncio.Queue` 背压；worker 里单次 `execute_transform` → `write_records` → `detect_extract_collisions`（约 :1475 起） |
| `backend/service/temporal_workflows.py:441` | `load_schema_extract_plan`：读控制库 + S3 下载脚本到临时文件，产出 scriptPath/functionName/kind/activeProps/sources |
| `backend/service/temporal_workflows.py:753` | `execute_transform` activity：组装 payload、`_resolve_resources` 选资源、`_spawn_script` 子进程调脚本、消化 `pendingReview`/`_strip_watermark_meta` |
| `backend/service/temporal_workflows.py:207` | `_spawn_script` + `_SINGLE_ARG_RUNNER`：唯一 runner，ctx 经 `KG_SCRIPT_CTX` env 注入 |
| `backend/service/schema_management.py:1020-1046` | `_validate_script`：ast.parse + 入口检查（有 `transform` 用 transform，否则兼容旧 `workflow`） |
| `backend/sdk/kg_sdk.py` | `Context`：`step_id`/`attempt`/`prev_outputs`/`execution_id` 等字段已定义 |
| `backend/service/temporal_workflows.py:240 附近` | `_sync_task_from_execution`：`real_steps`/`normalize_stages` 回写任务 steps，任务详情页由此渲染 |
| `backend/script/workflows/sample_step_pipeline.py` | 旧 kg.custom.steps 的 manifest 形状参考（标注 D5 处置，勿删） |
| `git show bf28410^:backend/service/temporal_workflows.py` | 被删的 `StepPipelineWorkflow`/`execute_pipeline_step` 语义参考——参考其 prev_outputs 传递思想，不照搬双参 runner |
| `docs/Schema管理模块.md`、`docs/工作流系统模块.md`、`CLAUDE.md` | 需同步的文档 |
| `dev2_extract_e2e.py`（仓库根） | e2e 驱动脚本 |

## 实施要求

### 1. 上传校验（`_validate_script`）
- 有顶层 `transform` → 现状不变（entry="transform"）。
- 无 `transform` 但有顶层 `STEPS`（赋值为 list literal）→ 校验：每项是 dict、含非空 `id`（匹配 `[A-Za-z0-9_-]{1,64}`）与 `fn`；id 唯一；每个 `fn` 都能在顶层 `FunctionDef` 里找到；清单非空。校验失败用中文报具体原因（沿用 `SchemaScriptError` 文案风格）。
- 两者都有 → 报错「transform 与 STEPS 不能同时声明」。
- `workflow_function_name` 列对 STEPS 脚本存什么由你定（建议存第一步 fn 或保留 "transform" 占位，plan 反正重新 ast 解析），但要写注释说明。

### 2. 计划组装（`load_schema_extract_plan`）
- 在现有脚本下载之后 `ast.parse` 临时文件：无 STEPS → `steps = [{"id": "_default", "fn": function_name}]`；有 STEPS → 解析出的清单。
- plan 增加 `steps` 字段；其余字段不动。注意 plan 会被 Temporal 序列化，steps 只放 id/fn 两个 str 键。

### 3. 执行（`SchemaExtractWorkflow` worker + `execute_transform`）
- worker 内把单次 `execute_transform` 改为按 `plan["steps"]` 顺序循环：
  - 第 1 步 request 同现状；第 N>1 步 request 增加 `input`（上一步完整输出）与 `prevOutputs`（{stepId: 输出}）。
  - 每步返回后：有 `entities`/`edges` → `write_records`（kind/name/activeProps/graph/sourceTable 同现状），实体再接 `detect_extract_collisions`；`failures` 从所有步聚合。
  - 步与步之间不引入新并发：来源内 worker 并发度 `max_inflight` 管批间并行，批内 step 链串行（保持现状的背压结构，不重写调度）。
- `execute_transform` activity：request 增加可选 `input`/`prevOutputs`；payload 组装为第 N>1 步的形状（见设计决策 4）；`resolved` ctx 合并 `stepId`（改为该 step 的 id，保留来源标识便于排查，如 `source:{sid}#{stepId}`——注意 `kg_script_watermark` 若以 stepId 参与键则维持现状不变，此处只影响观测）与 `prevOutputs`。
- `output` 大小防护：步输出经 activity 返回值传递（与现状 records 相同量级），`stats`/额外键合计建议上限（如单步输出 JSON > 4MB 时截断 `input` 透传并记 warning，防 gRPC 上限炸批次）——具体阈值与策略你定，写清注释。

### 4. 执行结果可见性
- workflow 结果与 `self._sources` 摘要增加分步计数：`"steps": {stepId: {"records": n, "written": n, "failed": n}}`（聚合计数，不放完整输出）。
- `_sync_task_from_execution` / 任务详情页能展示分步统计（`real_steps`/`pipeline_steps` 现有机制优先复用；不够再最小扩展）。

### 5. 前端（最小改动）
- `SchemaBrowserView.vue` 上传脚本弹窗的提示文案补一句「支持在脚本内声明 STEPS 多步清单」；查看脚本/落后版本/失败徽标逻辑不动。
- `ProcessInstanceDetailView` 若现有 steps 渲染已能展示新分步统计则零改动；标签不合适就微调。
- `JobLaunchDialog` 零改动（任务类型仍是 extract）。

### 6. 文档与示例
- `docs/Schema管理模块.md`：脚本契约章节补 STEPS 声明、payload 链、逐步重试语义；`kg_script_watermark` 说明不变。
- `docs/工作流系统模块.md`：kg.schema.extract 段落同步。
- `CLAUDE.md`「平台喂数批次抽取」段补一句多步能力描述。
- `docs/抽取脚本示例/`：新增一个多步示例脚本（三步：行清洗 → 机构名解析（未命中进 pendingReview）→ 出边），风格对齐现有两个示例。
- `script/register_platform_extraction.py` 与九域注册脚本零改动（单 transform 继续合法）。

### 7. 测试（全部容器内跑，见 CLAUDE.md）
- 单元：`_validate_script` 的 STEPS 接受/拒绝矩阵（缺 id/fn、id 重复、fn 不存在、与 transform 共存、空清单）；plan 解析；workflow 循环（沿用现有测试对 SchemaExtractWorkflow 的做法）断言：步序执行、input/prevOutputs 链、任意步 records 触发 write_records、failures 跨步聚合、水位仍整链推进。
- 集成：走 API 上传 STEPS 脚本 → 绑来源 → 触发 → execution 结果含分步统计（模式对齐 `tests/integration/test_schema_extract_api.py`）。
- 回归：现有 `test_schema_extract_*`、`test_extract_rerun_and_jobs` 全绿（单 transform 行为不变）。
- 完成标准：容器内 `pytest -m "not external"` 全过 + `ruff format --check .` + `ruff check .` 通过。

## 硬性约束

- 不新增上传通道/端点/表；脚本安全审计（LLM review 整文件）链路不动。
- 注释、用户可见文案、模块描述一律中文；代码风格对齐周边。
- 提交信息中文、**绝不带 Co-Authored-By 等 co-author trailer**（CLAUDE.md 约定）。
- 主机不跑后端测试（无 MySQL/Redis/TRSGraph），一律 `docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m pytest ...`。
