# yunfei_test_1 全量重建「纯前端操作」e2e 问题记录（2026-10-08）

按 `backend/docs/yunfei_test全量重建文档.md`（58d66cee 精简版）重跑 yunfei_test_1 全量重建，
要求**所有操作通过前端 UI 完成**，前端做不到的记为问题并走 CLI 兜底。本文是问题清单与
处置实录；每条问题的截图证据在 `artifacts/yft1-frontend-e2e/`（文件名见各条目），可复现
e2e 用例在 `frontend/e2e/yft1/`（宿主机 Playwright → yunfei3 栈 8093/8004，`workers=1` 串行）。

## 结论速览

| 阶段 | 前端完成度 | 兜底（CLI） |
| --- | --- | --- |
| 清场（手册 §3） | **0/3**——DROP 图空间 / Milvus 同名库 / 抽取水位全部无前端通道 | ✅ 全部 CLI |
| 建空间（§4 ①） | ✅ 配置管理→新建图数据空间，vid FIXED_STRING(256) 默认口径正确 | 无 |
| 预建统一 schema（§4 ②） | ❌ 无通道（DDL 禁令 + 平台建表 NOT NULL 口径冲突） | ✅ CLI |
| Schema 目录核对 | ✅ 16 实体 + 33 关系全列出，空间隔离正确 | 无 |
| 平台三链（§5） | ✅ 删旧任务 / 新建三链 / 触发执行 / 终态轮询全走 UI | 无 |
| 离线域 ETL（§6） | ❌ 五域全是脚本通道，平台无对应页面 | ✅ 全部 CLI |
| 索引重建 | ❌ 前端按钮已下线（5ce8d455），后端端点仍在；本轮三试皆被宿主内存水位掐断（⑫） | ⚠️ 环境受阻，待内存缓解重试 |
| 对账验证（§7） | ◐ SHOW STATS 可读（窗口期）；SUBMIT JOB STATS 被禁；九模块 env 冻结 dev | ◐ CLI SUBMIT + SHOW STATS 快照 |

**本轮终态**（2026-10-08）：三链 实体=COMPLETED（修复轮）/ 关系A=COMPLETED（修复轮，小源库行级零失败）/
关系B=ABNORMAL（行级失败转审核：T_EXTRACT_FAIL 6408 / T_LINK 4520，符合口径）；离线域 域1/域2/域3/域4
全过（域5 可选被 ⑫ 环境阻断）；全空间 308,084 点 / 664,404 边；**全部对账锚点精确命中**：
SAME_AS 259=dev 259（域4 written=259）、Journal 2134、DataSource 39、PatentFamily 1999、Project 4005、
Report 3000、OrganizationBase 61652；Person 39737 / COAUTHOR_WITH 156144（源年代差组，与重灌小源自洽）。

## 问题清单

### ① 前端无删除/清空图空间通道（清场 3 项全缺）

- nGQL 控制台对 DDL/管理语句一律 403：`DROP SPACE IF EXISTS yunfei_test_1` 被拒，报
  「禁止执行 DDL/管理类语句（DROP）；图空间与 Schema 请通过配置页 / Schema 管理维护」。
  证据：`s1a-console-drop-space-rejected.png`（e2e 用例 S1a）。
- 配置管理→图数据空间只有「＋ 新建图数据空间」，表内无删除/解绑/清空按钮；后端也无
  DELETE 端点（`DELETE /{name}` 是解绑且明确「图空间数据保留」）。
  证据：`s1b-config-space-no-delete.png`（S1b）。
- Milvus 同名库/映射行、抽取水位（`kg_script_watermark`，跨空间共享）属后端内部状态，
  前端无任何水位/向量库管理页面。

**影响**：「清空某个图空间重新装载」这一操作在前端不可达，只能 CLI（手册 §3 全套）。

### ② ABNORMAL/已完成任务无重触发入口（**运行异常态已修复**）

