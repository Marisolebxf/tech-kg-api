# KG-COMPLY-STRUCT-L01 · 图谱结构与合规验收空间选定

## 一分钟说明（给非图谱同事）

本文件只回答两件事：**合规验收用的这张图，点分几类、连线分几种、每个点怎么编号；以及这张图画在哪个图数据库空间里。**

- 点的类别叫 Tag，连线的种类叫 Edge，点的唯一编号叫 VID（相当于身份证号）。
- 空间（space）是图数据库里一块独立区域，相当于仓库隔间；不同空间的数据互不串门。
- 上游 `KG-7ELEM-BUILD-REQ-L01` 已经把「必须有哪 24 条关系」定死（编号 M01–M24），本任务**不加不减不改**，只负责把它落成可施工的 Tag / Edge / VID，并选定空间。
- 本任务**不建空间、不写库、不灌数、不跑算法**，只交结构与空间选择。
- 科学技术全景页要读的「技术点」（`technology_node_id` 那套点）作为单独一层夹带，不并进七要素「技术」，不新增必须边；细节见 [科学技术全景-建图基线](./科学技术全景-建图基线.md)。

---

## 任务卡

| 项 | 内容 |
|---|---|
| 任务 | `KG-COMPLY-STRUCT-L01`（合规验收线） |
| 认领 / 确认 | 唐绍祖（human） |
| 日期 | 2026-11-07 |
| 交付位置 | 本目录 `07-图数据库集成` |
| 输入 | [KG-7ELEM-BUILD-REQ-L01](./KG-7ELEM-BUILD-REQ-L01-七要素必须三元组与建图需求.md)（M01–M24，已签收）、[KG-7ELEM-SCHEMA-DDL-L01](./KG-7ELEM-SCHEMA-DDL-L01-图数据库初始化脚本.md)、[科学技术全景-建图基线](./科学技术全景-建图基线.md)、[WBS-全景维护与知识图谱分工](./WBS-全景维护与知识图谱分工.md) |
| 附表 | [KG-COMPLY-STRUCT-L01-附表-结构与空间.xlsx](./KG-COMPLY-STRUCT-L01-附表-结构与空间.xlsx)（M01–M24 / B1–B6 / 空间对比） |
| 不做 | 不建空间、不写库、不灌数、不跑算法、不改 L01 正文 |

**DoD（派单原文 4 条）**

1. 结构覆盖 L01 必须三元组 M01–M24。不新增必须边，不把技术点并进七要素「技术」。不建的不写，待确认的不猜。
2. 同一套 Tag / Edge / VID 既能建在新空间，也能补进 `demo_gkx_chain`。两种放法都写清，不只写其中一种。
3. 书面选定本期合规验收用哪一种，并写明选定理由。
4. 不写库，不改 L01 正文。

---

## 1. 结构

一套结构，两层，一个空间。七要素层按 M01–M24；技术点层按 B1–B6 夹带，单独一层。

- 七要素「技术」= 论文 / 专利 / 项目，**只此三者**。
- 技术点（`technology_node_id`）**不并进**七要素「技术」，不新增必须边。
- 两层同空间，**Tag 名不混用**。

### 1.1 Tag

| Tag | 层 | VID 规则 | 必需属性 | 现有数据 |
|---|---|---|---|---|
| `enterprise` | 七要素 | `ent:<信用代码>`；无码 `ent:<name_norm>` | name, enterprise_code, chain_role, weight, props | 待建桥 |
| `segment` | 七要素 | `seg:<chain_code>:<node_id>` | name, segment_key, chain_id, chain_stage, weight | 已有 |
| `research` | 七要素 | `inst:<org_id>` | name, org_type, props | 可接 |
| `person` | 七要素 | `person:<talent_id>` | name, org, field, props | 可接 |
| `paper` | 七要素 | `paper:<doi>`；无 DOI `paper:<src_id>` | name, year, doi, props | 可接 |
| `patent` | 七要素 | `patent:<patent_no>` | name, year, patent_no, props | 可接 |
| `project` | 七要素 | `proj:<project_no>` | name, year, project_no, props | 可接 |
| `policy` | 七要素 | `policy:<policy_id>` | name, level, year, props | 已有 20,000（属性在 props：level/year/type） |
| `institution` | 七要素 | `svc:<org_id>` | name, institution_type, weight, props | 已有 43,296（7 类 institution_type，待甲方确认） |
| `tech_point` | 技术点 | `tp:<technology_node_id>` | technology_node_id, name_zh, name_en, community_role, weighted_degree, community_id, graph_release_id, data_version | 已有 19,430 |
| `tech_paper` | 技术点 | `tp_paper:<paper_id>` | paper_id, name_zh, technology_node_id, data_version | 已有 108,337 |
| `tech_patent` | 技术点 | `tp_patent:<patent_id>` | patent_id, name_zh, technology_node_id, data_version | 已有 172,644 |
| `tech_institution` | 技术点 | `tp_inst:<institution_id>` | institution_id, name_zh, technology_node_id, data_version | 已有 51,000 边侧 |
| `tech_person` | 技术点 | `tp_person:<talent_id>` | talent_id, name_zh, source_paper, source_topic, data_version | 已有（人·论文 1,912 / 人·主题 13,725） |

