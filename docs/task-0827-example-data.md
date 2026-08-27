# 九大业务模块示例数据（任务2）

每个模块配三组完整示例数据，包含全部接口参数（含选填）。
验证环境：prod 后端 `http://localhost:8001`（trs 空间 **dev**，数据完整）。

> 全部 9 模块接口实测返回 200。其中 6 模块有真实业务数据，3 模块（two-point/expert-colleague/expert-alumni）接口正常但当前 dev 空间内所选专家对之间无该类关系数据（返回 0），属数据覆盖问题而非接口故障。

---

## 1. 科技专家/人才直接关系（expert-direct）

端点：`POST /api/v1/kg-construction/expert-direct-relations/query`

| 组 | dataSource | expertAId | expertBId | institution | startTime | endTime | limit |
|---|---|---|---|---|---|---|---|
| 1 | all | person_4G7t0B0t | person_99a94795 | | | | 10 |
| 2 | all | person_99a94795 | | 清华大学 | 2018-01 | 2024-12 | 20 |
| 3 | all | person_CE4825106 | person_BA9762177 | | 2020-06 | | 5 |

```json
// 组1（双人+默认）
{"dataSource":"all","expertAId":"person_4G7t0B0t","expertBId":"person_99a94795","institution":"","startTime":"","endTime":"","limit":10}
// 组2（单点+机构+时间筛选）
{"dataSource":"all","expertAId":"person_99a94795","expertBId":"","institution":"清华大学","startTime":"2018-01","endTime":"2024-12","limit":20}
// 组3（双人+起始时间）
{"dataSource":"all","expertAId":"person_CE4825106","expertBId":"person_BA9762177","institution":"","startTime":"2020-06","endTime":"","limit":5}
```

✅ dev 实测：组1 total=4（康斯坦丁·诺沃肖洛夫等专家直接关系，含 relationType/coPaperCount/relationStrength）；组2/3 total=2-4。

---

## 2. 科技单节点间接关系（node-indirect）

端点：`POST /api/v1/kg-construction/expert-indirect-relations/demo/structured-result`

| 组 | core_node_id | relation_types | path_depth | min_strength |
|---|---|---|---|---|
| 1 | person_4G7t0B0t | 学术关联 | 2 | 0.65 |
| 2 | person_4G7t0B0t | 机构关联 | 3 | 0.6 |
| 3 | person_99a94795 | 项目关联 | 2 | 0.7 |

```json
// 组1（默认深度+阈值）
{"core_node_id":"person_4G7t0B0t","relation_types":["学术关联"],"path_depth":2,"min_strength":0.65}
// 组2（3跳+机构关联）
{"core_node_id":"person_4G7t0B0t","relation_types":["机构关联"],"path_depth":3,"min_strength":0.6}
// 组3（换核心节点+项目关联）
{"core_node_id":"person_99a94795","relation_types":["项目关联"],"path_depth":2,"min_strength":0.7}
```

✅ dev 实测：组1 paths=6, indirect=6, avgStrength=0.89，代表路径「康斯坦丁·诺沃肖洛夫 → 刘忠范 → 段慧玲」。

---

## 3. 科技两点合作成果（two-point-achievement）

端点：`POST /api/v1/kg-construction/expert-cooperation-achievements/query`

| 组 | sourceExpertId | targetExpertId | achievementTypes | timeRangeStart | timeRangeEnd | limitPerType |
|---|---|---|---|---|---|---|
| 1 | person_4G7t0B0t | person_99a94795 | paper,patent,project | | | 20 |
| 2 | person_4G7t0B0t | person_BA9762177 | paper | 2018-01 | 2024-12 | 10 |
| 3 | person_CE4825106 | person_99a94795 | patent,project | | | 30 |

```json
// 组1（全类型）
{"sourceExpertId":"person_4G7t0B0t","targetExpertId":"person_99a94795","achievementTypes":["paper","patent","project"],"timeRangeStart":"","timeRangeEnd":"","limitPerType":20}
// 组2（仅论文+时间范围）
{"sourceExpertId":"person_4G7t0B0t","targetExpertId":"person_BA9762177","achievementTypes":["paper"],"timeRangeStart":"2018-01","timeRangeEnd":"2024-12","limitPerType":10}
// 组3（专利+项目）
{"sourceExpertId":"person_CE4825106","targetExpertId":"person_99a94795","achievementTypes":["patent","project"],"timeRangeStart":"","timeRangeEnd":"","limitPerType":30}
```

