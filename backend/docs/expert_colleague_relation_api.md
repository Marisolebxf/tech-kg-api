# 科技专家同事关系服务 API

基础路径：`/api/v1`。

本服务通过提取科技专家在不同时期的工作单位、所属部门、参与团队等机构信息，结合知识图谱中的机构架构与人员任职数据，运用任职时间匹配与团队归属算法，推理并构建专家之间的同事关系。服务会判断同事关系的生效时段、所属团队或项目组，标注同事关系期间的共同工作内容与协作场景，同时关联两者在同事期间产生的合作成果，帮助用户了解科技专家的职业社交圈与工作协作历史。

服务通过内部 ASGI 调用公开图谱查询 API（`/api/v1/graph-search/*`）读取事实数据；推理成功后由应用层将 `COLLEAGUE` 边幂等写入固定的 `dev` 图空间。写入失败时接口失败，不会把未落库关系报告为成功。首次部署需执行 `schemas/dev_expert_colleague_schema.ngql`。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/kg-construction/expert-colleague-relations` | 模块描述（目录信息：code/name/description），无需参数 |
| POST | `/kg-service/expert-colleague-relation` | 推理并查询专家同事关系 |

统一响应包装为 `{code, success, data, msg}`。业务结果承载在 `data` 字段中。

## 1. 模块描述

`GET /api/v1/kg-construction/expert-colleague-relations`

返回该模块在 KG 构建模块目录中的注册信息，供前端展示与子功能下拉选择使用。

**响应示例：**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "code": "expert_colleague_relation",
    "name": "科技专家同事关系",
    "description": "基于任职单位、团队和时间匹配，推理专家之间的同事关系。"
  },
  "msg": "success"
}
```

## 2. 查询专家同事关系

`POST /api/v1/kg-service/expert-colleague-relation`

组合公开查图 API，推理指定专家的同事关系。

### 2.1 请求

请求体为 JSON，结构如下：

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `expert_id` | string | 是 | — | 专家 VID、`scholar_id`、`source_record_id` 或精确姓名；兼容旧字段 `expertId` |
| `organization` | string | 否 | null | 共同任职机构关键词，模糊匹配 |
| `department` | string | 否 | null | 共同部门、实验室或团队关键词，模糊匹配 |
| `overlap_period` | string | 否 | null | 任职重叠区间，如 `2018-01 至 2022-12`；兼容旧字段 `overlapPeriod` |
| `team_or_project` | string | 否 | null | 共同团队或项目组筛选 |
| `achievement_types` | string[] | 否 | null | Paper、Patent、Project、Report、Award |
| `min_confidence` | float | 否 | 0 | 最低置信度，0–1 |
| `limit` | int | 否 | 20 | 返回同事数量上限，取值范围 1–50 |
| `offset` | int | 否 | 0 | 分页偏移量，必须大于等于 0 |
| `space` | — | — | — | 不对普通调用方开放，查询和写入均由服务端固定为 `dev` |

`expertId` 解析顺序（`FastAPIGraphSearchGateway.resolve_person`）：

1. 将 `expertId` 原值作为 VID 调 `GET /nodes/{id}`；
2. 若不以 `person_` 开头，再以 `person_{expertId}` 作为 VID 重试（ETL 中人才实体 VID 形如 `person_{scholar_id}`）；
3. 仍取不到时，按 `name_zh` / `name_cn` / `name_en` / `name` / `source_record_id` 调 `POST /nodes/search` 取首条命中。

**请求示例：**

```json
{
  "expert_id": "E10001",
  "organization": "中国科学院自动化研究所",
  "department": "智能系统实验室",
  "overlap_period": "2018-01 至 2022-12",
  "limit": 20,
  "offset": 0
}
```

### 2.2 推理算法

服务以解析到的人才实体节点为圆心，沿边扩展推理：

1. 取专家 `AFFILIATED_WITH` 出边，得到任职机构列表（可按 `organization` 过滤）；
2. 取专家 `COAUTHOR_WITH` 边，得到合著论文计数；
3. 取专家 2 跳子图，建立邻居索引，用于后续查找共享成果与团队；
4. 对每个机构，查其 `AFFILIATED_WITH` 入边，找到同机构的其他人才（可按 `department` 过滤）作为同事候选；
5. 任职时间匹配：按月计算专家、候选和请求区间的交集；没有时间交集则排除（只要存在至少 1 个月的有效交集即成立），任一任职时间缺失也不输出同事关系，只计入待复核数；
6. 团队归属与成果关联：规范化比较双方部门，2 跳共享的团队/项目作为共同团队；共享成果只有在同事生效时段内才关联；
7. `COAUTHOR_WITH` 作为论文协作场景证据，但没有带年份的真实共同成果节点时不虚构成果；
8. 聚合同一候选人的多机构、多时段共同任职历史，并生成可解释评分明细；
9. 按置信度与成果数排序后，根据 `offset`、`limit` 分页。