> 已签收 DDL 里 `research / paper / patent / project / person` 是空属性 Tag。本期**不为加属性重建 Tag**：业务属性先进 `props`（JSON），等 LOAD 签收后再决定是否升列。避免 DDL 变更阻塞 11-09。

### 1.2 七要素层：M01–M24

24 条，一字不改；「燕大对照」列取自 L01，本任务不复用、不据此改边。

| 编号 | 起点 | 关系 | 终点 | 方向 | 燕大对照（只作对照，不复用） | 本期数据 |
|---|---|---|---|---|---|---|
| M01 | 人才 | cooperate | 人才 | 无向 | `COAUTHOR_WITH` 只覆盖合著 | 可用 |
| M02 | 科研机构 | cooperate | 科研机构 | 无向 | 无机构间合作边 | 可用 |
| M03 | 人才 | cooperate | 科研机构 | 无向 | `AFFILIATED_WITH` 是任职，不是合作 | 可用 |
| M04 | 人才 | belong | 科研机构 | 有向 | `AFFILIATED_WITH`（Person→Organization），Organization 非单指科研机构 | 可用 |
| M05 | 科研机构 | belong | 科研机构 | 有向 | `SUBSIDIARY_OF` 是企业子公司 | 不可用 |
| M06 | 技术 | cite | 技术 | 有向 | 论文→论文有 `CITES`；专利引用未列 | 部分可用 |
| M07 | 人才 | participate | 技术 | 有向 | `HAS_PARTICIPANT`/`LEADS` 方向相反（项目→人） | 可用 |
| M08 | 科研机构 | participate | 技术 | 有向 | `FUNDED_BY` 方向相反（项目→机构） | 可用 |
| M09 | 人才 | author_of | 技术 | 有向 | `AUTHORED_BY`/`INVENTED_BY` 方向相反 | 可用 |
| M10 | 科研机构 | publish | 政策 | 有向 | 无政策 EDGE | 不可用 |
| M11 | 政策 | policy_relate | 政策 | 无向 | 无政策 EDGE | 不可用 |
| M12 | 政策 | policy_apply_to | 企业 | 有向 | 无政策 EDGE | 不可用 |
| M13 | 政策 | policy_apply_to | 人才 | 有向 | 无政策 EDGE | 不可用 |
| M14 | 政策 | policy_apply_to | 科研机构 | 有向 | 无政策 EDGE | 不可用 |
| M15 | 产业链环节 | depends_on | 产业链环节 | 有向 | `DOWNSTREAM_OF` 记录 0 边；`CHILD_OF` 是上下级 | 可用 |
| M16 | 政策 | cite | 政策 | 有向 | 无政策 EDGE | 不可用 |
| M17 | 企业 | participates | 产业链环节 | 有向 | `BELONGS_TO_NODE` 是归属，不是参与 | 需建桥 |
| M18 | 服务机构 | participates | 产业链环节 | 有向 | 无服务机构 EDGE | 不可用 |
| M19 | 科研机构 | research_coop | 科研机构 | 双向 | 无机构间合作边 | 可用 |
| M20 | 人才 | talent_coop | 人才 | 双向 | `COAUTHOR_WITH` 只覆盖合著 | 可用 |
| M21 | 服务机构 | service_provide | 企业 | 有向 | 无服务机构 EDGE | 不可用 |
| M22 | 企业 | cooperate | 企业 | 双向 | 企业间只有投资/收购/子公司 | 不可用 |
| M23 | 企业 | supply | 企业 | 有向 | 无供给边 | 不可用 |
| M24 | 企业 | parent_sub | 企业 | 有向 | `SUBSIDIARY_OF` 方向相反 | 不可用 |

