# 对外图谱查询 API（kg-open）

本接口面向其他业务系统，仅提供三个只读接口：查询类型目录、按实体类型查询实体、按关系类型查询关系及两端实体。不增加其他对外查询入口。

公网入口按当前 edu 部署的网关路径编写：

```text
https://edu.itic-sci.com/bkg_zpt/api/v1/kg-open
```

**该地址是部署契约，不表示已在线上验收。** 发布新版后需确认 edu 网关允许下列 GET 路由转发，并保留认证 Header；如网关另有统一登录拦截，需要由运维为机器调用配置适用的认证规则。

## 1. 接口总览

以下路径相对于上面的公网入口。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/schema` | 实体类型、关系类型、属性及端点定义，附参考统计 |
| GET | `/entity-types/{name}/entities` | 按实体类型分页枚举实体 |
| GET | `/relation-types/{name}/edges` | 按关系类型分页枚举关系，可附两端实体 |

调用方先获取目录，再按实体类或关系类分页获取数据，通过边的 source/target 与实体 id 关联。按实体类型查询返回实体及属性，不自动返回其关联边；需要点边一起返回时，使用关系类型接口并保持 includeEntities=true。

## 2. 认证与授权

外部系统每次请求同时携带：

```http
X-Client-Id: <管理员分配的调用方ID>
X-API-Key: <管理员签发的密钥>
```

三个接口均为 GET，不需要请求体。

- 3 个接口统一要求 `kg-open:read`。只有 `project-relations:read` 的旧凭证不能调用这些接口。
- 凭证由本系统自己的 `external_api_client` 表管理，不需要调用方登录统一用户中心；每个业务系统单独签发，不要共用其他系统的凭证。
- API Key 为 32 字节安全随机数，数据库只存 SHA-256 摘要。明文仅创建或轮换时显示一次。
- 默认有效期 **365 天**；签发/轮换可指定 `--expires-days 1～3650`。精确过期时刻为签发 UTC 时刻加指定天数；请求不会续期。
- 带任一 API Key Header 就选择机器认证，缺项、重复、错误、过期或停用均拒绝，不回退到 Bearer/Cookie。
- 不带两个 API Key Header 时，兼容平台用户的 Bearer/Cookie 认证和空间读权限检查。
- 固定查询后端 `TRS_GRAPH_SPACE` 配置的默认空间，未配置时为 `dev`。请求中的 `space`、`graphSpace` 和 `X-Graph-Space` 不用于切换空间。
- `BUSINESS_RBAC_ENABLED=true` 时，机器调用还要求默认空间登记为共享生产空间。单个 `kg-open:read` 凭证可读取这个空间的所有对外目录实体类型、关系类型及完整属性；目前没有细分到字段或业务行的授权。
- 正式环境启用 `AUTH_ENABLED=true`，不要启用模拟开发身份；调用方在后端保存凭证，通过 HTTPS 调用。

## 3. 公共响应与分页

成功响应：

```json
{"code":200,"success":true,"data":{"space":"dev"},"msg":"success"}
```

以下各接口仅展示 `data` 内容；实际均包含外层响应壳和实际生效的 `space`。

### 分页规则

- `limit` 默认 20，范围 1～500。
- 首次不传 `cursor` 或传空字符串。读取 `hasMore`，为 true 时将 `nextCursor` 原样传回；false 时结束。**不能用 `total` 或 `count` 决定是否结束。**
- 服务端多取一条记录判断 `hasMore`，不依赖统计总数。
- 游标绑定空间和类型筛选条件；更换类型时必须重新开始。`limit` 可改变，`includeEntities` 可改变。
- 实体按 VID 排序，边按 `(source, target, rank)` 排序。新游标使用上述最后一个键继续，不存在一千万 offset 上限；这不保证查询耗时与总量无关。
- 旧 GET 类型列表仍接受 `offset=0～10000000`，默认 0；与非空 cursor 同时使用时 offset 必须为 0。新调用方使用 cursor。
- 游标是分页位置，不是认证凭证、加密数据或数据库快照。遍历时新增的较小键可能不被读到，删除的记录可能消失；严格一致的全量导出需独立快照机制。
- `total`、`count` 是 SHOW STATS 的参考快照，`totalIsEstimate` / `countIsEstimate` 恒为 true；未知时为 **-1**。统计缓存约 300 秒，实际新鲜度还取决于最近一次统计任务，不是每 300 秒自动重算。

### 实体与关系结构

实体：

```json
{"id":"paper_1","type":"Paper","types":["Paper"],"name":"示例论文","properties":{"title":"示例论文"}}
```

`id` 是原样使用的实体 VID，可含 `/` 等字符，不要从中解析业务信息。`types` 保留所有标签，旧字段 `type` 为第一个标签。`name` 优先取属性 name，其次 title，均无则为空字符串。`properties` 完整返回，值可以为 null。

关系：

```json
{
  "id":"[\"AUTHORED_BY\",\"paper_1\",\"person_1\",0]",
  "type":"AUTHORED_BY","source":"paper_1","target":"person_1","rank":0,
  "properties":{"confidence":0.9},
  "sourceEntity":{"id":"paper_1","type":"Paper","types":["Paper"],"name":"示例论文","properties":{"title":"示例论文"}},
  "targetEntity":null
}
```

`id` 是服务端返回的完整关系标识，调用方原样保存；完整去重键为 `(type, source, target, rank)`。相同两端可以存在不同 rank 的平行边。`source` → `target` 始终为存储方向，入向查询不会将其反转。附带实体时，缺失端点返回 null（悬挂边），并不伪造实体。关闭附带实体时省略两个 Entity 字段。

## 4. 接口明细

三个接口的外层响应壳一致（`code` / `success` / `data` / `msg`），`data` 内均含生效的 `space`。以下仅描述 `data` 中的业务字段。

### 4.1 GET `/schema` — 查询类型目录

**用途**：一次性返回当前图谱全部有效的实体类型与关系类型定义（类型编码、显示名、描述、属性清单、关系端点），并附每类的参考计数。这是调用另外两个接口的前提——先从本接口拿到合法的类型编码 `name`，再去做分页枚举；类型编码不存在时枚举接口直接返回 404。

**输入参数**：无业务入参，仅携带认证 Header。

**输出参数**（`data`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `space` | string | 实际生效的图空间（固定默认业务空间） |
| `entityTypes` | array | 实体类型列表，元素结构见下表 |
| `relationTypes` | array | 关系类型列表，元素结构见下表 |
| `statsAvailable` | bool | 是否取得了图统计；false 时所有 `count` 均为 -1，目录仍正常返回 |

`entityTypes[]` / `relationTypes[]` 元素结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 类型编码。调用 4.2 / 4.3 时传这个值，**不能用中文 `displayName` 代替** |
| `displayName` | string | 中文显示名，仅用于界面展示 |
| `description` | string | 类型描述，可为空字符串 |
| `properties` | array | 属性定义列表，元素 `{name, type, required}`：属性编码、目录登记的数据类型（string/int/float/bool 等）、目录定义是否必填。这只是目录定义，不保证每条实体/边上该属性有值 |
| `count` | int | 该类型的参考计数（SHOW STATS 快照，约 300 秒缓存）；未知为 **-1** |
| `countIsEstimate` | bool | 恒为 true，`count` 是估计值不是精确总数 |
| `sourceType` | string | 仅 `relationTypes`：关系起点实体类型编码。端点定义可能用 `\|` 表示多个实体类型，如 `Paper\|Patent\|Report` |
| `targetType` | string | 仅 `relationTypes`：关系终点实体类型编码，规则同上 |

**响应示例**（截短，仅保留 1 个类型）：

```json
{
  "code": 200, "success": true, "msg": "success",
  "data": {
    "space": "dev",
    "statsAvailable": true,
    "entityTypes": [
      {
        "name": "Paper", "displayName": "论文", "description": "",
        "properties": [
          {"name": "id", "type": "string", "required": true},
          {"name": "title_zh", "type": "string", "required": false},
          {"name": "doi", "type": "string", "required": false}
        ],
        "count": 92000, "countIsEstimate": true
      }
    ],
    "relationTypes": [
      {
        "name": "AUTHORED_BY", "displayName": "作者关系", "description": "",
        "properties": [{"name": "confidence", "type": "float", "required": false}],
        "sourceType": "Paper", "targetType": "Person",
        "count": -1, "countIsEstimate": true
      }
    ]
  }
}
```

### 4.2 GET `/entity-types/{name}/entities` — 按实体类型枚举实体

**用途**：分页枚举指定实体类型下的全部实体，返回每个实体的完整属性。本接口只返回点，**不返回边**——也不会自动附带这些实体参与的关联边；需要边和两端实体一起返回时使用 4.3。

**输入参数**：

路径参数：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 实体类型编码（`/schema` 返回的 `entityTypes[].name`），须匹配 `[A-Za-z_][A-Za-z0-9_]{0,127}`；不匹配返回 400，目录中不存在返回 404 |

Query 参数：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `limit` | int | 否 | 20 | 页大小，范围 1～500 |
| `cursor` | string | 否 | 空串 | 翻页游标。首页不传或传空串；之后原样回传上一页 `nextCursor`。最长 4096 字符；与服务端记录的空间/接口/类型绑定，换类型必须从头开始；与 `offset` 非零值同传返回 400 |
| `offset` | int | 否 | 0 | 旧 offset 分页兼容参数，范围 0～10000000。新调用方一律使用 `cursor` |

**输出参数**（`data`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `entityType` | string | 本次查询的实体类型编码（回显） |
| `entities` | array | 实体列表，元素结构见下；按 `id`（VID）升序排列 |
| `limit` | int | 生效页大小（回显） |
| `offset` | int | 生效 offset（回显；cursor 翻页时为 0） |
| `hasMore` | bool | 是否还有下一页，**翻页结束的唯一依据**（不要用 total 判断） |
| `nextCursor` | string | 下一页游标；`hasMore=false` 时为空字符串 |
| `total` | int | 该类型参考总数（SHOW STATS 快照）；未知为 -1 |
| `totalIsEstimate` | bool | 恒为 true |
| `relationTypes` | array[string] | 该实体类型作为起点或终点参与的关系类型编码列表，提示可用 4.3 继续枚举这些边 |

`entities[]` 元素结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 实体 VID，原样保存使用，可含 `/` 等字符，**不要从中解析业务信息** |
| `type` | string | 第一个标签（兼容旧调用方的字段） |
| `types` | array[string] | 该实体的全部标签 |
| `name` | string | 便捷名称：优先取属性 `name`，其次 `title`，均无为空字符串 |
| `properties` | object | 该实体全部属性的键值对，完整返回，值可为 null |

**响应示例**（`limit=1` 截短）：

```json
{
  "code": 200, "success": true, "msg": "success",
  "data": {
    "space": "dev", "entityType": "Paper",
    "entities": [
      {
        "id": "paper_100000040", "type": "Paper", "types": ["Paper"], "name": "",
        "properties": {
          "doi": "10.1515/zna-2023-0322",
          "title_zh": "自旋1/2简并致密量子等离子体中的磁声波：非线性动力学与耗散效应"
        }
      }
    ],
    "limit": 1, "offset": 0, "hasMore": true,
    "nextCursor": "eyJ2IjogMSwgInNjb3BlIjogIjk1MDUzMjY5NzI1MmU2OTE0NmQ5MjEx...",
    "total": 92000, "totalIsEstimate": true,
    "relationTypes": ["AUTHORED_BY", "CITED_BY"]
  }
}
```

示例中 `name` 为空字符串：该实体没有 `name`/`title` 属性，标题在 `title_zh`。需要展示名称时自行从 `properties` 里取合适的字段。

### 4.3 GET `/relation-types/{name}/edges` — 按关系类型枚举边

**用途**：分页枚举指定关系类型下的全部边，返回每条边的完整属性；`includeEntities=true`（默认）时同时附带两端实体的完整数据，通过 `source`/`target` 与实体 `id` 对齐。**需要"点+边"一起拿数据时使用本接口**；只想要点用 4.2 更快。

**输入参数**：

路径参数：`name` — 关系类型编码（`/schema` 返回的 `relationTypes[].name`），命名规则与错误码同 4.2。

Query 参数：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `limit` | int | 否 | 20 | 页大小，范围 1～500 |
| `cursor` | string | 否 | 空串 | 翻页游标，规则同 4.2；本接口游标绑定 `(source, target, rank)` 三键位置 |
| `offset` | int | 否 | 0 | 旧 offset 分页兼容参数，规则同 4.2 |
| `includeEntities` | bool | 否 | true | 是否附带两端实体对象。false 时每条边省略 `sourceEntity`/`targetEntity` 字段，响应更小；已用 4.2 单独枚举过实体时建议关闭以减少重复传输 |

**输出参数**（`data`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `relationType` | string | 本次查询的关系类型编码（回显） |
| `edges` | array | 边列表，元素结构见下；按 `(source, target, rank)` 升序排列 |
| `limit` / `offset` / `hasMore` / `nextCursor` / `total` / `totalIsEstimate` | — | 语义与 4.2 对应字段完全一致 |

`edges[]` 元素结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 服务端生成的完整关系标识，即 JSON 数组字符串 `["类型","source","target",rank]`，调用方原样保存即可，不要自行拼接 |
| `type` | string | 关系类型编码 |
| `source` | string | 起点实体 VID（始终为存储方向） |
| `target` | string | 终点实体 VID（始终为存储方向，入向查询也不会反转） |
| `rank` | int | 边 rank（int64）。相同两端可存在多条不同 rank 的平行边；完整去重键 = `(type, source, target, rank)` |
| `properties` | object | 该边全部属性的键值对，值可为 null |
| `sourceEntity` | object 或 null | 起点实体对象，结构同 4.2 的 `entities[]` 元素；端点实体在图中不存在（悬挂边）时为 **null，不伪造实体** |
| `targetEntity` | object 或 null | 终点实体对象，规则同上 |

`includeEntities=false` 时 `sourceEntity`/`targetEntity` 两个字段整体省略（不是 null）。

**响应示例**（`limit=1` 截短）：

```json
{
  "code": 200, "success": true, "msg": "success",
  "data": {
    "space": "dev", "relationType": "ACTUAL_CONTROLLER_OF",
    "edges": [
      {
        "id": "[\"ACTUAL_CONTROLLER_OF\",\"person_15f36a9c...\",\"org_MOCK_...\",7889892470359242357]",
        "type": "ACTUAL_CONTROLLER_OF",
        "source": "person_15f36a9cd43ddbe691e002fde0498cd5",
        "target": "org_MOCK_FORG_20260721_036",
        "rank": 7889892470359242357,
        "properties": {"confidence": 0.95, "direct_pct": 85.0},
        "sourceEntity": {"id": "person_15f36a9cd43ddbe691e002fde0498cd5", "type": "Person",
                          "types": ["Person"], "name": "谭某某", "properties": {"...": "..."}},
        "targetEntity": {"id": "org_MOCK_FORG_20260721_036", "type": "Organization",
                          "types": ["Organization"], "name": "Mei Tan Demo Holdings", "properties": {"...": "..."}}
      }
    ],
    "limit": 1, "offset": 0, "hasMore": true,
    "nextCursor": "eyJ2IjogMSwgInNjb3BlIjog...",
    "total": -1, "totalIsEstimate": true
  }
}
```

## 5. 完整调用示例

以下 CID/KEY 为调用方后端配置中的凭证，不包含真实密钥。

```bash
BASE='https://edu.itic-sci.com/bkg_zpt/api/v1/kg-open'

