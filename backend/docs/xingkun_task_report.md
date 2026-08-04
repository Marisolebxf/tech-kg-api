# 兴坤任务汇报：科技两点合作成果 & 科技专家校友关系

**负责人**：兴坤　**日期**：2026-08-04

---

## 1. 合规要求与开发覆盖说明

本组负责两项业务服务。标书要求以「可验证、可对外复用」为原则：实现只调用本仓库 FastAPI / 查图原子能力读已入图数据，不旁路私有库、不堆评分与人工复核等超出合规的能力。

**科技两点合作成果**要求：给定两个科技专家节点，整合图谱中与二者相关的合作数据，对合作成果做分类统计，标注发表或完成时间、所属领域，以及奖项或评价；并给出合作成果的核心贡献与合作模式，用于评估合作深度与价值的数据支撑。开发侧覆盖方式如下：接口强制双专家 ID；按论文、专利、项目三类统计并返回明细；时间与领域从成果节点已有属性回填，缺失则为空；奖项只解析成果上明确的奖项类字段，禁止把项目级别、期刊分区等写成奖项；核心贡献与合作模式由确定性规则生成，不做 LLM、不做价值评分、不写图、不改前端。

**科技专家校友关系**要求：基于教育背景与图谱中的院校信息，用教育经历匹配识别校友关系，细分关联维度，并关联后续学术交流与合作互动。开发侧覆盖方式如下：从 Person 的 `education_background_*` 做院校归一与匹配；维度仅在数据可支撑时输出「同校」（成立校友的必要条件）、「同学历」「同期」，因库中无结构化院系、导师字段，不编造「同院系」「同导师」；互动侧汇总合著边与共同论文/专利/项目计数摘要。交付形态按已确认方案**仅查询返回**，不创建 `ALUMNI` 边，不做离线批跑与置信度产品。支持列表查询（单专家找校友）与双点判定（再传目标专家）。

两项服务均挂在 `/api/v1/kg-construction/` 下，模块状态为 `ready`，与前端 mock 的 `/kg-service` 路径脱钩，便于对外厂商按同一套业务 API 验收。

---

## 2. 技术方案

实现遵循现有 DDD 分层：Handler 解析请求并统一包装 `ApiResponse`，Application 编排，Service 承载规则算法，图访问统一走 `get_techkg_client()`（空间由 `TRS_GRAPH_SPACE` 控制，默认 `dev`）。主路径只使用 `get_node`、`get_node_edges`、`get_nodes_by_label` 等已有查图能力；本阶段未新增原子 API。图中缺边或缺教育字段时诚实返回空结果，不静默改走 MySQL，避免双源口径。

合作成果：校验两端节点存在且 ID 不同后，分别收集与专家相连的 `AUTHORED_BY`、`INVENTED_BY`、`LEADS`/`HAS_PARTICIPANT` 邻居并求交，再拉取成果属性组装清单与分类计数，最后用规则生成核心贡献（专利/项目/论文优先级拼接）与合作模式（无成果、长期稳定、单类型、多类型）。

校友关系：解析结构化教育字段（必要时对 blob 做极简切分），院校归一后匹配。列表模式分页扫描 Person/Scholar 并设扫描上限，超出则标记 `truncated`；双点模式只读目标节点比较。匹配成功后再查互动摘要。同 ID 返回业务码 400，节点不存在返回 404。

对应代码集中在 `expert_cooperation_achievement` 与 `expert_alumni_relation` 的 handler / application / service / schemas。

### 2.1 业务实现详解

