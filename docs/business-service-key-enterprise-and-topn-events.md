# 重点关注科技企业关系 & 产业链点 TOP-N 事件 业务实现说明

本文档说明「九大业务」中的两个业务服务——**重点关注科技企业关系**（`key-enterprise-relation`）与**科技产业链点 TOP-N 事件关系**（`industry-node-top-events`）——的前后端实现。两个业务共同遵循一条硬约束：

> 业务编排层**只调用 FastAPI 后端暴露的 API**（`/api/v1/graph-search/*` 查图），**不直连 NebulaGraph、不直连图 SDK、不直连 MySQL**。

涉及的图空间固定为 `dev`。

---

## 1. 新增原子能力：filtered-subgraph

两个业务都依赖新增的 `GET /graph-search/filtered-subgraph/{node_id}` 端点（`biz/handler/graph_search.py`）：

- 参数：`edge_types`（逗号分隔多边类型）、`depth`、`direction`、`limit`、`space`。
- 与 `/subgraph` 的区别：支持**多边类型过滤**，每种边类型单独查 NebulaGraph，不互相占 limit 名额，不捞论文/合作者/引用等无关数据。
- 返回与 `/subgraph` 相同的 `{nodes, edges}` 结构。

---

## 2. 涉及文件

### 后端

| 层 | 重点关注科技企业关系 | 产业链点 TOP-N 事件 |
| --- | --- | --- |
| schemas | `biz/schemas/tech_enterprise_relation_business.py` | `biz/schemas/industry_node_top_events_business.py` |
| handler | `biz/handler/tech_enterprise_relation_business.py` | `biz/handler/industry_node_top_events_business.py` |
| service | `service/tech_enterprise_relation_business.py` | `service/industry_node_top_events_business.py` |
| router | `biz/router/register.py`（挂载于 `/api/v1/kg-service`） | 同左 |
| 原子 API | `biz/handler/graph_search.py`（新增 `filtered-subgraph` 端点） | 同左 |

端点：`POST /api/v1/kg-service/key-enterprise-relation`、`POST /api/v1/kg-service/industry-node-top-events`，均附带 `GET` describe。

两个 service 用 `httpx.AsyncClient` 调本机 FastAPI 的 `graph-search` 端点（`BUSINESS_API_BASE`，默认 `http://127.0.0.1:8000`），**不直连图、不直连 MySQL**。

### 前端

| 文件 | 作用 |
| --- | --- |
| `frontend/src/api/kgService.ts` | `invokeKgService(endpoint, params)`：走 `http.post`（baseURL `/api`，dev 由 vite 代理）。 |
| `frontend/src/views/business-service/service-modules.ts` | 业务模块契约，含真实可用的 `requestExample`。 |
| `frontend/src/views/business-service/components/BusinessServiceAlgorithmPanel.vue` | `handleRun()` 调真实 API，`buildLiveGraph()` 渲染图，`buildLiveSummary()` 渲染结果详情，溯源回退渲染 `evidence[]`。 |
| `frontend/vite.config.ts` | `host='0.0.0.0'`、`allowedHosts=true`，便于经跳板机/端口转发访问。 |

### ETL 脚本（数据准备）

| 脚本 | 作用 |
| --- | --- |
| `script/industry_chain_etl/load_industry_chain_graph.py` | 产业链图谱 ETL：建 IndustryChain/IndustryNode tag + HAS_NODE/CHILD_OF/DOWNSTREAM_OF/COVERS_CHAIN edge，从 gkx_element 灌入 180 链节点 + 374 企业关联 + 476 产业资讯。 |
| `script/workflow/paper_journal_chain_etl.py` | 工作流封装脚本（任务二）：论文实体+关系+产业链 ETL 合一，支持增量更新，入口 `workflow(payload)`。 |

---

## 3. 重点关注科技企业关系（key-enterprise-relation）

### 3.1 业务目标

围绕一个**科技专家/人才**，聚合其与**重点关注科技企业**之间的全部关联关系，输出可解释的「专家 ↔ 企业」关系清单，含合作模式、角色定位、角色层级、合作时间、企业背景。

### 3.2 三类关系来源

通过 **filtered-subgraph(depth=2, 12 种边类型)** 一次拿到专家 2 跳内全部业务相关边（不捞论文/合作者/引用），在 Python 内存里分类：