# 1. 查看实体与关系类型及其属性
curl --fail-with-body "$BASE/schema" \
  -H "X-Client-Id: $CID" -H "X-API-Key: $KEY"

# 2. 按实体类型分页获取实体（类型名以目录实际返回为准）
curl --fail-with-body --get "$BASE/entity-types/Paper/entities" \
  -H "X-Client-Id: $CID" -H "X-API-Key: $KEY" \
  --data-urlencode 'limit=100'

# 3. 按关系类型分页获取边及两端实体
curl --fail-with-body --get "$BASE/relation-types/AUTHORED_BY/edges" \
  -H "X-Client-Id: $CID" -H "X-API-Key: $KEY" \
  --data-urlencode 'limit=100' --data-urlencode 'includeEntities=true'

# 4. 下一页：CURSOR 填上一页 data.nextCursor 原值，直到 hasMore=false
curl --fail-with-body --get "$BASE/relation-types/AUTHORED_BY/edges" \
  -H "X-Client-Id: $CID" -H "X-API-Key: $KEY" \
  --data-urlencode 'limit=100' --data-urlencode "cursor=$CURSOR"
```

curl 的 --fail-with-body 不能识别 HTTP 200 包装的业务错误；调用代码必须同时检查 HTTP 状态码和 JSON 的 success / code。

## 6. 错误约定

| 场景 | HTTP | 响应 |
|---|---:|---|
| 成功（含无匹配结果） | 200 | `code=200, success=true` 响应壳 |
| 参数校验失败、分页越界等 | 200 | 平台统一 `code=422, success=false` 响应壳 |
| 非法类型名、无效/不匹配游标 | 400 | `{"detail":"..."}` |
| 缺少身份、密钥错误/缺项/重复/过期/停用 | 401 | `{"detail":"..."}` |
| 有效凭证但缺少 kg-open:read 或空间门禁不通过 | 403 | `{"detail":"..."}` |
| 类型不存在 | 404 | `{"detail":"..."}` |
| 图执行队列满或等待超时 | 429 | `{"detail":"..."}`，`Retry-After: 1` |
| 图服务调用失败或超时 | 502 | `{"detail":"图数据服务暂时不可用，请稍后重试"}` |
| 认证数据库不可用、目录数据库查询失败、所需索引未就绪 | 503 | `{"detail":"..."}` |

不对 400/401/403/404 盲目重试。429 至少退避 1 秒并加随机抖动，502/503 有限次数退避并联系运维排查。非 2xx 且响应不是 JSON 时，应保留 HTTP 状态作为网关/网络故障处理。

## 7. 运维与兼容性

首次部署初始化凭证表（已存在则不修改）：

```bash
docker exec -w /app <后端容器名> .venv/bin/python -m script.manage_external_api_clients init
```

给新系统创建一份 365 天图查询凭证：

```bash
docker exec -w /app <后端容器名> .venv/bin/python -m script.manage_external_api_clients create \
  --client-id partner_graph_a --business-name '图查询业务系统A' \
  --scopes kg-open:read --expires-days 365