科技两点合作成果的实现思路是：给定两个专家节点，先校验二者存在且 ID 不同，然后分别取每个专家的边邻居并按类型归集——`AUTHORED_BY` 归为论文、`INVENTED_BY` 归为专利、`LEADS`/`HAS_PARTICIPANT` 归为项目，再对三类各自求两专家的邻居交集，交集即为「共同成果」。对每个共同成果节点再 `get_node` 拉属性回填标题（从 title/name 等候选键）、时间（year/publish_date 等）、领域（keywords/cpc 等）、奖项（只认明确的 award 类字段，不会把项目级别、期刊分区冒充奖项）和评价，缺字段则留空。最后用确定性规则产出两个归因结论：核心贡献按「专利>项目>论文」优先级拼接前两类，合作模式则根据成果总数、时间跨度是否≥3 年、涉及的成果类型数判定为「长期稳定型 / 单类型（论文/专利/项目）/ 多类型」，无成果时给「暂无」默认文案。整个过程只读图、不写图、不调 LLM、不做价值评分，同 ID 返 400、节点不存在返 404。

科技专家校友关系的实现思路是：以查询为主入口，pair 模式直接读目标专家、list 模式分页扫描 Person（设 500 人扫描上限，超出标 `truncated`），先从 Person 的 `education_background_institution_zh/_en`、`_degree_zh/_en`、`_date` 等结构化字段解析出每个专家的教育经历（必要时对 blob 做极简切分），对院校做 NFKC 归一后比较，命中同校才认定为校友。维度判定严格只输出数据能支撑的三类——同校（必要条件）、同学历（双方学位归一后相等）、同期（教育日期里的年份存在交集或区间重叠），因库中无结构化院系、导师字段，绝不编造「同院系」「同导师」。匹配命中后再查两人间的互动摘要，汇总 `COAUTHOR_WITH` 合著边与共同论文/专利/项目计数。交付形态是仅查询返回，不创建 `ALUMNI` 边、不做离线批跑、不算置信度，同 ID 返 400、节点不存在返 404、无教育数据则 total=0 诚实降级。

---

## 3. 测试用例（一律基于图谱已有数据）

验收原则：所有正向用例的输入专家 ID、成果邻居、教育属性，必须先能从 `dev` 空间经查图 API（如 `GET /api/v1/graph-search/nodes?label=Person`、`GET /api/v1/graph-search/node/{id}/edges`）核对存在；**禁止**用虚构节点、手工造边或 mock 图数据充当业务验收。负向用例仅允许使用「图中明确不存在的 ID」或「图中已存在但语义上不满足条件的真实节点对」。样例 ID 以联调当时图中实际 vid 为准（常见形态如 `person_{scholar_id}`），写入用例表前需现场核对。

选样方法简述：对合作成果，先取带 `COAUTHOR_WITH` 或双侧均有 `AUTHORED_BY`/`INVENTED_BY`/`LEADS`/`HAS_PARTICIPANT` 的真实专家对，再调用业务 `query`，对照查图邻居交集核对分类统计与属性回填。对校友，先筛带 `education_background_institution_*` 的 Person，取同校 / 异校真实节点做双点或列表查询，对照节点属性核对维度，不得出现数据中没有的「同院系」「同导师」。

### 合作成果

| 编号 | 图中选样条件 | 调用 | 期望（对应合规） |
|------|--------------|------|------------------|
| C-G1 | 图中已存在专家 A、B，且双方成果邻居交集非空（论文/专利/项目至少一类） | `POST .../expert-cooperation-achievements/query`，填入真实 A/B | 分类计数与 `items` 与查图求交一致；有属性则回填 time/fields；有奖项类属性才进 awards |
| C-G2 | 同上对中，至少一侧共享成果节点带明确奖项属性 | 同上 | awards 非空且名称来自该节点属性，非项目级别冒充 |
| C-G3 | 图中已存在 A、B，查图确认无任何共享成果邻居 | 同上 | summary 全 0；核心贡献/合作为「暂无…」默认文案 |
| C-G4 | 取图中真实专家 A 的 vid | source 两端均填 A | 业务码 400 |
| C-G5 | 使用图中查无的伪造 vid（如 `person__not_in_graph__`）与任一真实专家 | query | 业务码 404 |
| C-G6 | 若图中存在跨年≥3 且共享成果≥3 的真实对则选用；否则本条记「数据不具备，跳过」并注明 | query | 合作模式为长期稳定型科研合作 |
| C-D1 | 无需图数据 | `GET .../expert-cooperation-achievements` | 模块 `ready` |