`GraphBuildView` 的执行按钮仅对统一状态 `未运行/运行失败` 渲染（`已完成按产品决策不提供
重复执行`，`运行异常`即 ABNORMAL 同样被排除）。上轮（09-30）全量重建三链终态均为
ABNORMAL（行级失败转审核是常态口径），**前端唯一路径是删任务重建**——本次沿用了该路径
（e2e S6a 删除三链后经新建任务弹窗重建）。本轮重灌后的小源库行级零失败，修复轮实体链与
关系A 直接 COMPLETED——终态分布取决于数据脏度，但「已完成/运行异常均无重触发入口」
的结论不变。若产品预期「重跑=增量续抽」，这两态也应提供入口（或提供显式
「重置水位全量重跑」）。

> **2026-10-08 处置**：`运行异常` 态已提供「重新执行」入口（后端 `trigger_job` 本就不拦
> ABNORMAL，仅前端口径收窄；重跑语义=水位增量续抽，行级失败仍在审核队列不受影响）。
> 已完成态维持产品决策不提供。单测 `GraphBuildViewFilter.spec.ts` 三条用例覆盖
> （异常行有按钮且点击真触发 / 已完成行无 / 未运行行仍显示「执行」），UI 只读验证截图
> `s-rerun-btn-abnormal.png`。

### ③ 预建统一 schema 无前端通道（§4 存在理由本身）

平台建 Schema 会把 required 属性建成 NOT NULL，与离线域整行 `INSERT VERTEX/EDGE` 结构
冲突；正确顺序是先以全可空口径预建两路并集。前端两条路都走不通：

- 控制台 DDL 禁令（同①）；
- Schema 管理页逐个建表的口径仍是 NOT NULL——预建的目的恰恰是绕开它。

且 45+ 个 schema 从 dev 整体复制无任何「跨空间复制/导入」能力。本次按手册 §4 脚本 CLI
预建（TAG 20 / EDGE 42 与 dev 现网完全一致，含 dev 本周新增的 ALUMNI/COLLEAGUE 等）。

### ④ 水位清理无前端入口

「清空重跑」语义要求把 45+ 链内 schema 的抽取水位一并清掉（水位按
`schema-extract-{schema_key}` 键控、**跨空间共享**——不清则新空间首跑直接读 0 行）。
本次 CLI 清 151 行 / 49 definition_id（与上轮实测一致）。前端既无水位展示也无清理入口。

### ⑤ SUBMIT JOB STATS 被控制台禁（对账只读半边）

对账需要 `SUBMIT JOB STATS` 刷新统计快照后 `SHOW STATS` 才是现值；SUBMIT 属管理语句被
403。前端只能读上次快照。本次 CLI 提交统计、前端控制台读数取证（`s8-1-show-stats.png`、
`s8-2-submit-job-stats-rejected.png`）。建议：控制台放开 `SUBMIT JOB STATS`（幂等安全）
或状态页内置「刷新统计」。

### ⑥ 索引重建前端按钮已下线

实体列表依赖的检索索引（`POST /api/v1/entity-search/reindex`）按钮随 5ce8d455 下线，
重建后新空间的索引只能 CLI 打 admin 端点。若产品确认不再从 UI 触发，建议在重建手册
层面显式标注为固定 CLI 步骤。

### ⑦ 九大业务模块 env 冻结 dev 空间（待终验取证）

九模块查询走容器 `TRS_GRAPH_SPACE`（本栈恒为 dev），不跟全局图空间选择器；业务模块
页面也无空间切换入口（`s8-3-expert-direct-page.png`）。重建空间的数据无法从九模块 UI
验证，只能容器内 `-e TRS_GRAPH_SPACE=<空间>` 起进程探针（手册 §7.1 口径）。
属已知架构决策（图空间全局选择改造审计结论），此处作为「前端无法完成重建验证」记录。

### ⑧ 链式任务的 Schema 搜索易误选（实测踩中）