```

轮换不传 `--scopes` 时保留现有权限；传入时**替换**为给定权限。下面同时保留两个接口组权限（旧 Key 会立即失效，需协调调用方更新）：

```bash
docker exec -w /app <后端容器名> .venv/bin/python -m script.manage_external_api_clients rotate \
  --client-id partner_graph_a --expires-days 365 \
  --scopes project-relations:read,kg-open:read
```

轮换不会启用已停用调用方。`disable --client-id ...` 立即阻止后续调用。

上线检查：

1. 默认空间和共享生产空间登记正确，目录与实际 TAG/EDGE 一致。
2. 类型枚举需 TAG/EDGE 索引，创建后执行对应 REBUILD 并确认完成。本版缺索引返回 503，**不再自动 MATCH 全扫**。索引 DDL 由运维执行，本 API 不创建索引。
3. TRS 定制版实际执行 LOOKUP 的 src/dst/rank 投影、管道排序与过滤查询成功；在小页上逐项联调，特别验证平行边、自环、悬挂边和含斜杠/引号的 VID。
4. 共用进程/事件循环图预算，默认 16 执行并发、64 排队、等待最多 10 秒，可用 GRAPH_EXEC_* 环境变量调整。它不是分布式全局限流或每业务方配额。
5. 每条 read 查询 HTTP 超时为 20 秒；附端点实体会分批多次查询，统计采用客户端配置超时，所以**整个接口不承诺 20 秒完成**。需结合网关超时和实测页大小设置调用方超时。大类排序仍有成本，大类型仍可能超时，返回行数限制不等于执行扫描量限制。
6. 3 个接口都测试正常密钥、错误密钥、缺项、过期、停用、scope 不足和无身份请求；确认统一用户中心登录兼容。部署前运行新增容器契约测试；单元测试不代替真实 TRS 和公网验收。

与原 3 接口相比：路径及原主要字段保留；新增游标/hasMore/关系标识/rank/types；total 未知时改为 -1；不再依靠 total 判断终点；不再无索引自动全扫。旧调用方需同步分页结束判断。项目关系 POST `/api/v1/kg-service/project-relations/query` 的数据契约不受影响。