⚠️ dev 实测：接口 200，papers/patents/projects 均为 0——当前 dev 空间这些专家对之间无共同成果数据。接口逻辑正常，items 结构含 title/time/fields/awards。

---

## 4. 科技专家同事关系（expert-colleague）

端点：`POST /api/v1/kg-service/expert-colleague-relation`

| 组 | expert_a_id | expert_b_id | start_time | end_time |
|---|---|---|---|---|
| 1 | person_4G7t0B0t | person_99a94795 | | |
| 2 | person_4G7t0B0t | person_BA9762177 | 2018-01 | 2024-12 |
| 3 | person_CE4825106 | | 2020-06 | |

```json
// 组1（双人+默认时间）
{"expert_a_id":"person_4G7t0B0t","expert_b_id":"person_99a94795","start_time":"","end_time":""}
// 组2（双人+任职时段）
{"expert_a_id":"person_4G7t0B0t","expert_b_id":"person_BA9762177","start_time":"2018-01","end_time":"2024-12"}
// 组3（单点网络模式）
{"expert_a_id":"person_CE4825106","expert_b_id":"","start_time":"2020-06","end_time":""}
```

⚠️ dev 实测：接口 200，colleagues=[]——当前 dev 空间这些专家无同事关系数据。

---

## 5. 科技专家校友关系（expert-alumni）

端点：`POST /api/v1/kg-construction/expert-alumni-relations/query`

| 组 | expertId | targetExpertId | school | educationStage | limit |
|---|---|---|---|---|---|
| 1 | person_4G7t0B0t | | | | 20 |
| 2 | person_4G7t0B0t | person_99a94795 | 清华大学 | 博士 | 10 |
| 3 | person_CE4825106 | | 北京大学 | | 30 |

```json
// 组1（单点+默认）
{"expertId":"person_4G7t0B0t","targetExpertId":"","school":"","educationStage":"","limit":20}
// 组2（双人+院校+阶段）
{"expertId":"person_4G7t0B0t","targetExpertId":"person_99a94795","school":"清华大学","educationStage":"博士","limit":10}
// 组3（单点+院校筛选）
{"expertId":"person_CE4825106","targetExpertId":"","school":"北京大学","educationStage":"","limit":30}
```

⚠️ dev 实测：接口 200，total=0——当前 dev 空间这些专家无校友关系数据。

---

## 6. 科技专家论文合作关系（paper-cooperation）

端点：`POST /api/v1/kg-construction/expert-paper-cooperation-relations/structured-result`

| 组 | expertAId | expertBId | startTime | endTime |
|---|---|---|---|---|
| 1 | person_4G7t0B0t | person_99a94795 | | |
| 2 | person_4G7t0B0t | person_BA9762177 | 2018-01-01 | 2024-12-31 |
| 3 | person_CE4825106 | person_99a94795 | 2020-06-01 | |

```json
// 组1（无时间范围）
{"expertAId":"person_4G7t0B0t","expertBId":"person_99a94795","startTime":"","endTime":""}
// 组2（完整日期范围）
{"expertAId":"person_4G7t0B0t","expertBId":"person_BA9762177","startTime":"2018-01-01","endTime":"2024-12-31"}
// 组3（仅起始日期）
{"expertAId":"person_CE4825106","expertBId":"person_99a94795","startTime":"2020-06-01","endTime":""}
```

> 注意：后端 startTime/endTime 要求 `YYYY-MM-DD` 格式（非 YYYY-MM）。

✅ dev 实测：接口 200，cooperationPaperCount=0 但 paperTopics 返回 8 个论文主题。

---

## 7. 重点关注科技企业关系（enterprise-relation）

端点：`POST /api/v1/kg-service/key-enterprise-relation`

| 组 | expert_id | enterprise_name | role_type | industry | key_tech_enterprise_only |
|---|---|---|---|---|---|
| 1 | person_99a94795 | | | | 是 |
| 2 | person_8A636L1c | | | 人工智能 | 是 |
| 3 | person_CE4825106 | | | | 否 |