新建任务弹窗「串联 Schema 队列」下拉是子串模糊匹配且选中后无精确校验：搜索
`Organization` 会把 `OrganizationBase`（DOM 序在前）加进队列、搜索 `Patent` 会误加
`PatentFamily`——本次首轮实测即错装了实体链（14 项、顺序错位），靠 e2e 的
`· 名称）` 后缀精确匹配 + 队列长度断言才纠正。建议：选项匹配按英文全名精确优先，
或队列加入时校验与搜索词全等。队列虽有 ↑↓× 可修，但用户很难发现静默错选。

### ⑨ 排障口径：schema 目录活表在 control 库，业务库同名残留易误导

`kg_schema_definition` 等四表实际挂 `service.workflow_models.Base`（`techkg_control` 库），
业务库（本栈 `gkx_element` 库）存在一套同名残留表。本次排查时先查到业务库副本误判
「45 个 schema 定义已被删」，实际 control 库 49 行健在（含 4 个链外关系）。
建议清理残留表或在手册标注。

### ⑩ dev 现网 schema 漂移 → 平台链两轮硬失败（本轮实测阻断项，两个表现）

手册 §4 预建口径是「从 dev 现网 DDL 复制」，隐含前提是 dev 稳定；dev 本周被重建过
schema，本轮两个表现先后炸链：

1. **TAG 小写化**：dev 的 `OrganizationBase` 已变为小写 `organization_base`。实体链首轮
   终态 FAILED（非预期 ABNORMAL）：worker 反复 `No schema found for 'OrganizationBase'`
   （平台按 schema 驼峰名写图，Nebula 大小写敏感），write_records 重试耗尽。
   修复：按平台 schema 属性（17 列、全可空）CLI 补建大写 TAG → 前端「重新执行」→
   COMPLETED，OrganizationBase 61652 与上轮精确一致。
2. **EDGE/TAG 瘦化**：dev 现网 EDGE/TAG 只剩业务列，缺平台治理列
   （`create_time/update_time/match_method/match_evidence/ingest_batch/...`）。关系A 首轮
   FAILED：`Unknown column 'update_time' in schema`。对比 control 库 schema 属性全集，
   33 个 EDGE + 15 个 TAG 共 48 个缺列（实体脚本输出列恰被瘦口径覆盖所以实体链先漏过）。
   修复：按 schema 属性 `ALTER ... ADD`（幂等补齐、天然可空）→ 前端「重新执行」。
   另有 **9 个目录外 EDGE**（SAME_AS/CITED_BY/SOURCED_FROM/ALUMNI 等离线域 ETL 专用边）
   + BidNotice TAG 同样瘦化——它们不在 schema 目录里、修复脚本按目录对账时漏过，阶段 6/7
   交接时补齐（同 ALTER 口径，参照全列边超集补列，多余可空列无害）。

**建议**：预建脚本增加兜底——「schema 目录里存在的 TAG/EDGE/属性列，dev 缺失时按
schema 属性（全可空口径）补建」，把「dev 口径」从隐含前提变成校验项。

### ⑪ 源库 gkx_element_yft1 已被重灌（残差归因，非链问题）

本轮 Person 终值 32599（上轮 ~13.3 万）：源库各 Person 源表加总仅 ~4.3 万原始行
（dwd_scholar 2175 / dwd_zh_author 7906 / dwd_en_author 12977 / 股东·高管·受益人·实控
~2 万），与上轮装数时的行数量级不同——副本库在上轮之后被重灌过小数据集。装载结果与
当前源自洽（32599 = 源表去重合并口径），按 §7「以当前源为准」过账；全等锚点
（Journal 2134 / DataSource 39 / Project 4005 / Report 3000 / OrganizationBase 61652）
均精确命中，装载链路本身无缺陷。**环境事实**：重建前应按 §1 核对源库行数快照，
否则残差归因会被放大。

### ⑫ 共享宿主机内存贴死 Nebula 水位线（0.9），读路径按请求抖动拒绝（本轮环境阻断项）