| 关系类型 | 图路径 | 合作模式 | 合作时间来源 |
| --- | --- | --- | --- |
| governance 治理 | `Person --[EXECUTIVE_OF/LEGAL_REP_OF/ACTUAL_CONTROLLER_OF/BENEFICIAL_OWNER_OF/SHAREHOLDER_OF/AFFILIATED_WITH]--> Organization` | 边类型映射 | `AFFILIATED_WITH` 取专家 `work_experience_date`，其余无 |
| project_cooperation 项目合作 | `Person --[HAS_PARTICIPANT/LEADS]--> Project --[PARTICIPATES_IN/FUNDED_BY]--> Organization` | 项目合作 | `Project.research_period` / `approval_time` |
| patent_cooperation 专利合作 | `Person --[INVENTED_BY]--> Patent --[APPLIED_BY]--> Organization` | 专利合作 | `Patent.application_date` |

角色层级：`董事长/CEO/法人/控制人/受益/股东 → L1`，`CTO/首席/总工程师/总监/副总 → L2`，`工程师/技术员/主管/经理 → L3`。

重点科技企业筛选：排除高校/研究院/医院/政府/MOCK；命中上市状态/股票代码/公司类名称才保留。支持 `enterprise_name` / `role_type` / `industry` 过滤。

### 3.3 流程图

```mermaid
flowchart TD
    A["前端 handleRun()<br/>invokeKgService(key-enterprise-relation, params)"] --> B["POST /api/v1/kg-service/key-enterprise-relation"]
    B --> C["KeyEnterpriseRelationService.run"]
    C --> D["httpx GET /graph-search/filtered-subgraph/{expert_id}<br/>edge_types=12种, depth=2, space=dev"]
    D --> E["拿到专家 2 跳内业务相关 nodes+edges<br/>（不含论文/合作者/引用）"]
    E --> F["构建 node_props / node_labels / adj 邻接表"]
    F --> G1["governance：expert 直连 Organization 边"]
    F --> G2["项目合作：expert→Project→Organization"]
    F --> G3["专利合作：expert→Patent→Organization"]
    G1 --> H["汇总 EnterpriseRelationItem 列表"]
    G2 --> H
    G3 --> H
    H --> I["过滤：重点科技企业 + enterprise_name/role_type/industry"]
    I --> J["回填 expert_name / enterprises / roles / cooperation_fields / evidence"]
    J --> K["前端 buildLiveGraph + buildLiveSummary 渲染"]
```

---

## 4. 产业链点 TOP-N 事件关系（industry-node-top-events）

### 4.1 业务目标

给定一个**产业链节点**（如 `IC0007007`），找出该节点下重点企业的**高风险/高影响力事件**并做 TOP-N 排名，输出「事件 ↔ 企业 ↔ 专家」关联，给出风险等级。

### 4.2 数据来源（纯 graph-search API，不直连 MySQL）

产业链节点/企业/事件/专家全部从 dev 图空间经 graph-search API 查：

1. `GET /graph-search/filtered-subgraph/{node_vid}?edge_types=BELONGS_TO_NODE,HAS_NODE&depth=1` → 链节点信息 + 关联企业（BELONGS_TO_NODE，带 chain_score）+ 产业链名（HAS_NODE→IndustryChain）。
2. 按 chain_score 降序取 top `max_orgs` 家企业。
3. 每个企业 `GET /graph-search/filtered-subgraph/{org_id}?edge_types=INVOLVED_IN&depth=1` → 事件。
4. TOP 事件企业 `GET /graph-search/node/{org_id}/edges?edge_type=EXECUTIVE_OF&direction=in` → 专家。

> 产业链节点数据由 `script/industry_chain_etl/load_industry_chain_graph.py` 从 gkx_element 灌入 dev 图空间（IndustryNode tag + BELONGS_TO_NODE/HAS_NODE/CHILD_OF/DOWNSTREAM_OF 边）。

### 4.3 影响力评分

```
impact_score = EVENT_WEIGHT(event_type)        # 风险类 3.0 / 财务类 2.0 / 其它 1.0~1.5
             × (1 + log10(amount+1)/10)        # 金额因子
             × recency                         # 按年衰减，2026≈1.0
             × (1 + chain_score/100)           # 企业在链上的强度
```