### 2.3 响应

`data` 为 `ExpertColleagueRelationData`，结构如下：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `expert` | object | 中心专家信息 |
| `colleagues` | array | 当前页同事关系列表，按置信度与成果数降序 |
| `total` | int | 满足条件的同事总数，不受分页影响 |
| `returnedCount` | int | 当前页实际返回数量 |
| `offset` | int | 当前分页偏移量 |
| `limit` | int | 当前分页大小 |
| `summary` | object | 汇总统计 |
| `graph` | object | 可视化图谱（节点 + 边） |
| `apiCalls` | array | 本次推理实际调用的查图 API 记录 |
| `persistence` | object | `COLLEAGUE` 写入 dev 的新增、更新和总数 |

`expert` / `colleague` 结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 实体 VID |
| `name` | string | 姓名 |
| `organization` | string \| null | 机构 |
| `department` | string \| null | 部门 |
| `title` | string \| null | 职称 / 职务 |

`colleagues[]` 元素结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `colleague` | object | 同事专家信息（结构同上） |
| `commonOrganization` | string | 共同任职机构 |
| `commonDepartment` | string \| null | 共同部门 |
| `commonTeamOrProject` | string[] | 共同团队或项目组（最多 5 个） |
| `effectivePeriod` | string | 同事关系生效时段，如 `2020-01 至 2022-12` |
| `overlapMonths` | int | 重叠月数 |
| `overlapYears` | float | 重叠年数，按月数换算 |
| `workContent` | string[] | 共同工作内容（成果标题，最多 5 条；无真实成果证据时为空数组，不生成推测文本） |
| `collaborationScenes` | string[] | 协作场景，如 `同机构任职` / `同部门/团队协作` / `论文合作` / `项目组协作` |
| `achievements` | object[] | 同事期间关联合作成果（最多 10 条） |
| `confidence` | float | 置信度，范围 0–0.98 |
| `scoreBreakdown` | object | 同机构、重叠时长、同部门、合著、团队和成果的评分明细 |
| `employmentHistory` | object[] | 与该同事在不同机构、部门和时段的共同任职历史 |
| `evidence` | string[] | 证据链说明 |
| `reviewRequired` | bool | 已输出关系均具备时间证据，当前为 false；缺时间候选不输出 |

`achievements[]` 元素结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 成果节点 ID |
| `type` | string | 成果类型，如 `Paper` / `Project` / `Patent` / `Report` / `Award` |
| `title` | string | 成果标题 |
| `year` | int \| null | 成果年份 |

`summary` 结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `colleagueCount` | int | 同事数量 |
| `teamCount` | int | 涉及团队数量 |
| `maxOverlapYears` | float | 最大重叠年数 |
| `achievementCount` | int | 关联成果数量（去重） |
| `reviewRequiredCount` | int | 需人工复核的同事数量 |
| `generatedAt` | string | 生成时间（ISO 8601，UTC） |

`graph` 结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | array | 中心专家、同事、共同机构、团队/项目和合作成果节点 |
| `edges` | array | 同事关系、共同任职、所属团队和合作成果边 |

**成功响应示例：**