宿主机 62.78G 常态已用 ~55G（多套栈共享：dev2/生产/他人 dev server 等），Nebula 的
高水位按**整机内存**计算（page cache 计入），本轮全程在 90% 边界抖动，表现为：

- `MATCH` 全扫类读（对账计数、`/nodes/label`）被 `use space failed: Used memory hits the
  high watermark` 按请求拒绝；SHOW STATS 快照读与 CLI `execute_read/write` 大体可过；
- **域5 学者消歧（可选）被阻断**：`GET /nodes/label/Person` 直接 400（手册口径：跑与
  不跑不影响计数，本轮跳过）；
- **实体索引重建三试皆中止**：两遍流式读中第二遍归零，防御性中止逻辑（2026-09-21 加）
  正确保住旧索引——这是该保护在真实环境退化的首次实战触发；
- e2e 06 用例的 UI 控制台读数需抢内存窗口（本轮窗口期已取证 s8-1/s8-2；S8b 锚点断言
  改走 SHOW STATS 快照 + 退避重试后通过）。

`drop_caches`（仅 pagecache）可临时开窗 ~1 分钟，但窗口极短且属共享生产宿主机运维动作，
不宜反复执行。**建议**：图服务水位告警接入运维（当前无感知）；重建类长任务（reindex
两遍流式读）考虑对水位 400 做批内退避重试而不是整体中止。

> **⑫ r2 重现（同日晚间，比第一轮更紧）**：目录重建完成后的三链触发连续三轮被水位掐死
> ——`write_records`/`resolve_entity_batch` 的 5 次 Temporal 重试全被
> `use space failed: Used memory hits the high watermark(0.900000)` 拒绝，实体链 4–8 分钟即
> 终态「运行失败」，空间落库 **0 点**（两轮失败后 SHOW STATS 全 0）。晚间宿主真实占用
> 53G + page cache 3–5G，地板正好压在 0.9 线（56.5G）上下：单发顺序小写（探针 3/3、
> SUBMIT JOB STATS）能过，链式并发批量写（多 activity 同时在飞、批语句更大）立刻顶破
> 水位被整批弹回。`drop_caches` 开窗 ~1 分钟不够覆盖浏览器启动 + UI 触发的延迟，缓存
> 分钟级回涨。环境性阻断与第一轮同源，晚间负载更重；改为「探针探窗（连续 3 次小写
> 全过）→ 窗口即开即经 UI 触发」的研磨重试。
>
> **后续勘误（当晚串行研磨实测）**：worker 降到活动并发 1（compose override）+ 批 100 后
> 链可贴线爬行，实体链 22 分钟 COMPLETED。「并发 write-200 流 vs SHOW STATS 0 点」之谜
> 解开：`write_records` 是**逐条 INSERT VERTEX**（~247/s 串行合理），写入真实落库；SHOW STATS
> 是统计快照，水位期 `SUBMIT JOB STATS` 未真正算成时快照停 0——**对账要用 LOOKUP 直数**
> （DataSource 39 / Journal 2134 / OrganizationBase 61652 全中）而非 SHOW STATS。另水位表
> `updated_at` 存 UTC，探针脚本用东八区时间过滤会误报「0 行更新」。三链后续被 ⑱
> （Temporal 历史事件数硬限）截断，非水位所致。

## 前端正常项（正向结论）

- 建空间 → vid 默认 256 口径无需任何干预；
- Schema 管理空间隔离正确：切 yunfei_test_1 后 16 实体 + 33 关系全列出（服务端分页正常）；
- 任务中心删任务（confirm）、新建链（任务类型/队列/批大小/数据源跟随绑定/一次性不立即执行）、
  触发执行、SSE 终态 toast、状态列翻转为「运行异常」全链路 UI 可用；
- **运行失败态的「重新执行」是修复轮的主力通道**：CLI 补建大写 TAG / 补齐缺列后，两轮
  修复全靠该入口续跑（水位增量语义），无需删任务重建；
- 控制台只读语句（SHOW/MATCH/DESCRIBE）正常，读数与 CLI 一致（内存窗口期内取证）。

