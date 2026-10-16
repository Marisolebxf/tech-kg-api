# gkx_local_1 图空间精简测试手册（3 实体 3 关系 · 页面操作）

覆盖实体 `Paper`（论文）/ `Journal`（期刊）/ `IndustryChain`（产业链），关系 `PUBLISHED_IN`（论文发表，Paper→Journal）/ `AUTHORED_BY`（论文署名，Paper→Person）/ `BELONGS_TO_NODE`（企业归属链节点，Organization→IndustryNode）。全部步骤按页面上鼠标怎么点来写。

## Step 1 建 Schema（Schema 管理页）

1. 「平台总览」右上角**全局图空间选择器**切到 `gkx_local_1`——Schema 管理、图谱构建、总览统计都跟随这个选择。
2. 左侧导航 **「Schema 管理」**，默认在「标准实体」标签页。
3. 点右上 **「＋ 增加」** 打开新建弹窗：
   - 实体名 `IndustryChain`、中文名 `产业链`、说明随意（如"产业链主链"）。
   - 属性表里带锁图标的**公共必选属性已预置**（id/name/create_time/update_time/source_table 等，不可改不用管），点「添加属性」补业务属性：`chain_code`（string）、`chain_name`（string）。
   - 「来源表（可选）」这次先不绑，Step 2 单独做。
   - 底部「nGQL 预览（创建时将执行）」扫一眼 CREATE TAG 语句 → **「确认创建」**。
4. 应看到 toast「已创建并执行图 DDL：CREATE TAG …」；列表多出一行「产业链 / IndustryChain」，**脚本状态**列显示「未上传」。
5. 同法建 `Paper`（论文）、`Journal`（期刊）。属性想后补也行，但注意：后补属性会弹「请更新脚本后重跑」引导——新列脚本不输出就永远是 NULL。
6. 切到 **「关系」** 标签页，「＋ 增加」：
   - 关系英文名 `PUBLISHED_IN`、中文名 `论文发表关系`、**起点实体**下拉选 `Paper`、**终点实体**选 `Journal` → 确认创建（执行 CREATE EDGE）。
   - 同法建 `AUTHORED_BY`（论文署名关系，Paper→**Person**）、`BELONGS_TO_NODE`（企业归属产业链节点，**Organization**→**IndustryNode**）。Person/Organization/IndustryNode 是本栈存量实体，新空间里没有就先回「标准实体」按 1–5 建出来。

## Step 2 绑来源表（行级「来源表」弹窗）

先记住页面能力边界：绑定表单只有 **数据源 / 库 / 表 / 主键列 / 时间列** 五个下拉，**没有 querySql 输入框**。裸表绑定页面全流程可做；带 SQL 的绑定（裁列、过滤 `is_deleted`、语义映射）是接口预置的，弹窗里同样只显示这五个下拉值，SQL 本体存在后端（要核对去物料包 `docs/gkx_local_1_materials/bindings.json`）。本栈已全部配好，这一步在页面上做的是**核对 + 会绑裸表**。

1. 「Schema 管理」实体列表找到「期刊」行 → 操作列 **「···」→「来源表」**。
2. 弹窗「来源表 · 期刊」→ **「＋ 绑定来源表」** 加一行，依次选：
   - 数据源 `MYSQL-DWD-LOCAL`（下拉显示"名称（host）"格式）
   - 库 `gkx_dwd_local`
   - 表 `dwd_zh_journal` —— 主键列/时间列会按表结构自动带出（`pk_id` / `updated_time`），不对再手改。
3. 再「＋ 绑定来源表」加第二行 `dwd_en_journal`（`dwd_id` / `updated_time`）。
4. **「保存绑定」** → toast「来源表绑定已保存」。弹窗顶部提示说的是实话：**保存绑定不会自动触发抽取**。
5. 同法核对/绑定其余选样（表 → 主键列 / 时间列）：

| Schema | 绑定行 | 备注 |
|---|---|---|
| Paper | `dwd_en_paper` → dwd_id / updated_time；`dwd_zh_paper` → pk_id / updated_time；`dwd_scholar_papers` → dwd_id / 无时间列 | 第 3 行带预置 SQL（73.8 万论文那源） |
| Journal | `dwd_zh_journal`、`dwd_en_journal` | 裸表 |
| IndustryChain | `dwd_industry_chain_info` → row_pk / 无时间列 | 带预置 SQL（语义映射） |
| PUBLISHED_IN | `dwd_zh_paper`、`dwd_en_paper` | 与 Paper 前两行同口径 |
| AUTHORED_BY | `dwd_zh_author` → pk_id；`dwd_en_author` → dwd_id；`dwd_scholar_paper_relation` → dwd_id；`dwd_scholar_paper_relation_element` → row_id | 四行都无时间列、都带预置 SQL |
| BELONGS_TO_NODE | `dwd_org_industry_chain_dtl` → row_pk / 无时间列 | 带预置 SQL（JSON 展开） |

6. 有行没选完整（数据源/库/表缺一）就保存会被拦：toast「存在未选择完整的来源表绑定（数据源/库/表均需选择）」。

