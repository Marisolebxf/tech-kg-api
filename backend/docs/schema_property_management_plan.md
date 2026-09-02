# Schema 属性管理方案：硬删除 / 脚本版本信号 / 历史回填

> 状态：方案已评审，待实施（2026-09-01）
> 涉及模块：schema-management、kg.schema.extract 工作流、任务中心、前端 Schema 页面

## 1. 背景与决策演进

自定义 Schema 平台需要支持属性（property）的增加与删除。此前实现为**目录级软删除**
（`kg_schema_property.is_deleted` 标记，不动图库），评审后放弃，改为**硬删除**，理由：

- 软删引入两处无法低成本闭环的复杂度：
  1. **复活路径 DDL 隐患**——软删后图库列还在，同名复活再发 `ALTER ADD` 行为不可控；
  2. **查询侧过滤**——所有图数据读取路径都要按目录过滤已删属性，`DESCRIBE TAG`
     与目录展示还要 merge 出"生效 schema"。
- 硬删除（目录删行 + 图库 `ALTER ... DROP`）让**目录与图库回到同一个事实源**，
  上述问题整体消失；`ALTER DROP` 物理删列连带全量数据，顺带满足数据擦除语义。

代价与接受方式：

- **不可逆** → 前端二次确认 + required 属性硬拦；
- **删除时可能有运行中抽取任务在写该列** → 删除前拦截 + 写图自愈双保险；
- **业务引用（identity/关系表达式）** → 不拦，只在响应里给 `warnings` 警告。

### 已拍板的三个决策点

| 问题 | 决策 |
|---|---|
| 删除属性时存在运行中抽取任务 | **拦截**：409 提示任务名，引导用户先去任务中心停止、任务结束后重试 |
| 历史数据回填触发方式 | **独立"回填历史数据"按钮**（可反复重跑、失败可重试），不在 add_property 里自动触发 |
| 脚本与属性变更的关联检测 | **版本号机制**（属性修订号 vs 脚本上传时记录的修订号），不做脚本文本扫描 |

## 2. 总体设计

三件事互相咬合：

```
新增属性 ──→ property_revision+1 ──→ 脚本"落后于 Schema"角标 ──→ 用户更新脚本
   │                                                                  │
   └── ALTER ADD（现状） ──→ 老数据新列为 NULL ──→ 「回填历史数据」按钮 ←─┘
                                                   （清水位 + 全量重跑）

删除属性 ──→ 拦运行任务 → 警告依赖引用 → 图库 DROP + 目录删行 → revision+1
```

核心约束：**抽取按 `time_column` 水位增量**，老行不动就永远不会带新属性值，
所以新属性要"长"出来必须重置水位全量重跑；而产出属性靠的是 S3 用户脚本，
**新增目录属性 ≠ 抽取能产出它**——脚本不更新，回填跑完新列还是 NULL。
这就是"版本号提示"存在的理由。

## 3. 表结构变更（workflow 库）

| 表 | 新列 | 说明 |
|---|---|---|
| `kg_schema_definition` | `property_revision INT NOT NULL DEFAULT 1` | 属性修订号；**不复用**现有 `version`（那是 `v1.0` 式展示口径） |
| `kg_schema_script` | `captured_revision INT NOT NULL DEFAULT 1` | 脚本上传时的修订号，重传自动刷新（警告即消） |
| `kg_schema_script` | `last_run_status VARCHAR(16) NOT NULL DEFAULT 'none'` | none / ok / failed，抽取工作流收尾回写 |
| `kg_schema_script` | `last_run_error VARCHAR(1024) NULL` | 脚本阶段失败的错误信息 |

- ORM：`backend/db_model/schema_management.py`（`GraphSchemaDefinition` :29、
  `GraphSchemaScript` :154）。
- 迁移：仿 `workflow_repository._migrate_job_columns()`
  （`backend/service/workflow_repository.py:77`）的幂等 `ADD COLUMN` 模式——
  `create_all` 只建缺表不加列，已有库需要启动时补列。
- 旧软删列 `kg_schema_property.is_deleted/deleted_at`：代码不再读写；
  模型列与库列保留不删（避免给存量库写删列迁移），相关过滤逻辑退役。

## 4. 属性硬删除

重写 `delete_property`（`backend/service/schema_management.py:694`），
endpoint `DELETE /schemas/{schema_id}/properties/{property_name}`
（`backend/biz/handler/schema_management.py:193`）。

### 4.1 Guard 顺序（前两条拦，最后一条警告）

1. `category == "required"` → 409「必选属性不可删除」。
   `id/name/create_time/update_time/source_table` 是平台管道无条件写的标准列
   （注入逻辑 `service/schema_management.py:119-130`），删了下次抽取必 400，
   属于硬约束，不在"警告"范畴。
2. 运行中任务 → 409。查 `workflow_type = kg.schema.extract` 且 payload
   `schemaId` 匹配、状态 running 的执行记录，报
   「任务「{name}」正在抽取该 Schema，请先到任务中心停止，任务结束后重试」。
3. 依赖引用 → 收集进 `warnings` 返回（不拦）：
   - 本 definition 的 `identity_key` / `attribute_identity_key`（merge 去重语义）；
   - 引用该实体的关系的 `source_expression` / `target_expression`；
   - 匹配方式为 substring。脚本内引用不扫（版本号机制替代，见 §6）。

### 4.2 执行顺序与失败语义

```
收集 warnings
  → DESCRIBE TAG/EDGE 列存在性检查（graph client execute_query）
  → 列存在：执行 ALTER TAG/EDGE <name> DROP (prop)
       失败 → 抛 SchemaDdlError，目录不动（索引依赖等错误如实透出）
  → 删目录行（flush）
  → DDL 已成功 → commit；property_revision += 1
  → 列不存在（system schema DDL 未跑过 / 已删过）→ 跳过 DDL 只删目录行
```

