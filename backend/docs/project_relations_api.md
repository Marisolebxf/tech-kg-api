# 项目关系查询接口

## 1. 接口说明

该接口供其他业务系统分页查询“项目—关系—关联实体”记录。调用方无需了解图空间、
节点 VID、边方向或 nGQL，也不能通过该接口执行任意图查询。

```http
POST /api/v1/kg-service/project-relations/query
```

公网候选地址（须由部署人员确认网关 `/bkg_zpt` 转发规则）：

```text
https://edu.itic-sci.com/bkg_zpt/api/v1/kg-service/project-relations/query
```

生产内网地址应使用后端 API 或 API 网关的内网入口。`http://10.50.183.56:8091/graph-query`
是页面路由，不是本接口地址，不能作为系统间调用地址。

## 2. 认证

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

接口复用系统统一认证，不接收 TRSGraph `X-API-Key`，不支持匿名调用。调用系统应申请
服务账号或可续期的机器凭证，不应长期复用个人浏览器登录 Token。

## 3. 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---:|---|
| `keyword` | string | 否 | — | 项目名称或项目编号关键词，最大 256 字符 |
| `projectNumber` | string | 否 | — | 项目编号精确匹配，最大 128 字符 |
| `relationTypes` | string[] | 否 | 全部 | 关系类型白名单；空数组表示全部 |
| `pageSize` | integer | 否 | 100 | 每页关系记录数，范围 1～200 |
| `cursor` | string | 否 | — | 首次不传；翻页时原样传回 `nextCursor` |

`keyword` 与 `projectNumber` 不能同时传。空字符串经去空格后按未传处理。

允许的 `relationTypes`：

| 类型 | 中文名称 | 关联实体 |
|---|---|---|
| `FUNDED_BY` | 项目资助机构 | Organization |
| `LEADS` | 项目负责人 | Person |
| `HAS_PARTICIPANT` | 项目参与人 | Person |
| `HAS_KEYWORD` | 项目关键词 | Keyword |
| `HAS_OUTPUT` | 项目产出成果 | Paper、Patent、Report |

请求示例：

```json
{
  "keyword": "人工智能",
  "projectNumber": "",
  "relationTypes": ["LEADS", "HAS_OUTPUT"],
  "pageSize": 100,
  "cursor": ""
}
```

## 4. 成功响应

每个 `items` 元素是一条项目关系记录。分页单位是关系记录，不是项目。

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

无数据时：

```json
{
  "code": 200,
  "success": true,
  "data": {"items": [], "pageSize": 100, "nextCursor": "", "hasMore": false},
  "msg": "success"
}
```

仅返回接口定义的项目字段、关联实体展示字段以及白名单关系属性。内部溯源、匹配证据、
图空间和数据库连接信息不会返回。

## 5. 错误码

| HTTP 状态码 | 含义 |
|---:|---|
| 400 | 游标无效、为负数或与当前筛选条件不一致 |
| 401 | 未认证或 Token 无效 |
| 403 | 已认证但无接口访问权限 |
| 422 | 参数校验失败，包括非法关系类型、互斥条件或分页大小越界 |
| 502 | 图数据服务不可用或查询失败 |

## 6. curl 示例

```bash
curl -X POST \
  'https://edu.itic-sci.com/bkg_zpt/api/v1/kg-service/project-relations/query' \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "relationTypes": ["FUNDED_BY", "LEADS"],
    "pageSize": 100
  }'
```

## 7. 部署确认项

1. 确认公网网关是否把 `/bkg_zpt/api/*` 转发到 FastAPI，或是否会剥离 `/bkg_zpt`。
2. 确认内网后端/API 网关的真实端口；不要把前端 `/graph-query` 页面地址当成 API。
3. 确认 `TRS_GRAPH_SPACE` 指向正式生产图空间，不能是 `dev` 或 `dev2`。
4. 为调用系统配置独立机器身份、授权范围、Token 获取和续期方式。
5. 联调确认防火墙、TLS、超时、调用频率及审计要求。