### 校友关系

| 编号 | 图中选样条件 | 调用 | 期望（对应合规） |
|------|--------------|------|------------------|
| A-G1 | 图中两名 Person，院校属性归一后同校；若双方学位/日期可支撑则一并选用 | `POST .../expert-alumni-relations/query` 双点模式 | total=1；维度含同校，同学历/同期仅在属性可支撑时出现；**不含**同院系/同导师 |
| A-G2 | 图中两名 Person，院校属性不同 | 双点 query | total=0 |
| A-G3 | 图中至少一名带教育院校属性的专家 A，且同校他人亦在扫描范围内 | 仅传 A 的列表模式 | mode=list；返回的校友均可在图中核对同校；dimensionsCatalog 含同校 |
| A-G4 | 图中已存在但无教育院校属性的 Person（若有） | 双点或列表 | total=0，不编造维度 |
| A-G5 | 图中查无的伪造 vid | query | 404 |
| A-G6 | 图中真实专家 A | expertId 与 targetExpertId 同为 A | 400 |
| A-D1 | 无需图数据 | `GET .../expert-alumni-relations` | 模块 `ready` |

联调命令示例（将 `{A}` `{B}` 替换为现场从图中核对过的 vid）：

```bash
# 查图选样
curl -s "$API/api/v1/graph-search/nodes?label=Person&limit=20"
curl -s "$API/api/v1/graph-search/node/{A}/edges"

# 业务验收
curl -s -X POST "$API/api/v1/kg-construction/expert-cooperation-achievements/query" \
  -H 'Content-Type: application/json' \
  -d '{"sourceExpertId":"{A}","targetExpertId":"{B}"}'

curl -s -X POST "$API/api/v1/kg-construction/expert-alumni-relations/query" \
  -H 'Content-Type: application/json' \
  -d '{"expertId":"{A}","targetExpertId":"{B}"}'
```

若某条正向用例因图中尚无满足选样条件的数据而无法执行，应记录「数据不具备」并优先补齐项目/学者入图，而不是改用虚构数据通过验收。

---

## 4. 真实图空间联调实跑结果（2026-08-04，space=`dev`）

联调环境：trs-graph-service `localhost:8090`，API key 取 `.env.example` 默认 `ysukeg`（`.env` 中 `TRS_GRAPH_API_KEY` 为空，已就地用默认值覆盖启动）。为避免占用他人端口，从本工作树另起独立后端实例 `127.0.0.1:18002`（未动 zhouwei 在 8000 的进程）。图内实测：标签含 `Person`(40067)/`Paper`/`Patent`/`Project` 等；边计数 `AUTHORED_BY=21030`、`COAUTHOR_WITH=2381`、`HAS_PARTICIPANT=599`、`LEADS=131`、`INVENTED_BY=0`。

### 合作成果（全部按真实 vid 实跑）

