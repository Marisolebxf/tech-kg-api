# 项目关系查询接口

分页查询「项目—关系—关联实体」记录，供外部业务系统调用。调用方无需了解图空间、
节点 VID、边方向或 nGQL，也不能通过本接口执行任意图查询。

## 1. 接口地址

```http
POST /api/v1/kg-service/project-relations/query
Content-Type: application/json
```

| 环境 | 地址 |
|---|---|
| 公网（网关） | `https://edu.itic-sci.com/bkg_zpt/api/v1/kg-service/project-relations/query` |
| 内网（直连后端） | `http://10.50.183.56:8002/api/v1/kg-service/project-relations/query` |

注意：`http://10.50.183.56:8091/graph-query` 是前端页面地址，不是本接口地址，不能用于系统间调用。

## 2. 认证

每个请求必须携带统一用户中心签发的 Bearer Token：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

- Token 由「统一用户中心」（OAuth2）签发。接入前向平台申请服务账号或可续期的机器
  凭证，勿长期复用个人浏览器登录 Token。
- Token 缺失或过期返回 HTTP 401，重新获取或续期后重试。
- 本接口不接收 TRSGraph `X-API-Key`，不支持匿名调用。

## 3. 请求参数

请求体为 JSON 对象，**必传**（没有任何筛选时也至少传空对象 `{}`）。所有字段均可选：

| 字段 | 类型 | 默认值 | 约束 | 说明 |
|---|---|---|---|---|
| `keyword` | string | 不筛选 | ≤256 字符 | 项目名称**或**项目编号的子串匹配（CONTAINS） |
| `projectNumber` | string | 不筛选 | ≤128 字符 | 项目编号**等值精确**匹配 |
| `relationTypes` | string[] | `[]` = 全部 | ≤5 个，重复自动去重 | 关系类型白名单 |
| `pageSize` | integer | 100 | 1～200 | 每页返回的关系记录条数 |
| `cursor` | string | 不翻页 | ≤2048 字符 | 翻页游标，原样传回上一页的 `nextCursor`，不要自行构造或修改 |

规则：

- `keyword` 与 `projectNumber` 互斥，同时传返回 422。
- 空字符串（去空格后）视为未传。
- **不传任何筛选参数（空对象 `{}`）= 查询全部项目的全部关系**：按默认
  `pageSize=100` 返回第一页，之后用 `nextCursor` 翻页，直到 `hasMore=false`
  即遍历完全量数据。
- 结果排序固定为：项目 id → 关系类型 → 关联实体 id。翻页基于偏移量，遍历期间
  图数据若有增删，可能出现少量重复或遗漏，对一致性敏感的调用应重查核对。

参数输入示例：

| 参数 | 示例值 | 含义 |
|---|---|---|
| `keyword` | `"人工智能"` | 标题含「人工智能」的项目 |
| `keyword` | `"2029378"` | 编号含「2029378」的项目（子串，可能命中多个） |
| `projectNumber` | `"2029378"` | 编号恰好等于 2029378 的那一个项目（定点查询的推荐方式） |
| `relationTypes` | `[]` | 全部五种关系 |
| `relationTypes` | `["LEADS"]` | 只查项目负责人关系 |
| `relationTypes` | `["LEADS", "HAS_OUTPUT"]` | 负责人 + 产出成果 |
| `pageSize` | `20` | 每页 20 条 |
| `cursor` | `"eyJ2IjoxLCJvZmZzZXQiOjEwMC..."` | 上一页响应里 `nextCursor` 的值，原样回传 |

允许的 `relationTypes` 取值：

| 类型 | 中文名称 | 关联实体类型 |
|---|---|---|
| `FUNDED_BY` | 项目资助机构 | Organization |
| `LEADS` | 项目负责人 | Person |
| `HAS_PARTICIPANT` | 项目参与人 | Person |
| `HAS_KEYWORD` | 项目关键词 | Keyword |
| `HAS_OUTPUT` | 项目产出成果 | Paper、Patent、Report |

## 4. 请求示例

（1）查询全部项目关系（第一页，其余字段全部走默认）：

```json
{}
```

（2）按项目编号精确查询（推荐的系统间定点查询方式）：

```json
{"projectNumber": "2029378", "relationTypes": [], "pageSize": 100}
```

（3）按关键词查询，只看负责人和产出成果：

```json
{"keyword": "人工智能", "relationTypes": ["LEADS", "HAS_OUTPUT"], "pageSize": 50}
```

（4）只查某一种关系：

```json
{"relationTypes": ["FUNDED_BY"], "pageSize": 10}
```