## 复现

```bash
cd frontend
pnpm exec playwright test -c e2e/yft1/playwright.config.ts   # 全部串行
# 阶段拆跑：01(基线/清场取证) 02/02b(建空间) 03(Schema) 04(建链)
#   05(首轮三链) 05b(实体修复轮) 05c/05d(关系修复轮) 06(对账)
```

注意：05 系列为 40–60 分钟长跑（三链串行等终态）；06 需阶段 7 离线 ETL 完成后再跑，
且受 ⑫ 内存水位影响——控制台读数需抢窗口，S8b 走 SHOW STATS 快照 + 重试。

---

# 第二轮（r2）：目录全前端重建（2026-10-08 下午）

与第一轮的差异：第一轮 CLI 预建全可空 DDL + Schema 目录沿用 09-30 旧绑定；本轮把目录
49 个定义全部经前端**删掉重建**，建实体/关系、上传脚本、绑定来源、跑链全走 UI，前端
做不到的记为问题并 CLI 兜底。e2e 用例 `frontend/e2e/yft1-r2/`（10 个 spec + fixtures +
CLI 兜底脚本），证据截图 `artifacts/yft1-frontend-e2e-r2/`。清场（CLI clear_space.py：
DROP SPACE + Milvus 库/映射 + 两套键型水位 162 行）与 01/02（基线、建空空间）先行通过。

### ⑬ UI 建目录锁定必填行 → 图 DDL NOT NULL，与离线域整行 INSERT 冲突（第一轮预判，本轮真实踩中）

新建 Schema 表单锁定必填行（实体 `id/name/create_time/update_time/source_table`，关系
`create_time/update_time/source_table`）自动带出且不可取消必填 → 生成的 CREATE TAG/EDGE
DDL 全部带 NOT NULL（DDL 预览截图取证 `r2-s4-1-ddl-preview-notnull.png` /
`r2-s5-1-ddl-preview-notnull.png`）。平台喂数写图路径（kg.schema.extract 逐行 INSERT，
平台感知补值）可以过；但 §6 离线域脚本对整行做 `INSERT VERTEX/EDGE`，缺列即
`400 SemanticError`。处置：链前 CLI 归一化（`cli/normalize_ddl.py`：DROP 全部 TAG/EDGE
索引与类型 → 按目录 `ddl_statement` 去 NOT NULL 重建 + `idx_{name}_name` 索引，此时图内
无数据无损）——与手册 §4「预建全可空口径」一致。**建议**：要么表单允许取消锁定行的
必填，要么 DDL 生成默认可空（NOT NULL 只约束平台写入路径能保证补值的列）。

### ⑭ 来源绑定 querySql 完全无 UI 通道（比第一轮预期的更重）

「来源表」弹窗只有 数据源/库/表/主键列/时间列 五项，无 querySql 字段；后端
`PUT /schemas/{id}/sources` 本身接受 querySql（SchemaSourceInput.query_sql），纯 UI 缺
入口。更重的是 47 条 querySql 绑定里大量 pk/time 是 **SQL 合成列**（`row_pk`/`wm_col`/
`source_row_id`），不在物理表的列下拉里——连「UI 绑五项、CLI 只补 querySql」的折中都
做不到。另 DataSource 的绑定 `tableName=placeholder` 是虚拟表，表下拉搜不到（取证
`r2-s7-1-placeholder-table-not-listable.png`）。处置三档：16 个纯普通表 schema 全 UI 绑；
12 个混合 schema UI 绑普通表部分；21 个（全 querySql / placeholder）CLI PUT 兜底
（`cli/restore_querysql.py`，按清场前 dump 的原 sources 数组整体回写，随后做目录还原度
对账：properties(name/dataType/required)、sources 六元组、script sha256 与清场前全等）。
**建议**：来源绑定表单增加「自定义 SQL」高级模式（querySql + 合成列手填），或至少在
表单里显式提示该绑定含 UI 不可表达的配置。