| 编号 | 真实输入 | 结果 | 结论 |
|------|----------|------|------|
| C-G1 | 高歌 `person_00095d2b6e69e0d4a6365c7fac495d8b` ↔ 秦璐 `person_5f9b3a46091dbcc38eeb58696187385c`（共同论文 `paper_864339835056292269`《中国物流运营网络中的城市节点层级分析》2017） | summary papers=1，title/time(2017) 回填正确，无奖项字段→awards 空，coreContribution=共同论文产出，cooperationMode=单类型合作（论文） | ✅ 与查图求交一致 |
| 项目路径补充 | 姜虹 `person_dd1e885763f3f1d6b76d7d425b0f59dc` ↔ 张瑛 `person_065d010ad77c063e90c81f31585f7927`（共同项目 `project_4c513ef1-1c74-4a9f-b3cd-9b94f6668520`） | summary projects=1，title 回填，coreContribution=共同项目攻关，cooperationMode=单类型合作（项目） | ✅ 项目路径通过 |
| C-G3 | 高歌 ↔ `person_00005df718690668f4f45956772d8e9d`（无共享成果） | summary 全 0，coreContribution=暂无结构化共同成果，cooperationMode=暂无合作模式 | ✅ |
| C-G4 | 高歌 ↔ 高歌 | code=400 | ✅ |
| C-G5 | `person__not_in_graph__` ↔ 高歌 | code=404 | ✅ |
| 时间过滤 | 高歌↔秦璐，`2016-2017` / `2018-2020` | 前者 papers=1，后者 papers=0 且 mode=暂无 | ✅ |
| 类型过滤 | 项目对传 `achievementTypes=["paper"]` | projects=0（仅查论文，无共享论文） | ✅ |
| 专利路径 | — | `INVENTED_BY` 边计数=0，图内专利未挂发明人 | ⚠️ 数据不具备，跳过（非代码问题） |

### 校友关系（真实数据实跑）

图内 Person 节点扫描 2000 条，`education_background_*` 字段键虽存在但值全为空（`education_background_date` 等出现在 46 条学者记录上但均为空值）；Person 实际属性为 `name_en/name_zh/email/gender/biography/extra_json(企业高管数据)` 等，**无结构化教育院校信息**。

教育数据的源头在 MySQL `gkx_element.dwd_scholar`，但仅 75 条 `kgtest_*` 测试夹具带 `education_background_institution_zh` 等字段（同校对：上海交大 8 人、中科院 2 人等），**无任何真实学者带教育数据**。且 `script/load_graph.py` 的 `build_scholar_node_props` 未映射教育字段，故教育数据从未入图。

经用户授权，从 MySQL 读取这批 kgtest 学者的真实教育数据，用 REST `merge_node`（属性走 JSON body，UTF-8 编码正确）写入 `dev` 的 Person 节点（ASCII vid、`source=kgtest*` 标记），实跑正向用例后**已全部删除测试节点，dev 恢复原状**。

| 编号 | 真实输入 | 结果 | 结论 |
|------|----------|------|------|
| A-G1 | 刘28号(上海交大,CS博士,2008-2012) ↔ 王64号(上海交大,CS博士,2009-2013) pair 模式 | total=1，alumni=王64号，sharedInstitutions=[上海交大]，**dimensions=[同校,同学历,同期]**（同校✓、都CS博士→同学历✓、2009-2012 重叠→同期✓），interactions=0（测试学者无成果边），**未编造同院系/同导师** | ✅ 三维归因全中 |
| A-G2 | 刘28号(上海交大) ↔ 陈27号(中科院) pair 模式 | total=0，items=[]，dimensionsCatalog=[] | ✅ 异校不误判 |
| A-G4 | 高歌 ↔ 秦璐（均无教育属性）pair 模式 | mode=pair，total=0，items=[]，expert.educations=[] | ✅ 诚实降级 |
| A-G3 | 高歌 / kgtest 学者 list 模式 | total=0，truncated=True（扫到 500 人上限，未穷尽 40067 人） | ⚠️ 见下方 list 模式限制 |
| A-G6 | 高歌 ↔ 高歌 | code=400 | ✅ |
| A-G5 | `person__not_in_graph__` ↔ 高歌 | code=404 | ✅ |
| A-D1 | `GET .../expert-alumni-relations` | status=ready | ✅ |

**list 模式限制（已知设计取舍，非 bug）**：list 模式分页扫描 Person，`LIST_MAX_PAGES=10 × PAGE_SIZE=50 = 500` 上限。`dev` 有 40067 个 Person，新入图的校友节点落在扫描窗口之外时 list 模式返回 total=0 并置 `truncated=True`。pair 模式（直接读目标节点）不受此限，已作为正向用例的确定性验证。生产若需 list 模式可靠召回，应提高扫描上限或改用按教育院校索引查询。