（5）翻页取下一页（`cursor` 填上一页响应的 `nextCursor` 原值）：

```json
{"relationTypes": [], "pageSize": 100, "cursor": "eyJ2IjoxLCJvZmZzZXQiOjEwMC4uLg"}
```

## 5. 成功响应

HTTP 200。`items` 的每个元素是一条关系记录；**分页单位是关系记录，不是项目**
——一个项目有 9 条关系就会占 9 条记录。接口不返回总条数，翻页终点以
`hasMore=false` 为准。

```json
{
  "code": 200,
  "success": true,
  "data": {
    "items": [
      {
        "project": {
          "id": "project_123",
          "projectNumber": "2026ABC001",
          "title": "人工智能关键技术研究",
          "projectSource": "zh_project",
          "projectLevel": "国家级",
          "approvalYear": "2026",
          "researchPeriod": "2026-2028"
        },
        "relation": {
          "type": "LEADS",
          "name": "项目负责人",
          "direction": "out",
          "properties": {"confidence": 1.0}
        },
        "relatedEntity": {
          "id": "person_456",
          "type": "Person",
          "name": "张三",
          "properties": {}
        }
      }
    ],
    "pageSize": 100,
    "nextCursor": "eyJ2IjoxLCJvZmZzZXQiOjEwMC4uLg",
    "hasMore": true
  },
  "msg": "success"
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `data.pageSize` | 本页条数上限（回显请求值） |
| `data.nextCursor` | 下一页游标；`hasMore=false` 时为空字符串，无需再传 |
| `data.hasMore` | 是否还有下一页 |
| `project.id`、`relatedEntity.id` | 图库内部 ID，无业务含义，仅用于展示或去重，不要解析其内容 |
| `relation.direction` | 恒为 `"out"`（项目 → 关联实体） |
| `relation.properties` | 白名单关系属性，见下；未列出的关系属性一律不返回 |
| `relatedEntity.properties` | 恒为空对象 |

`relation.properties` 白名单：`FUNDED_BY` → `funded_amount` / `fund_category` /
`confidence`；`LEADS` / `HAS_PARTICIPANT` / `HAS_KEYWORD` → `confidence`；
`HAS_OUTPUT` → `output_type` / `output_title` / `output_identifier` / `confidence`。

无数据时：

```json
{"code": 200, "success": true, "data": {"items": [], "pageSize": 100, "nextCursor": "", "hasMore": false}, "msg": "success"}
```

## 6. 错误响应

**重要：参数校验失败时 HTTP 状态码仍为 200**，失败信息在响应体的 `code` / `success`
字段里（平台统一响应壳）。调用方判断成败必须看 `success`（或 `code`），不能只看
HTTP 状态码。其余错误（400 / 401 / 502）是真实 HTTP 状态码，响应体为
`{"detail": "..."}` 格式。

| 场景 | HTTP 状态码 | 响应体格式 |
|---|---:|---|
| 参数校验失败：非法关系类型、`keyword` 与 `projectNumber` 同传、`pageSize` 越界、缺请求体等 | **200** | 统一响应壳 `code=422`，见下方实测示例 |
| 游标格式无效；或修改了筛选条件后仍沿用旧游标 | 400 | `{"detail": "游标格式无效"}` |
| 未认证、Token 缺失或已过期 | 401 | `{"detail": "尚未登录"}` |
| 图数据服务不可用或查询失败 | 502 | `{"detail": "图数据服务暂时不可用，请稍后重试"}` |

参数校验失败响应体示例（`keyword` 与 `projectNumber` 同传，实测返回）：

```json
{
  "code": 422,
  "success": false,
  "data": [
    {
      "loc": ["body"],
      "msg": "Value error, keyword 和 projectNumber 不能同时传入",
      "type": "value_error"
    }
  ],
  "msg": "请求参数校验失败"
}
```

排查提示：若 400 响应中出现 `No valid index found`，为平台图库缺少编号索引的
环境问题，请联系平台运维处理，调用方无需改动。

## 7. 完整 curl 示例

```bash
curl -X POST \
  'https://edu.itic-sci.com/bkg_zpt/api/v1/kg-service/project-relations/query' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"projectNumber": "2029378", "relationTypes": [], "pageSize": 100}'
```

## 8. 性能预期

- `projectNumber` 精确匹配走图库索引，响应快（毫秒～秒级），适合系统间定点查询。
- `keyword` 为子串全扫描，项目规模大时响应可能达秒级，适合人工检索场景；
  程序化集成优先使用 `projectNumber`。
