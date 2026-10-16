# kg-open 对外图谱查询接口

面向外部系统的只读图谱查询 API。设计原则：**入口是 Schema 大类，不是 VID**——调用方不需要预先了解图内部结构，先拿"地图"（接口 1），再按类分页拉数据（接口 2/3）。不做属性条件过滤（无索引全扫）、不提供 nGQL 直通、不做多跳遍历。

- 路由前缀：`/api/v1/kg-open`
- 实现代码：`backend/biz/handler/kg_open.py`（鉴权 `backend/biz/dependencies/kg_open_auth.py`）
- 鉴权与项目关系接口（`/kg-service/project-relations`）同一套双通道模式
- **图空间固定为默认业务空间（dev）**：不接受 `space` / `graphSpace` 参数或 `X-Graph-Space` 头换空间，传了也会被忽略

## 鉴权

| 通道 | 用法 | 可查空间 |
|---|---|---|
| 机器密钥 | 请求头 `X-Client-Id` + `X-API-Key`（scope 须含 `kg-open:read`） | 固定默认业务空间（dev），另需共享生产空间门禁 |
| 平台用户 | `Authorization: Bearer <统一用户中心token>`（或平台会话） | 固定默认业务空间（dev） |

- 提供任一 API Key 头即视为机器认证，密钥错误**不会**回退到浏览器身份。
- 密钥签发/轮换/停用（后端容器内执行）：

```bash
docker exec <api容器> python script/manage_external_api_clients.py create \
  --client-id <调用方id> --business-name <业务方名> --scopes kg-open:read
# 输出的 api_key 仅展示一次，通过安全渠道交付；轮换用 rotate，回收用 disable
```

## 响应与错误约定

- 成功：HTTP 200 + 统一信封 `{"code": 200, "success": true, "data": {...}, "msg": "success"}`
- 失败：真实 HTTP 状态码 + `{"detail": "..."}`（与项目关系接口一致）
- 参数校验失败（长度/范围等）：平台统一包装为 HTTP 200 + `code 422` 信封
- 常见错误：`400` 类型名不合法 / `401` 密钥无效 / `403` 无空间权限或 scope 不足 / `404` 类型不存在 / `429` 图查询过载（带 `Retry-After: 1`，应退避 ≥1s 重试）/ `502` 图服务不可用

图查询共用平台全局执行预算（16 并发 / 64 排队 / 等待 10s），过载时返回 429，不会拖垮图库。

## 接口 1：`GET /kg-open/schema` — 图谱地图

无参数（空间固定，见总约定）。

返回 `data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `space` | string | 实际生效空间 |
| `entityTypes[]` | array | 实体类：`name`（TAG 名，接口 2 入参）/ `displayName` / `description` / `count`（图上总数，SHOW STATS 口径）/ `properties[]`（`{name, type, required}`） |
| `relationTypes[]` | array | 关系类：同上外加 `sourceType` / `targetType`（两端实体类名） |

```json
{"code": 200, "success": true, "data": {
  "space": "dev",
  "entityTypes": [
    {"name": "Paper", "displayName": "论文", "description": "", "count": 6590000,
     "properties": [{"name": "title", "type": "string", "required": false}]}
  ],
  "relationTypes": [
    {"name": "AUTHORED_BY", "displayName": "撰写", "description": "", "count": 18400000,
     "properties": [], "sourceType": "Paper", "targetType": "Person"}
  ]
}, "msg": "success"}
```

## 接口 2：`GET /kg-open/entity-types/{name}/entities` — 按实体类拉实体

| 参数 | 位置 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `name` | path | 是 | — | `^[A-Za-z_][A-Za-z0-9_]{0,127}$`，来自接口 1 |
| `limit` | query | 否 | 20 | 1–500 |
| `offset` | query | 否 | 0 | 0–10,000,000 |

返回 `data`：`space`（固定默认空间）、`entityType`、`entities[]`（`id`=VID 稳定唯一键 / `type` / `name` 展示名 / `properties` 全属性整体透传）、`total`（图上真实总数）、`limit`、`offset`、`relationTypes[]`（目录推导：端点包含该实体类的所有关系类名，提示接下来可查哪些边）。

属性整体透传意味着 Schema 新增属性**无需**改对接；`properties` 内值可能为 null。

## 接口 3：`GET /kg-open/relation-types/{name}/edges` — 按关系类拉边

| 参数 | 位置 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `name` | path | 是 | — | 同上 |
| `limit` | query | 否 | 20 | 1–500 |
| `offset` | query | 否 | 0 | 0–10,000,000 |
| `includeEntities` | query | 否 | true | false 时只返回边不补端点实体（自持实体清单时省流量） |

返回 `data`：`space`（固定默认空间）、`relationType`、`edges[]`（`type` / `source` / `target` 两端 VID / `properties` 边属性；`includeEntities=true` 时附 `sourceEntity` / `targetEntity`，结构与接口 2 实体相同）、`total`、`limit`、`offset`。

`total` 采用 SHOW STATS 统计口径（与接口 1 的 `count` 同源，**包含悬挂边**；空间从未跑过统计时回退 REST 计数）。trs-graph REST 自带的分页计数对部分边类型恒为 0（实测返回行非空仍报 0），故不采用。

**悬挂边**：写入时端点实体未落图的边（如引用桩），对应 `sourceEntity` / `targetEntity` 为 `null`，不是错误。

## 调用方最小使用流

```bash
# ① 地图：有哪些类、属性怎么定义
curl -H "X-Client-Id: $CID" -H "X-API-Key: $KEY" http://host:8002/api/v1/kg-open/schema

# ② 按类拉实体（翻页：offset += limit，直到 offset >= total）
curl -H "X-Client-Id: $CID" -H "X-API-Key: $KEY" \
  "http://host:8002/api/v1/kg-open/entity-types/Paper/entities?limit=500&offset=0"

# ③ 按类拉边（边 + 两端实体一次拿全）
curl -H "X-Client-Id: $CID" -H "X-API-Key: $KEY" \
  "http://host:8002/api/v1/kg-open/relation-types/AUTHORED_BY/edges?limit=500&offset=0"
```

本地按 `edges[].source/target ↔ entities[].id` 关联，即得"实体 + 关系 + 属性"完整切片。

## 量级与边界

- **没有"返回全部"接口**：亿级图单次响应装不下（详见设计讨论）。全量需求 = 对每个类循环翻页，分页即护栏。若调用方要一次性镜像整图，另立异步导出通道（二期），勿走查询接口。
- 深分页（offset 极大）逐页变慢，属图库遍历特性；交互式查询建议带类过滤 + 小页。
- `total` / `count` 来自 SHOW STATS 统计快照（300s 缓存），非实时精确；按 `offset >= total` 判断翻页结束。

## 上线前置检查（运维）

1. **边索引**：按关系类枚举走 LOOKUP，需每个 EDGE 类型有边索引。TRS 定制版零属性边索引有"CREATE 静默 no-op"坑：先 `SHOW EDGE INDEXES IN <space>` 核查，缺的显式补建并去重。
2. **标签索引**：实体类枚举无标签索引时回退 MATCH 全扫（慢但正确）：`SHOW TAG INDEXES IN <space>` 核查，缺的补建后自动切快路径。
3. 对外空间的数据质量先行确认（空心化 Schema 未修复的空间不要对外）。