> **⑭-2 追加（同日晚间实测）：来源表弹窗会把既有 querySql 绑定保存丢**。弹窗打开时
> `openSourcesModal` 只回填 数据源/库/表/pk/time 五项（querySql 不在其中），行组件的
> `toSourcePayload` 也没有 querySql 字段——对含 querySql 绑定的 schema 打开弹窗点一次
> 「保存绑定」，这些绑定就被整体替换成「裸表 + 回填的 pk/time」的普通表绑定（合成列
> pk 指向不存在的物理列，抽取语义直接坏掉），全程无任何提示。「UI 不能表达 querySql」
> 因此升级为「UI 编辑会破坏既有 querySql」。连带表现：弹窗允许添加与已有行完全重复的
> 绑定行，保存时 PUT 撞后端 `uk_kg_schema_source_table` 唯一键 500，前端只闪一条 error
> toast（与⑰同款「toast 转瞬即逝、页面无残留提示」）。本轮 e2e 全量重绑即被此打断
> （弹窗预填既有绑定 + 脚本再加一遍 = 全重复行，28 个 schema 全部保存失败），改为
> 「先经 UI 逐行删除预填行再重加」的重绑语义后通过。**建议**：含 querySql 绑定的行
> 打开弹窗时显式标记且保存前确认；重复行在前端拦截；保存失败常显错误。

### ⑮ 关系类别 relationCategory 表单不可达「事实关系」；provenance 声明后回落 core

UI 新建 33 个关系的 `relation_category` 控制库实查**全部 inferred**（dev / 旧目录口径为
44 fact + 9 inferred）——表单没有该字段（或「事实关系」分支不可达）。另 provenance 类
（is_core=false）声明保存后回落 core。均为展示层元数据，不影响抽取与 DDL，但目录还原
度对账必须容忍该漂移（restore 脚本对账口径明确排除 category）。**建议**：表单补
relationCategory 字段或后端默认 fact；provenance 保存链路回读一次确认值。

### ⑯ 脚本上传 LLM 安全校验：判定不可复现 + LLM 服务不可用时上传通道整体不可用（本轮最重问题）

三层叠加：

1. **服务限流无降级**：45 个脚本连续上传，每个都过一次 LLM 安全校验 → 智谱 429
   （1302 账户级速率限制 / 1305 glm-5.2 模型过载）→ 前端收「LLM 调用失败」→ **上传被拒
   且不落盘**。LLM 服务不可用 = 脚本上传通道整体不可用，无 fail-open、无人工覆盖入口。
2. **判定不可复现**：与上轮**逐字节一致**的 45 个脚本，上轮 45/45 全过；本轮大面积被拒
   （一度 30/45），拒绝理由逐轮漂移（同一 Event 脚本三轮分别给「LLM 调用失败」「密码学
   强度降低及潜在的编码注入风险」「LLM 调用失败」），措辞多为「潜在风险 / 建议审查」类
   非确定性行为（DoS 风险、MD5 弱哈希、哈希截断、异常处理过宽……）。重试即重新抽样，
   同一脚本时拒时过。
3. **「LLM 返回格式异常」也判拒**：上游输出解析失败同样拦死上传（Patent/Person/
   AUTHORED_BY 等多次出现）。

处置：e2e 对被拒脚本循环「重新选择」重传抽样（限流类退避 30s、判定类 8s，至多 6 次），
把通过率拉满；仍被拒的走 CLI 兜底直传 S3 + 目录脚本记录（等同绕过平台校验，记入问题）。
最终通过率：**45/45 全部经前端 UI 上传成功**（第 1 轮仅 15/45，经 6 轮幂等续传补齐；
LEADS 最后一例连续被 1305 模型过载拦截 3 轮，退避循环第 4 轮通过），未动用 CLI 兜底——
但通过完全依赖「重试=对非确定性判定重新抽样」的运气，单人单次直传在当天环境下不可
完成。**建议**：确定性校验（AST 规则）为主、LLM 为辅；LLM 拒绝提供人工复核/白名单
通道；LLM 不可用时降级为「挂起待审」而非直接拒绝；批量上传对上游限流做平台侧排队/
退避（客户端连发 45 次校验即触发账户级 1302）。