边属性统一：`weight double`（没有就 0，不造）、`props string`（JSON：`source_table / source_record_id / batch / confidence / match_method / evidence`）、`first_year int`（没有就不填）。

### 1.3 技术点层：B1–B6（夹带，不新增必须边）

需规出处与逐条口径见 [科学技术全景-建图基线](./科学技术全景-建图基线.md)，此处只记 Tag / VID 与现有规模。

| 编号 | 起点 Tag | 关系 | 终点 Tag | 现有数据 |
|---|---|---|---|---|
| B1 | `tech_point` | 推断边（高/中/低） | `tech_point` | 587,252 边，证据 LOW 约六成 |
| B2 | `tech_point` | 关联实体 | `tech_institution` | 2,528,802 行 |
| B3 | `tech_point` | 关联实体 | `tech_paper` | 108,337 行 |
| B4 | `tech_point` | 关联实体 | `tech_patent` | 172,644 行 |
| B5 | `tech_point` | 关联实体 | `tech_person` | 无直连表；代表论文上的人，或代表论文主题上的人 |
| B6 | `tech_point` | 序列 | `tech_point` | 47,909 步 / 12,891 条路径，单快照 |

B5 必须落 `source_paper` / `source_topic` 两布尔属性，页面标明来源；两路不得混成一条边。B6 是点的序列，不是新边型。

### 1.4 不建的结构（DoD 第 1 条：不建的不写）

| 不建 | 原因 | 留什么 |
|---|---|---|
| 技术链 `TechChain` 实体 | 燕大只有 Keyword 无层级；我方无 TechChain 本体 | 用 `tech_point` 层级/社区近似，页头标口径 |
| `dataset` 数据集实体 | 两侧均无 | 不建 Tag |
| 事件 / 活动 / 创新载体 | L02 已判不进七要素闭包 | 不建 Tag，页面用业务表 |
| 服务机构服务类型细分 | 连服务机构本身都没有 | 只留 `institution` 空 Tag + M18/M21 空边 |

### 1.5 待确认不猜

- M01–M24 的**基数**：L03 全部写「待确认」，本任务不改，不猜。
- M06 专利引用：燕大未列，是否本期建由 LOAD 决定，本任务只留边型。
- M15 上下游 vs 上下级：需规未区分，本任务不裁，只按 `depends_on` 一种边型；细分属性走 `props.dependency_type`。

---

## 2. 放法 A · 新建合规空间

**做法**：新建 NebulaGraph space（建议名 `gkx_comply`，最终名书面确认），把 §1 的 14 个 Tag、24 + 6 条 Edge 原样建进去。

| 项 | 说明 |
|---|---|
| 建空间 | `CREATE SPACE gkx_comply (vid_type=FIXED_STRING(80))`，再建 Tag/Edge；**本任务不执行** |
| 灌数 | 由 `KG-COMPLY-LOAD-L01`（燕大）按 M01–M24 入图；技术点层可夹带 |
| 读图改造 | `lumen-algo-py` 读图 space 配置改 `gkx_comply`；Java 门面同步；前端不动 |
| 优点 | 干净、易审计、与 `gkx_chain`、`demo_gkx_chain` 三方隔离 |
| 缺点 | 空空间，必须先灌数才能跑算法；11-09 前风险最高；读图要改配置 |
| 适用 | 项目组/监理书面要求「合规验收不得用 demo 空间」时 |

**同一套结构要装得下**：14 个 Tag 名、24 + 6 条边名、VID 规则与 §1 完全一致，只换 space 名。无需任何结构改动。

---

## 3. 放法 B · 补 `demo_gkx_chain`

**做法**：在已有 space `demo_gkx_chain` 内按 §1 补 Tag/Edge；两层 Tag 并存不混用。

| 项 | 说明 |
|---|---|
| 已有数据 | 技术点 19,430；论文 108,337；专利 126,484；机构 17,542；人·论文 1,912；人·主题 13,725。边：高/中证据 172,000、低证据 369,428、论文 108,337、专利 172,644、机构 51,000、人·论文 3,078、人·主题 108,500、路径步 35,018（2026-11-06 页面读回，见 [背景稿](./WBS-全景维护与知识图谱分工-背景.md)） |
| 补什么 | 七要素层补齐 M01–M24 已能供数的边；空 Tag `policy` / `institution` 保留；技术点层 B1–B6 沿用现有 |
| 读图改造 | 零改造：展示在线读图已按 `demo_gkx_chain` 实现（`INT-C-X-490`） |
| 优点 | ① 立即可跑算法，不依赖先灌数；② 11-09 前能出结果；③ 与正式 `gkx_chain` 继续隔离，不双写、不互拷 |
| 缺点 | ① 「demo」名字在合规验收里需解释，靠 `props.batch` 与只读契约证明合规层；② 燕大 LOAD 若坚持只写 `gkx_chain`，需一句书面确认；③ 未来若迁独立空间，需一次导出/重建 |
| 适用 | 本期（默认） |