按分数降序取 `top_n`。风险等级：TOP 事件含风险类→高，含财务类→中，否则低。

### 4.4 流程图

```mermaid
flowchart TD
    A["前端 handleRun()<br/>invokeKgService(industry-node-top-events, params)"] --> B["POST /api/v1/kg-service/industry-node-top-events"]
    B --> C["IndustryNodeTopEventsService.run"]
    C --> D["filtered-subgraph(node_vid, BELONGS_TO_NODE+HAS_NODE, depth=1)<br/>→ 链节点信息 + 关联企业 + 产业链名"]
    D --> E{有企业?}
    E -- 否 --> Z["返回 evidence: 链节点下无关联企业"]
    E -- 是 --> F["按 chain_score 降序取 top max_orgs"]
    F --> G["每个企业 filtered-subgraph(org, INVOLVED_IN, depth=1)<br/>→ 收集事件"]
    G --> H["event_type / time_range 筛选 + 按 event_id 去重"]
    H --> I["impact_score 排序 → 取 TOP-N"]
    I --> J["风险等级判定"]
    J --> K["TOP 事件企业 GET /node/{org_id}/edges?edge_type=EXECUTIVE_OF 补查专家"]
    K --> L["构建 event→org→expert relations + evidence"]
    L --> M["前端 buildLiveGraph + buildLiveSummary 渲染"]
```

### 4.5 时序图

```mermaid
sequenceDiagram
    participant U as 浏览器/前端
    participant V as vite / nginx
    participant API as FastAPI (handler)
    participant SVC as IndustryNodeTopEventsService
    participant GS as graph-search API (dev)

    U->>V: POST /api/v1/kg-service/industry-node-top-events {chain_node_id, top_n}
    V->>API: 代理转发
    API->>SVC: run(req)
    SVC->>GS: GET /filtered-subgraph/{node_vid}?edge_types=BELONGS_TO_NODE,HAS_NODE
    GS-->>SVC: 链节点信息 + 关联企业(chain_score)
    SVC->>SVC: 按 chain_score 取 top max_orgs
    loop 每个企业
        SVC->>GS: GET /filtered-subgraph/{org_id}?edge_types=INVOLVED_IN
        GS-->>SVC: 事件
    end
    SVC->>SVC: 筛选/去重/impact_score 排序 → TOP-N
    loop TOP 事件企业
        SVC->>GS: GET /node/{org_id}/edges?edge_type=EXECUTIVE_OF
        GS-->>SVC: 专家
    end
    SVC-->>API: IndustryNodeTopEventsResponse
    API-->>V: 200 JSON
    V-->>U: 响应
    U->>U: buildLiveGraph / buildLiveSummary 渲染
```

---

## 5. 前端接线

`BusinessServiceAlgorithmPanel.vue`：

- `handleRun()` → `invokeKgService(module.endpoint, buildPayload())` → `liveResponse = res`。
- `buildLiveGraph(res, key)` → `graphNodes / graphEdges`（圆形布局，enterprise-relation: expert→企业；TOP-N: 链→企业→事件+专家）。
- `buildLiveSummary(res, key)` → `detailRows` 标签映射（角色/合作时间/合作模式/行业地位/风险预警…）。
- 溯源 tab：`liveResponse.data.evidence[]` 回退渲染。
- 图节点 `relations` 字段、事件置信度（`impact_score/10`）均来自真实响应。
- `moduleInfo.key` 变更时重置 `liveResponse`，避免上一业务的图残留。

---

## 6. 验证

- 单测：`tests/unit/test_tech_enterprise_relation_business_service.py`（mock httpx filtered-subgraph）、`tests/unit/test_industry_node_top_events_business_service.py`（mock httpx filtered-subgraph）。
- 集成测试：`tests/integration/test_tech_enterprise_relation_business_api.py`、`tests/integration/test_industry_node_top_events_business_api.py`（`@pytest.mark.external`）。
- 真实参数示例：重点关注科技企业关系 `expert_id=person_893b432670627d6337b9b7edaab0e917`；TOP-N 事件 `chain_node_id=IC0007007, top_n=5`。

> 已知数据缺口：TOP-N 中链节点关联企业的 governance 边（EXECUTIVE_OF）未全覆盖（`dwd_org_executive_info` 仅部分加载），部分企业查不到专家（experts=0），属数据覆盖问题，非脚本 bug。
