# 失败重跑与写前消歧 · 抽取脚本样例包

配套「平台喂批次抽取」（`kg.schema.extract`）两个核心治理链路的**可上传样例 +
演示数据 + 零库本地验证**：

| 文件 | 演示链路 | 源表 |
|---|---|---|
| `失败重跑_产品实体.py` | 毒行 → `failures` → **T_EXTRACT_FAIL** 审核 case（队列 C 类）→ 审核工作台点「重跑」→ 新执行 `triggerSource=RERUN` → 修数后 case 转 RESOLVED | `demo_fail_product`（3 好行 + 3 毒行） |
| `写前消歧_同名专家.py` | 实体写图前平台**同名召回 + 打分**（0.6×名称 + 0.4×属性一致率，阈值 0.85/0.65/0.08）：merge 自动并入 / **灰区 [0.65,0.85) 扣留建 T_LINK**（队列 A 类）/ new 直写 | `demo_disambig_expert`（两轮：4 种子 + 4 同名冲突） |
| `关系挂起_任职边.py` | 机构名解析未命中/多义 → `pendingReview` 人工裁决（默认 T_DIRECT，统一方案落地后并入 T_LINK）；端点命中灰区扣留实体的边被**停靠**（`_pendingRelations`），裁决后补写 | `demo_works_at_relation`（2 可解析 + 1 多义 + 1 未命中 + 2 毒行） |
| `demo_数据.sql` | 三张演示表的 DDL + INSERT（独立库 `techkg_script_demo`） | — |
| `本地验证.py` | 零数据库/零图库跑通三个脚本，并用**平台真实解析器**（`script_steps.extract_declared_steps`）与**真实消歧打分器**（`entity_disambiguation.score_candidate/decide`）断言输出契约与三分支预测 | — |

三个脚本均为 `@step` 多步形态（步顺序 = 函数源码出现顺序，与顶层 `transform`
互斥）、纯转换（不连库、不连图——入库/消歧/索引/水位全由平台负责），
`failures` 的 `recordId` 必填非 None（否则被平台整条丢弃）。

## 第二轮同名专家的三个分支（demo_数据.sql A2 段设计）

| 第二轮行 | 与图内同名者属性重合 | 得分 | 平台判定 |
|---|---|---|---|
| E2001 王伟（单位同、简介同） | 2/2 | 1.00 | **merge** 自动并入 `expert_E1001` |
| E2002 李娜（单位同、简介异） | 1/2 | 0.80 | **灰区 → T_LINK 扣留** |
| E2003 张敏（单位异、简介异） | 0/2 | 0.60 | **new** 直接新建 |
| E2004 刘洋（无单位；图内同名者无简介） | 无可比属性 → 0.5 | 0.80 | **灰区 → T_LINK 扣留** |

## 本地验证（改动脚本/数据后、上传平台前先跑）

```bash
backend/.venv/bin/python docs/抽取脚本示例/失败重跑与写前消歧/本地验证.py
```

输出末行「全部通过」即契约、毒行、三分支预测均符合预期。

## 隔离运行手册（真跑平台时）

**原则：不碰任何现有库。** 当前共享 trs-graph 上已有 `dev` / `dev2` / `techkg`
等 12 个空间、MySQL 上有 `gkx_element`（vendor 只读）等业务库——演示数据一律
进**新建的独立空间/独立库**，用完即删。

1. **独立图空间**（经 trs-graph REST 或 Nebula console，`X-API-Key` 见
   `backend/.env`）：

   ```ngql
   CREATE SPACE IF NOT EXISTS techkg_script_demo (vid_type = FIXED_STRING(64));
   ```

2. **独立 API 栈**：`docker-compose.lizhou.yml` 起独立栈（8006 端口、独立
   task queue）。⚠️ 它的 `env_file` 指向 `backend/.env`，其中
   `TRS_GRAPH_SPACE=dev2`——**务必覆盖成演示空间**（compose `environment`
   加 `TRS_GRAPH_SPACE: techkg_script_demo`），否则会写进共享 dev2。

3. **演示源库**：在抽取任务可用的 MySQL 实例上执行 `demo_数据.sql`
   （建独立库 `techkg_script_demo`；A2 第二轮 INSERT 默认注释着，
   跑完第一轮抽取再放开执行）。

4. **Schema**：独立栈 `SCHEMA_AUTO_INIT=true` 开机即种子 Product / Expert /
   WORKS_AT（含 `name_zh` / `organization_name_zh` / `bio_zh` /
   `product_name` 等脚本用到的属性列），无需新建；首次对演示空间运行时若
   TAG/EDGE 缺 DDL，参照 `script/run_dev2_schema_ddl.py` 对该空间执行 pending
   DDL。程序化闭环参照根目录 `dev2_extract_e2e.py`。

5. **上传/绑定/触发**（Schema 管理页 `/schema`）：对目标 Schema 点「上传
   脚本」→「来源表」绑定对应 demo 表（pk=`id`，增量列=`update_time`）→
   「保存并触发抽取」。失败重跑脚本一次跑完即得 3 条 T_EXTRACT_FAIL case
   （队列 C 类）；随后在审核工作台点「重跑」，或在 MySQL 里
   `UPDATE demo_fail_product SET product_name='边缘计算网关' WHERE id IN (4,5,6)`
   修数后再重跑，case 转 RESOLVED。

6. **两轮编排（写前消歧）**：第一轮只执行 A2 种子 4 行 → 触发抽取#1（全部
   直写）→ 放开 A2 第二轮注释并执行 → 触发抽取#2（增量水位只读新 4 行）→
   图内同名比对：E2001 自动并入、E2002/E2004 建灰区 T_LINK case、E2003 新建。
   在审核工作台对 T_LINK case 裁决 merge/create 后实体才落图。之后再跑
   关系挂起脚本：指向 `expert_E2002` 的边会被停靠进其未决 case，裁决后补写。

7. **清理**：

   ```sql
   DROP DATABASE IF EXISTS techkg_script_demo;      -- MySQL 演示源库
   ```

   ```ngql
   DROP SPACE IF EXISTS techkg_script_demo;          -- 演示图空间
   ```

   演示栈里的审核 case 随独立栈 MySQL 一起处理（`docker compose -f
   docker-compose.lizhou.yml down -v`），不影响主部署。

## 与其它样例的关系

- 单步 `transform` / STEPS 清单形态、SDK（`ctx.mysql` / `ctx.llm` /
  `ctx.config`）用法见上级目录 `sample_product_entity_extract.py` /
  `sample_produces_relation_extract.py` / `多步示例_三步出边.py`；
- 本包聚焦**治理链路触发**（failures / 同名消歧 / pendingReview），脚本刻意
  保持零外部依赖（机构别名表内联），保证 `本地验证.py` 离线可跑；
- 统一「写前打分」方案（脚本挂起项并入 T_LINK、detectCollisions 默认关）见
  `docs/T_DIRECT统一写前消歧方案.md`（评审中；落地后本包关系脚本的
  pendingReview 模板语义随之统一，脚本无需改动）。