- 与 `add_property` 的"目录先行 + DDL 失败回滚"对称，保证目录与图库一致
  （目录列在图里不存在会导致 merge_node 400，这是必须维持的不变量）。
- 极小概率的「DROP 成功但 commit 失败」留下目录有/图库无的坏状态：记日志告警，
  不做自动补偿（re-ADD 复杂度不值）。
- DDL 构建执行：`service/schema_ddl.py` 新增 `build_alter_drop_ddl` /
  `run_alter_drop_ddl`，镜像现有 `build_alter_add_ddl`（:86）/ `run_alter_add_ddl`（:96），
  复用 `execute_schema_ddl` 的重试（应对 DDL 传播延迟）。
- 响应：`{deleted, propertyName, warnings[], ddlStatement, ddlStatus, ddlError}`。

### 4.3 add_property 收尾（`service/schema_management.py:622`）

- 删除"同名软删属性复活"分支：同名一律 409「属性名已存在」；
- 成功后 `property_revision += 1`。

## 5. 写图自愈

`write_records`（`backend/service/temporal_workflows.py:765`）：
`merge_node` / `merge_edge` 遇 `GraphRequestError` 且报错为 unknown column 类 →
从该条 props 中剔除对应列**重试一次**，仍失败才抛。

用途：兜住「运行任务检查通过 → 任务恰好启动 → 属性被删」的时序窗口，
以及一切计划快照与图库 schema 的错位。

保留现有 `activeProps` 过滤（temporal_workflows.py:613/:788）：软删退役后它仍有独立价值——
**用户脚本输出未声明属性时先剔除再写图**，避免 400。

## 6. 脚本双信号："旧了"与"坏了"是两个维度

| | 旧了（stale） | 坏了（broken） |
|---|---|---|
| 信号来源 | 版本号比较，**事前**可知 | 只有跑起来才知道，**事后**反馈 |
| 可能的组合 | 旧但能跑 | 新但报错 |
| 用户动作 | 更新脚本以产出/停产出变更属性 | 修 bug 重新上传 |

两路信号并存，**不合并成一个状态字段**。

1. **staleness**：`replace_script`（`PUT /schemas/{id}/script`，
   `service/schema_management.py` replace_script）上传成功时
   `captured_revision = 当前 property_revision`。
2. **health**：kg.schema.extract 工作流收尾回写
   `last_run_status` / `last_run_error`（脚本阶段=normalize/extract 的成败；
   挂点在 `service/temporal_workflows.py` 抽取工作流的成败处理）。
3. **下发检查**：`trigger_extraction`（`service/schema_extraction.py:54`）启动前比较
   `captured_revision < property_revision` → 响应带 `staleScript: true`，
   **提示但放行**——旧脚本永远跑不挂：删掉的属性被 activeProps 过滤、
   新属性只是没人产出留 NULL。
4. **序列化**：schema detail 的 script 段输出
   `capturedRevision` / `lastRunStatus` / `lastRunError` / `stale`。

## 7. 历史回填（独立按钮）

### 7.1 端点

`POST /schemas/{schema_id}/backfill`，body `{ force?: bool }`：

- 前置校验同 `trigger_extraction`：已上传脚本、≥1 来源表绑定，否则 409；
- `stale` 且未带 `force` → 409
  「当前脚本未覆盖最新属性（落后 N 版），回填可能无效，请先更新脚本」；
  前端强确认后带 `force=true` 重发（脚本可能通配透传所有字段，不硬拦）。

### 7.2 后端动作

1. `service/script_watermark.py` 新增 `clear_watermarks(definition_id)`：
   删除该 definition 全部 `source:{id}` 水位（现只有 read :46 / write :57）；
2. 复用 `trigger_extraction` 启动 kg.schema.extract（`persist_task=True`），
   任务中心照常可见/可停。

### 7.3 语义要点

- merge_node 是 UPSERT：回填会用源表当前值覆盖既有属性（正是想要的），
  `update_time` 会刷新，可接受；
- 回填失败可直接重跑（清水位幂等）；
- 属性新增本身不因回填失败回滚（DDL 已成功，两者解耦）。

## 8. 前端

页面：`frontend/src/views/platform/SchemaBrowserView.vue`（及属性编辑所在的
`GraphBuildView.vue`），API：`frontend/src/api/schemaManagement.ts`
（addProperty :300 / deleteProperty :314）。

- 删除属性：**不可逆二次确认**（写明"将删除图库中该属性列及其全部数据"）+
  展示返回 `warnings` + 运行中任务 409 文案透出；
- 脚本卡片两个角标：「落后于 Schema（N 版）」 / 「上次运行失败：{err}」；
- 「回填历史数据」按钮：stale 时弹强确认（说明可能无效）后带 force 调用；
- 触发抽取遇 `staleScript` → 可继续的警告 toast。

## 9. 测试

- 单测：`build_alter_drop_ddl` 构建；`delete_property` 各 guard（required 拦 /
  运行任务拦 / warnings 收集 / 列不存在跳 DDL / DDL 失败目录回滚）；
  `clear_watermarks`；自愈剔除重试。
- 集成：沿用 `backend/tests/integration/test_schema_property_management.py` 模式补：
  增/删属性 revision 自增、脚本 `captured_revision` 刷新、`stale` 判定、
  回填清水位、`last_run_status` 回写。
- 全部在 dev2 容器内执行：rebuild api-dev2 镜像后再 pytest
  （`docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m pytest tests -m "not external" -q`）。

## 10. 实施顺序

B 属性硬删除 + C 写图自愈（核心）→ A 表结构 + D 脚本双信号 → E 回填 → F 前端；
测试随每步走，最后容器内全量回归。