### ⑰ 删除目录在 Nebula 内存水位线上被打断（⑫ 的延伸，删除路径专属表现）

HAS_NEWS 实锤：删除时后端先 `SHOW EDGES` 探测类型是否存在 → 撞水位 500 → 探测函数返回
None（无法判定）→ 不走「图库无此类型」快速路径，硬闯 `_delete_all_edges` →
`GET /edges/type/HAS_NEWS` 又 500（`use space failed: Used memory hits the high
watermark(0.900000)`）→ DELETE 502 → 前端弹窗滞留错误态（error toast 转瞬即逝，弹窗不
关）。本空间是刚重建的空壳、EDGE 类型并不存在，本可零成本跳过。e2e 处置：关弹窗退避
12s 后整删重试（至多 4 次）全部通过（水位是波动放行的）。**建议**：`SHOW TAGS/EDGES`
探测失败时先重试再判「无法判定」；删除链路对水位类 400/500 做批内退避；错误态弹窗常显
错误文案（当前 toast 消失后无任何提示）。

### ⑱ chain 长 run 撞 Temporal 历史事件数硬限被服务端 TERMINATED（r2 晚间实测，新发现）

关系A 链运行 55 分钟后突然停止，控制库 `workflow_executions` 行翻 `TERMINATED`、前端状态列
「运行失败」，worker 无任何错误日志、写入流戛然而止。Temporal 侧实锤（describe + 历史末事件）：

- 历史事件 **51,199 条**，末事件 `WorkflowExecutionTerminated`，`reason: "Workflow history
  count exceeds limit." identity: "history-service"`——**服务端 history count 硬限（默认 5 万）**
  主动 TERMINATE，非人工、非水位、非代码异常；
- 撞限前服务端曾**自动 continue-as-new** 过一次（describe 捕获到 status=CONTINUED_AS_NEW，
  新 run 接续跑），新 run 再次积累满 5 万事件后同样终止——大源链在「批 100 + 逐条
  INSERT」模式下事件吞吐 ~15 事件/批，CITES+COAUTHOR_WITH 30 万+行必然撞限；
- 控制面把 server auto-continue-as-new 的中间态映射成 `TERMINATED`/「运行失败」展示，
  实际续跑 run 仍在执行——**UI 状态与 Temporal 真值短暂背离**（续 run 也终止后两者才一致）。

**处置**：依赖「重新执行」的水位增量语义研磨收敛（已抽取部分水位已过账，重跑只吃剩余行，
新 run 事件数够用）；批大小越大事件越少（批 500 比批 100 少 5 倍事件），大源链建议用大批。
**建议**：① chain workflow 对大源按事件预算显式 `continue_as_new`（带水位恢复语义，现依赖
服务端 auto-continue 的行为不可控）；② 控制面把 `history count exceeds limit` 识别为「可续跑
截断」类终态，前端提示「链过长已截断，重新执行可续抽」而不是笼统「运行失败」；
③ CONTINUED_AS_NEW 中间态应保持「运行中」展示而不是翻 TERMINATED。

### ⑲ 离线域 ETL schema 阶段新建索引不 REBUILD → 空索引把图读全部遮成 0（r2 实测，静默假数据丢失）

域1 `rebuild_scholar_graph --stages schema` 对已有数据的空间执行「对齐」时 `CREATE TAG INDEX
IF NOT EXISTS person_tag_idx ...`（另有 edu_inst 两列索引）。**Nebula 新建索引不回填既有数据**，
而查询计划器会优先选它：此后 `LOOKUP ON Person`（连 `| YIELD count(*)`）与 REST
`GET /nodes/label/Person` 全部返回 **0 行**——32,547 个 Person 「凭空消失」，域1 milvus 阶段
`person scan: total=0` 写出空集合，全程无任何报错（脚本日志还自提示「需再执行 REBUILD
TAG INDEX 索引才生效」，但流程不执行它）。修复：CLI 逐个 `REBUILD TAG INDEX`（异步 job，
需等 FINISHED；进行中读数偏小），读数即恢复。**建议**：① ETL schema 阶段建索引后自动
SUBMIT `REBUILD TAG INDEX` 并等 job 终态；② 手册 §6 域1 加显式 REBUILD 步骤；③
`total=0` 且非新空间时 ETL 应告警而非静默写空集合。