**同一套结构要装得下**：同 §1，不改 Tag / Edge / VID。

---

## 4. 书面选定

> **选定放法 B：本期合规验收的图结构落在 NebulaGraph space `demo_gkx_chain`。**
>
> - 七要素层按 M01–M24 补 Tag/Edge；技术点层按 B1–B6 夹带；两层同空间、Tag 名不混用。
> - **不新建空间**。正式加工线 `gkx_chain` 仍归 WBS-07-00G / 00H，与本空间隔离，不双写、不互拷。
> - 本空间即图相关算法（中心性、社群、路径、子图）跑出结果的空间。

**选定理由（4 条）**

1. **有数据**：已有技术点、论文、专利、机构、产业链两层真实数据，补结构即可跑算法；新空间是空的，必须先等灌数。
2. **零读图改造**：展示在线读图已按 `demo_gkx_chain` 实现，不新增改造风险。
3. **11-09 可达**：不依赖燕大先入库，符合本期验收时间。
4. **不破正式线**：`demo_gkx_chain` 与 `gkx_chain` 继续隔离，正式加工线结构不变。

**触发改用放法 A 的条件（任一成立，需重新书面确认）**

1. 项目组/监理书面要求「合规验收不得使用 demo 空间」；
2. 燕大 LOAD 拒绝写 `demo_gkx_chain`，且不出双写方案；
3. `demo_gkx_chain` 出现被清空/重建风险，无法保证验收期稳定。

**空间纪律**

- 不写 `gkx_chain`；不把 `gkx_chain` 的点边拷进 `demo_gkx_chain`；不反向拷。
- 不以 `gkx_local_1` / `gkx_full_1` 当入库空间。
- 不双写。
- 建空间、DDL 变更不在本任务执行；密码与连接串不进 git。

---

## 5. 交付与下游

| 交付物 | 状态 |
|---|---|
| 本文件（结构 + 两种放法 + 选定） | 完成 |
| [附表 xlsx](./KG-COMPLY-STRUCT-L01-附表-结构与空间.xlsx)（3 sheet） | 完成 |
| 燕大书面确认（合规层写 `demo_gkx_chain`） | 已发，待回 |

| 下游 | 给什么 |
|---|---|
| `KG-COMPLY-LOAD-L01` | 目标空间 `demo_gkx_chain`；只写 §1 的 Tag/Edge，不新增；每条带 `props.batch`；政策/服务机构先不写 |
| `KG-COMPLY-ACCEPT-L01` | 可验：技术点子图、关联实体、关键路径、中心性/社群、人才/机构合作网、产业链环节图；只能空态：政策、服务机构、企业股权/供应链。缺数返回空态或 501，不返回 0 或假图 |
| `KG-COMPLY-SDD-L01` | 空间已定，不再讨论切换；结构以 §1 为基线，接口出入参不得新增 Tag/Edge；技术点与七要素「技术」分开描述 |

**未闭合项（还没落实、等人回话的事）**

1. 燕大书面确认「合规层补 `demo_gkx_chain`」——确认函已发，回签后在此登记。
2. 合规空间是否必须独立（触发 §4 条件 1）。
3. M06 专利引用是否本期建（LOAD 定）。

---

## 6. 本文件不含什么

按交付范围，本文件只定结构与空间。以下内容不在本文件内：

- 展示系统 618 叶逐叶判定、图谱相关叶子盘点——归 `KG-YANDA-SCHEMA-REQ` 与 `KG-COMPLY-SDD-L01`；
- 图算法的指标定义与验收判据——归 `KG-COMPLY-ACCEPT-L01`；
- 各数据源的字段级可用性逐项对照——归 `KG-7ELEM-LOAD-PATH-L01`～`L06` 与本目录背景稿；
- 正式加工线 `gkx_chain` 的入图结构——归 WBS-07-00G / 00H。