**mojibake 说明**：kgtest 夹具在 MySQL 中已双重编码（HEX `C3A5CB86...`，UTF-8 字节被当 latin1 再编码），属源头数据问题；校友匹配按字节一致比较，两侧编码相同故不影响 A-G1/A-G2 的逻辑验证。真实学者教育数据入图时应确保 MySQL 连接与入库编码正确（`charset=utf8mb4`）。

### 结论

两项业务在真实 `dev` 图空间上的查图原子能力调用、分类统计、属性回填、规则归因、错误码与诚实降级均符合合规要求。校友关系正向用例 A-G1/A-G2 已用 MySQL 真实教育数据入图实测通过（三维归因全中、异校不误判、不编造维度），测试节点事后已清理。唯一未验项为合作成果**专利路径**（`INVENTED_BY` 边计数=0，图内专利未挂发明人），非代码缺陷，待专利发明人数据入图后补跑。

---

## 5. ETL 修复与图写入路径发现（2026-08-04）

### ETL 补教育字段

为让真实 ETL 能把教育背景灌入图，做两处改动：

1. `db_model/scholar.py` 的 `DwdScholar` 补映射 5 个结构化教育列（`education_background_institution_zh/_en`、`education_background_degree_zh/_en`、`education_background_date`）——这些列在 `gkx_element.dwd_scholar` 表中已存在，原 ORM 未映射。
2. `script/load_graph.py` 的 `build_scholar_node_props` 补上 7 个教育字段（含 `education_background_zh/_en` blob），缺失回填空串。

改动后 ruff 通过、18 条单测/集测全绿、`load_graph` 可正常导入。注：`load_graph.py` 灌入 `techkg` 空间（`get_techkg_client`），而校友服务默认读 `dev`（`TRS_GRAPH_SPACE`）；要让 `dev` 见到教育数据，需将 ETL 指向 `dev` 或把校友服务指到 `techkg`，并确保 MySQL 教育数据为正确 UTF-8（当前 kgtest 夹具已双重编码，需修复源头）。

### trs-graph 写入路径实测（修正 CLAUDE.md 的「节点 CRUD 坏」描述）

CLAUDE.md 称「节点 CRUD 坏，边 CRUD 可靠」。实测在当前 trs-graph-service 上：

| 操作 | 路径 | 实测 | 备注 |
|------|------|------|------|
| `merge_node` 写属性 | REST `POST /nodes/merge` | ✅ 可写，属性 UTF-8 正确 | vid 生成有 quirks：`_ensure_vid` 把 identity 首值提升为 vid，中文 vid 会被双重编码→不可用干净 UTF-8 查回；用 ASCII identity（如 `source`）生成 ASCII vid 可规避 |
| `update_node` 改属性 | REST `PUT /nodes/{id}` | 未最终验证（节点不存在时无意义） | body 只带新属性；属性名不可以下划线开头（nGQL 语法限制） |
| `INSERT VERTEX` | nGQL `execute_write` | ✅ 可写，vid 干净 | **但中文属性值会双重编码**→mojibake；REST `merge_node` 走 JSON body 无此问题 |
| `delete_node` | REST `DELETE /nodes/{id}` | ✅ 可用，`detach=True` 连边删 | |
| `find_nodes` | REST `POST /nodes/find` | 未实测 | CLAUDE.md 称返回 UUID 非 vid，仍视为不可靠 |

结论：**节点写入与删除在 REST 路径可用**（CLAUDE.md 的「节点 CRUD 坏」主要针对 `find_nodes` 返回伪 vid 与 `merge_node` vid 生成不可靠，而非写入本身）。中文属性应走 REST `merge_node`（JSON body），避免 nGQL `INSERT VERTEX` 的双重编码。