```json
{
  "code": 200,
  "success": true,
  "msg": "success",
  "data": {
    "expert": {
      "id": "person_a",
      "name": "张明远",
      "organization": "中国科学院自动化研究所",
      "department": "智能系统实验室",
      "title": null
    },
    "colleagues": [
      {
        "colleague": {
          "id": "person_b",
          "name": "李佳宁",
          "organization": "中国科学院自动化研究所",
          "department": "智能系统实验室",
          "title": null
        },
        "commonOrganization": "中国科学院自动化研究所",
        "commonDepartment": "智能系统实验室",
        "commonTeamOrProject": [],
        "effectivePeriod": "2020-01 至 2022-12",
        "overlapMonths": 36,
        "overlapYears": 3.0,
        "workContent": ["科技知识图谱关系推理"],
        "collaborationScenes": ["同机构任职", "同部门/团队协作", "论文合作"],
        "achievements": [
          {"id": "paper_1", "type": "Paper", "title": "科技知识图谱关系推理", "year": 2022}
        ],
        "confidence": 0.86,
        "evidence": [
          "共同任职机构：中国科学院自动化研究所",
          "任职时间重叠：2020-01 至 2022-12（36 个月）",
          "部门/团队：智能系统实验室",
          "同事期间关联合作成果 1 项"
        ],
        "reviewRequired": false
      }
    ],
    "total": 1,
    "summary": {
      "colleagueCount": 1,
      "teamCount": 0,
      "maxOverlapYears": 3,
      "achievementCount": 1,
      "reviewRequiredCount": 0,
      "generatedAt": "2026-08-05T08:00:00+00:00"
    },
    "graph": {
      "nodes": [
        {"id": "person_a", "type": "expert", "label": "张明远", "data": {"...": "..."}},
        {"id": "person_b", "type": "expert", "label": "李佳宁", "data": {"...": "..."}}
      ],
      "edges": [
        {
          "source": "person_a",
          "target": "person_b",
          "label": "同事关系",
          "data": {"organization": "中国科学院自动化研究所", "period": "2020-01 至 2022-12", "confidence": 0.86}
        }
      ]
    },
    "apiCalls": [
      {"method": "GET", "path": "/api/v1/graph-search/nodes/person_a", "params": {"space": "dev"}},
      {"method": "GET", "path": "/api/v1/graph-search/subgraph/person_a", "params": {"depth": 1, "limit": 100, "direction": "out", "edge_type": "AFFILIATED_WITH", "space": "dev"}}
    ]
  }
}
```

### 2.4 错误响应

HTTP 状态码均为 200，通过响应体 `code` 区分业务状态：

| code | success | 触发条件 | msg |
| --- | --- | --- | --- |
| 200 | true | 查询成功 | `success` |
| 404 | false | `expertId` 解析不到人才实体（`LookupError`） | `未找到专家: {expertId}` |
| 422 | false | `expertId` 为空或缺失（Pydantic 校验） | 校验错误信息 |
| 500 | false | 查图 API 调用失败或其他异常 | `专家同事关系查询失败: {exc}` |

失败时 `data` 为 `null`。

**错误响应示例：**

```json
{
  "code": 404,
  "success": false,
  "data": null,
  "msg": "未找到专家: person_10001"
}
```

## 3. 依赖的图谱查询接口

本服务通过内部 ASGI 调用以下已存在的通用图谱查询接口（非本模块新增）：

| 调用接口 | 用途 |
| --- | --- |
| `GET /api/v1/graph-search/nodes/{node_id}` | 按 VID 解析人才实体 |
| `POST /api/v1/graph-search/nodes/search` | 按姓名等属性解析人才实体 |
| `GET /api/v1/graph-search/subgraph/{node_id}` | 支持 `offset` 分页的一跳邻接扩展，取机构、同事、合著、成果、团队 |

涉及的图数据：人才实体节点（`Person`，VID 形如 `person_{scholar_id}`）、机构节点（`Organization`）、`AFFILIATED_WITH` 边（人→机构）、`COAUTHOR_WITH` 边（人→人），以及 Paper / Project / Patent / Report / Award 等成果节点与 Team / Laboratory / Department / Project 等团队节点。

## 4. dev 图空间数据就绪条件

服务只读取 `dev` 图空间，不读 MySQL，也不伪造同事关系。要产生同事结果，图中至少需具备：

- `Person -[AFFILIATED_WITH]-> Organization` 任职边；
- 任职边或相关节点上可解析的起止时间；
- 如需展示部门/团队，需有部门字段或共同 Team/Laboratory/Department/Project 节点；
- 如需关联合作成果，需双方共同连接带年份的 Paper/Project/Patent/Report/Award 节点。

当前实测通过 FastAPI ASGI 调用真实业务端点成功，但 `dev` 图空间查询未返回 `AFFILIATED_WITH` 边，因此返回空同事列表。这是图数据就绪问题，不是接口降级或 MySQL 兜底。

其他限制：同一候选人在多个机构均为同事时，仅保留置信度最高的一条；子图单页最多返回 200 条边，业务网关通过 `offset` 自动翻页并去重。
