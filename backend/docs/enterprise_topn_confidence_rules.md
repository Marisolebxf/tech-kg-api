# 重点科技企业关系 / 产业链点TOP-N事件 —— 置信度判断规则说明

> 对应 0907 任务第 7 条：列出两个模块的关系/实体置信度判断规则，并解释"暂无"的情况。
> 老师核对时可直接对照 `service/tech_enterprise_relation_business.py` 的 `COOPERATION_CONFIDENCE`
> 与 `service/industry_node_top_events_business.py` 的 `EVENT_CONFIDENCE / RISK_LEVEL_CONFIDENCE`。

## 一、重点关注科技企业关系（POST /api/v1/kg-service/key-enterprise-relation）

### 1. 关系置信度（每条 relation 的 confidence 字段）

置信度定义在**专家↔企业关系**上，按关系构成方式赋值（图上直连证据越短越可信）：

| 关系类型（cooperation_type） | 置信度 | 判断依据 |
|---|---|---|
| governance（治理类：高管任职/法人代表/实际控制/受益所有/股东持股/任职） | **0.9** | Person→Organization 图上直连边（EXECUTIVE_OF 等 6 种），一跳直达，证据最强 |
| project_cooperation（项目合作） | **0.8** | Person→Project→Organization 两跳路径（HAS_PARTICIPANT/LEADS + PARTICIPATES_IN/FUNDED_BY），路径中转 |
| patent_cooperation（专利合作） | **0.8** | Person→Patent→Organization 两跳路径（INVENTED_BY + APPLIED_BY），路径中转 |
| 其他未识别类型 | 0.7 | 兜底默认值 |

### 2. 综合置信度（响应顶层 confidence 字段）

= 全部返回关系置信度的**最大值**（`max(relations[].confidence)`）。
前端摘要行"综合置信度"展示该值并注明口径。

### 3. 实体置信度：不适用（显示"暂无"）

专家、企业等**实体本身没有置信度概念**——置信度刻画的是"关系成立的可信程度"，
不是实体真实性的度量。因此实体列表/实体详情中置信度一栏显示"暂无"，属预期行为，
不是数据缺失。关系列表、关系详情中的置信度为上述第 1 节的真实值。

## 二、科技产业链点TOP-N事件关系（POST /api/v1/kg-service/industry-node-top-events）

### 1. 事件置信度（每条 top_event 的 confidence 字段）

按事件类型赋值（证据类型风险等级越高越可信，资讯类无结构化佐证最低）：

| 事件类型 | 置信度 | 说明 |
|---|---|---|
| bankruptcy / zhixing / shixin / tax_punish / judicial_case / illegal / equity_freeze / judicial_sale / abnormal / pledge / chattel | **0.9** | 风险类：来自司法/监管结构化数据表 |
| financing / stock_finance / annual_finance | **0.85** | 财务类：来自财务结构化数据 |
| bid | **0.8** | 招投标：结构化公示数据 |
| news | 0.7 | 资讯：媒体稿，无结构化佐证 |
| change_record | 0.7 | 工商变更 |
| recruit | 0.6 | 招聘信息 |
| 其他未识别类型 | 0.7 | 兜底默认值 |

### 2. 综合置信度（响应顶层 confidence 字段）

按 TOP 事件池判定出的**风险等级**赋值：高 → **0.9**，中 → **0.75**，低 → **0.6**。
风险等级判定：TOP 事件含任一风险类 → 高；含融资/财务类 → 中；其余 → 低。

### 3. 实体置信度

- 产业链节点、企业、专家：优先展示图节点 `confidence`；缺失时统一调用实体置信度服务按入图证据计算并尽力写回。
- 统一权重为 DWD 来源 **0.40**、稳定 ID **0.20**、外部 ID/统一信用代码 **0.10**、展示名称 **0.20**、位置/时间/重要级别等支撑属性 **0.10**；完全无证据时兜底为 **0.80**。
- 事件节点（图上的“事件实体”）：展示第 1 节的事件置信度。

`IC0007007` 来自 `dwd_industry_chain_info`，具有稳定 `node_id`、节点名称及重要级别属性，回退置信度为 **0.90**。

## 三、影响力评分与置信度的区别（TOP-N 排序用）

TOP-N 事件排序依据 `impact_score`（影响力评分），与置信度是两个独立维度：

- **impact_score**（越大越排前）= 事件类型权重 × (1 + log10(金额)/10) × 时间新鲜度 × (1 + 企业链上得分/100)
- **confidence** = 该事件来源数据的可信程度（上表）

前端图上事件节点原用 `impact_score/10` 冒充置信度展示，本次已改为真实事件置信度；
影响力评分保留在"评分"展示位（节点副标题/摘要"影响力排名"行）。