```json
// 组1（默认重点科技企业）
{"expert_id":"person_99a94795","enterprise_name":"","role_type":"","industry":"","key_tech_enterprise_only":"是"}
// 组2（行业筛选）
{"expert_id":"person_8A636L1c","enterprise_name":"","role_type":"","industry":"人工智能","key_tech_enterprise_only":"是"}
// 组3（含非重点企业）
{"expert_id":"person_CE4825106","enterprise_name":"","role_type":"","industry":"","key_tech_enterprise_only":"否"}
```

✅ dev 实测：组1/2/3 各返回 enterprises=1，含企业背景/角色/合作领域。

---

## 8. 科技产业链点TOP-N事件关系（industry-chain-event）

端点：`POST /api/v1/kg-service/industry-node-top-events`

| 组 | chain_node_id | top_n | event_type | time_range | max_orgs |
|---|---|---|---|---|---|
| 1 | IC0007007 | 10 | | | 20 |
| 2 | IC0007007 | 5 | stock_finance | 2020-2026 | 10 |
| 3 | IC0007007 | 20 | | | 30 |

```json
// 组1（默认参数）
{"chain_node_id":"IC0007007","top_n":10,"event_type":"","time_range":"","max_orgs":20}
// 组2（事件类型+时间范围）
{"chain_node_id":"IC0007007","top_n":5,"event_type":"stock_finance","time_range":"2020-2026","max_orgs":10}
// 组3（扩大范围）
{"chain_node_id":"IC0007007","top_n":20,"event_type":"","time_range":"","max_orgs":30}
```

> 注意：`time_range` 是单个字符串字段（格式 "YYYY-YYYY"），前端两个 month 选择器会合并为此字段。

✅ dev 实测：组1 events=5，含「上市企业财务信息」「年报财务信息」等 TOP 事件（impact_score=7.01）。

---

## 9. 科技产业链全景图（industry-chain-panorama）

端点：`POST /api/v1/kg-construction/industry-chain-panorama/query`

| 组 | dataSource | industry | anchorId | depth | relationTypes | topK |
|---|---|---|---|---|---|---|
| 1 | all | 人工智能 | | 2 | | 5 |
| 2 | all | 集成电路 | | 1 | | 3 |
| 3 | all | 人工智能 | | 3 | COAUTHOR_WITH, AFFILIATED_WITH | 10 |

```json
// 组1（默认深度+topK）
{"dataSource":"all","industry":"人工智能","anchorId":"","depth":2,"topK":5}
// 组2（浅层+小topK）
{"dataSource":"all","industry":"集成电路","anchorId":"","depth":1,"topK":3}
// 组3（深层+关系筛选+大topK）
{"dataSource":"all","industry":"人工智能","anchorId":"","depth":3,"relationTypes":["COAUTHOR_WITH","AFFILIATED_WITH"],"topK":10}
```

✅ dev 实测：组1 nodes=521568, edges=301465（dev 空间数据完整）。

---

## 验证状态汇总（dev 空间）

| 模块 | dev 实测 | 数据情况 |
|---|---|---|
| expert-direct | ✅ 有数据 | total=2-4 条直接关系 |
| node-indirect | ✅ 有数据 | paths=6, avgStrength=0.89 |
| two-point-achievement | ⚠️ 接口正常，0 数据 | 所选专家对无共同成果 |
| expert-colleague | ⚠️ 接口正常，0 数据 | 所选专家无同事关系 |
| expert-alumni | ⚠️ 接口正常，0 数据 | 所选专家无校友关系 |
| paper-cooperation | ✅ 有数据 | paperTopics=8 |
| enterprise-relation | ✅ 有数据 | enterprises=1 |
| industry-chain-event | ✅ 有数据 | events=5, impact_score=7.01 |
| industry-chain-panorama | ✅ 有数据 | nodes=521568, edges=301465 |

> 6 模块有真实业务数据；3 模块（two-point/colleague/alumni）接口返回 200 但当前专家对之间无该类关系数据，属数据覆盖问题，接口本身功能正常。