## Step 3 传脚本（行级「更换脚本」）

1. 「产业链」行 → 操作列 **「更换脚本」**（从未传过时按钮文案是「上传脚本」）。
2. 弹窗里选择文件 `docs/gkx_local_1_materials/scripts/industry_chain_entity_step.py`（仅支持 .py）→ 提交。
3. 应看到「正在上传并校验...」→「**脚本已通过安全校验并保存**」（通道带语法/入口静态检查 + LLM 审核，被拒会给出原因）。
4. 列表「脚本状态」从「未上传」变「**已上传**」；没跑过抽取会带「未运行」角标，脚本更新过没重跑则显示「待重跑」，跑挂了显示「上次失败」。
5. 同法传其余 5 个（文件都在物料包 `docs/gkx_local_1_materials/scripts/` 下）：

| Schema | 脚本文件 |
|---|---|
| Paper | paper_entity_step.py |
| Journal | journal_entity_step.py |
| IndustryChain | industry_chain_entity_step.py |
| PUBLISHED_IN | published_in_relation_step.py |
| AUTHORED_BY | authored_by_relation_step.py |
| BELONGS_TO_NODE | belongs_to_node_relation_step.py |

「查看脚本」随时可看已传内容；脚本由 `script/tools/build_portable_steps.py` 自动生成，**勿手改**。

## Step 4 跑抽取（图谱构建 → 新建任务）

1. 左侧导航 **「图谱构建」**（本页就是任务列表）→ 右上 **「新建任务」**。
2. 弹窗里照这个填：
   - 任务名称：`gkx_local_1-精简样例链`
   - 任务类型：**「多脚本串行」**
   - 「串联 Schema 队列」搜索框依次添加 6 个：IndustryChain、Journal、Paper、PUBLISHED_IN、AUTHORED_BY、BELONGS_TO_NODE；用行内 **「上移」「下移」** 排成**先实体后关系**（边要等端点实体先在图里），「移除」可删；至少 2 个、最多 20 个。
   - 批大小（对每个 Schema 生效）：`2000`（默认 500）
   - MySQL 数据源 / 数据库：默认跟随 Schema 绑定，**不用动**（它只注入脚本 ctx.mysql，读取源始终按来源绑定走）
   - 增量游标 since：留空
   - 执行模式：**「一次性」** → 创建。
3. 任务卡出现在列表；点卡片进 **「任务详情」**：每个 Schema 一个抽屉，抽屉里是脚本转换步；上方执行历史看每次触发的终态。
4. 终态怎么读：`COMPLETED` 全部成功；`FAILED` 整链中止（链上任一环失败即中止）；`ABNORMAL` **≠失败**——抽取完成但有个别失败行转了人工审核，图已写入。
5. 只想跑一个 Schema：任务类型选「单脚本抽取」，选目标 Schema 即可（本栈 10-16 下午灌新绑定用的就是这种逐个触发）。
6. 幂等：跑完再触发一次，水位已高 → 空读快过、不重复写图。

参考时间线（本栈 2026-10-16 实录，供对照量级）：14:54 触发 Paper → 图内论文 4,000 → **742,106**；AUTHORED_BY 15:07 首跑 FAILED、15:11 重试 COMPLETED → 边 18,583 → **220,822**。

## Step 5 验收对账（页面 checkpoints）

| 页面 | 操作 | 应看到（2026-10-16 口径） |
|---|---|---|
| 平台总览 | 图空间切 gkx_local_1，看图资产统计卡 | 总量 ≈ **873,193 点 / 617,322 边**；「昨日图谱数据变化」卡片点开有当前总量 + 当日新增 + 统计日 |
| 实体列表 | 类型切「论文」 | 「共 742,106 个实体」；期刊 2,134、产业链 2 |
| 实体列表 | 点开任意一条论文 | 属性与源表一致；溯源列 source_table 指向 `gkx_dwd_local.dwd_zh_paper / dwd_en_paper / dwd_scholar_papers` |
| 实体列表 | 属性关键词搜索（DOI、标题词） | 命中且属于该类型 |
| 图谱可视化 | 搜一篇论文或一个机构 | 周边关系展开，AUTHORED_BY / PUBLISHED_IN 连线可点开看属性 |
| 任务详情 | 看执行历史 | 终态与 Step 4 的语义一致；失败步点开有错误信息 |
| 人工审核 | 打开「人工审核」页 | 存量案：实体对齐裁决（T_LINK）约 2,991 OPEN、抽取失败重跑（T_EXTRACT_FAIL）约 4,670 OPEN，后者页面可一键重跑 |

判读口径：**图 ≤ 源行合计属预期**（同名消歧 T_LINK 灰案扣留 + 毒行转审核）。选样对齐参考：BELONGS_TO_NODE 源 2,943 = 图 2,943 精确一致；Paper 源 742,114 → 图 742,106（差 8）；AUTHORED_BY 源 303,167 → 图 220,822（端点/去重/灰区扣留）。