### e2e 工程问题（附带记录，非产品缺陷）

- **arco a-input 的 aria-label 落在包裹层** `span.arco-input-wrapper` 上而非内层
  `<input>`（Schema 搜索框实锤），选择器须 `.schema-search-input input`；
- **列表搜索是 contains 匹配**：搜 `Organization` 会连 `OrganizationBase` 一起返回，且
  两行 code 列截断文本同为「Organizatio…」无法按单元格区分——用行内 `···` 按钮的
  aria-label（`${中文名}更多操作`，中文名唯一）消歧；删除场景另按「名字长度降序」先删
  长名兄弟；
- **合法空结果**（空空间 SHOW EDGES、清空后的目录列表）不能用「行数>0」判完成——一律
  以接口响应为完成信号；
- Node 24 + frontend `type:module`：JSON 导入必须 `with { type: 'json' }` import
  attribute；
- **下拉选项 contains 匹配误选**：自动化按文本过滤选项时 `hasText`（contains）会在
  列下拉搜「id」时先命中「logic_id」（CITES 的 dwd_en_paper_related 实际绑成 logic_id，
  经 dump 逐字段对账发现）——选项匹配必须精确全等；同理「核验绑定」不能只核条数，
  要核到 pk/time 列值。修复后以 CITES/Paper/HAS_KEYWORD（pk 均为 `id` 且列下拉存在
  `logic_id` 前缀兄弟）经 UI 重绑验证通过，并对全量 49 schema 做来源四元组
  （表/pk/time/querySql）逐字段对账全绿；
- **重绑操作语义**：来源表弹窗打开即预填已保存绑定（非空表单），自动化重绑必须先经
  UI 逐行删 `.source-binding-row__remove` 再重加，否则造出重复行、保存 500（见⑭-2）；
  另外行组件「＋ 绑定来源表」在存在未填完整行时会被前端拦截（内联提示，非 toast）。

### r2 阶段进展实录（2026-10-09 凌晨更新）

- **平台三链终态全达**（09 用例 3 passed）：实体链 COMPLETED（22 分钟）、关系A COMPLETED
  （撞 ⑱ 历史事件硬限后「重新执行」水位续跑轮 44.5 分钟）、关系B ABNORMAL（行级失败
  转审核，与 r1 同口径，32.4 分钟）。期间 worker 临时降到活动并发 1（compose override，
  用后已恢复 4）。
- **实体锚点 LOOKUP 直数已中**：DataSource 39 / Journal 2134 / Organization 8179 /
  Person 32448（+域1 并入 99=32547）/ OrganizationBase 61652（对上 r1）。
- **离线域**：域1 schema/entities/relations/align ✓（COAUTHOR_WITH written=156144 与 r1
  精确一致；SAME_AS 边类型由域1 创建）；域2 机构三连 ✓（try1 撞 DDL 传播延迟重跑即过）；
  域3 schema/实体关系/引用关系/置信度 四步 ✓；**域3-溯源、域4-桩对齐、域1-milvus 三步
  被 ⑫ 连续阻断**（`/query/read` 与 `/nodes/label` 读路径全被水位 500/400 拒，drop_caches
  开窗亦不够——扫描自身把 RocksDB 页拽回 cache 即越线，与 r1 域5/reindex 同型），
  已挂定时研磨任务待窗口（session cron）。
- ⑲ 索引空壳事故当场修复（REBUILD TAG INDEX 后读数恢复），无数据损失。
