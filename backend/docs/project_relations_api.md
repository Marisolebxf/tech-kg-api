# 项目关系查询接口

分页查询「项目—关系—关联实体」记录，供外部业务系统调用。调用方无需了解图空间、节点 VID、边方向或 nGQL，也不能通过本接口执行任意图查询。

**一条记录 = 一个项目的一种关系指向的一个关联实体**。例如某项目的「项目负责人」是 1 条记录，「项目资助机构」是另 1 条记录；一个项目有 9 条关系就会有 9 条记录。

## 1. 接口地址

- 方式：`POST`（请求体为 JSON，`Content-Type: application/json`）
- 路径：`/api/v1/kg-service/project-relations/query`

| 环境 | 地址 |
|---|---|
| 公网（网关） | `https://edu.itic-sci.com/bkg_zpt/api/v1/kg-service/project-relations/query` |

## 2. 认证

外部业务系统使用本系统分配的 client_id 和 API Key，每个请求同时携带以下两个 Header：

```
X-Client-Id: <client_id>
X-API-Key: <api_key>
Content-Type: application/json
```

- 接入前向本系统管理员提供业务方名称，由管理员分配 client_id、API Key 和有效期。调用方无需登录用户中心，应在后端保存凭证并随请求发送。原始 Key 仅在创建或轮换时显示一次，数据库仅保存 SHA-256 哈希值。
- 默认有效期为 90 天，以管理员签发为准。过期前联系管理员轮换；轮换后旧 Key 立即失效，停用后不能调用。凭证只授予 project-relations:read 权限，仅支持此项目关系查询接口；不能使用 TRSGraph 服务的内部 API Key。
- 原 `Authorization: Bearer <access_token>` 及登录 Cookie 继续兼容。携带 X-Client-Id 或 X-API-Key 任意一个 Header 即优先校验 API Key；缺项或校验失败不会回退到 Bearer/Cookie。正式接入应启用 AUTH_ENABLED=true，不依赖测试环境的关闭登录配置。

> 修订说明：本稿补充 API Key 接入方式，待对应后端代码部署并完成验收后生效；不代表当前测试环境已经启用。

## 3. 请求参数

### 3.1 参数总则（先读这个）

1. **请求体必传**：没有任何筛选时，也要传一个空 JSON 对象 `{}`。
2. **空对象 `{}` = 查询全部项目的全部关系**：按默认 pageSize=100 返回第一页，之后用响应里的 nextCursor 翻页，直到 hasMore=false 即遍历完全量数据。
3. **所有字段都是可选的**：不传哪个字段，就按该字段的默认值处理（见下表）。
4. **空字符串（去空格后）视为未传**。`"keyword": ""` 和不传 keyword 效果相同。
5. **不允许传下表之外的字段**：请求体里出现未知字段会直接被判为参数校验失败（code=422），请只传下表列出的 4 个字段。
6. 结果排序固定为：项目 id → 关系类型 → 关联实体 id。翻页基于偏移量，遍历期间图数据若有增删，可能出现少量重复或遗漏，对一致性敏感的调用应重查核对。

### 3.2 参数说明

| 字段 | 类型 | 必填 | 默认值 | 约束 | 含义 | 示例 |
|---|---|---|---|---|---|---|
| keyword | string | 否 | 不筛选（查全部） | ≤256 字符 | 按项目名称做子串模糊匹配：项目名称中**包含**该字符串的项目命中（不分词，大小写敏感） | `"人工智能"` |
| relationTypes | string 数组 | 否 | `[]`（= 全部五种关系） | 最多 5 个；重复值自动去重；只允许 3.3 节列出的取值 | 关系类型白名单：只返回这些类型的关系记录 | `["LEADS", "HAS_OUTPUT"]` |
| pageSize | integer | 否 | 100 | 1～200 | 每页返回的**关系记录**条数上限（注意单位是关系记录，不是项目） | `20` |
| cursor | string | 否 | 不填（= 第一页） | ≤2048 字符 | 翻页游标。取上一页响应里 `data.nextCursor` 的值**原样回传**，不要自行构造、拼接或修改 | `"eyJ2IjoxLCJvZmZzZXQiOjEwMC4uLg"` |

### 3.3 relationTypes 允许的取值

| 类型 | 中文名称 | 关联实体类型 | 这条记录表达的含义 |
|---|---|---|---|
| FUNDED_BY | 项目资助机构 | Organization（机构） | 该项目由该机构资助。**唯一携带金额字段 funded_amount 的关系类型**（单位见 4.4 节） |
| LEADS | 项目负责人 | Person（人员） | 该人员是该项目的负责人 |
| HAS_PARTICIPANT | 项目参与人 | Person（人员） | 该人员是该项目的参与人 |
| HAS_KEYWORD | 项目关键词 | Keyword（关键词） | 该关键词是该项目的关键词 |
| HAS_OUTPUT | 项目产出成果 | Paper / Patent / Report（论文/专利/报告） | 该成果由该项目产出 |

不传 relationTypes 或传空数组 `[]` = 以上五种全部返回。

### 3.4 请求示例

（1）**查询全部项目关系**（第一页，其余字段全部走默认）——最简调用：

```json
{}
```

（2）按项目名称模糊查询，只看负责人和产出成果：

```json
{"keyword": "人工智能", "relationTypes": ["LEADS", "HAS_OUTPUT"], "pageSize": 50}
```

（3）只查项目资助机构关系（要看金额就用这个类型）：

```json
{"relationTypes": ["FUNDED_BY"], "pageSize": 10}
```

（4）翻页取下一页（cursor 填上一页响应 `data.nextCursor` 的原值，**不要改动**）：

```json
{"relationTypes": [], "pageSize": 100, "cursor": "eyJ2IjoxLCJvZmZzZXQiOjEwMC4uLg"}
```

> 注意：翻页时 keyword / relationTypes / pageSize 必须与上一页保持一致，只增加 cursor。改了筛选条件仍沿用旧游标会返回 400（游标与筛选条件不一致）。

## 4. 成功响应

HTTP 200。**分页单位是关系记录，不是项目**——一个项目有 9 条关系就会占 9 条记录。接口不返回总条数，翻页终点以 hasMore=false 为准。

### 4.1 响应示例

```json
{
  "code": 200,
  "success": true,
  "data": {
    "items": [
      {
        "project": {
          "id": "project_123",
          "projectNumber": "81101234",
          "title": "人工智能关键技术研究",
          "projectSource": "国家自然科学基金(NSFC)",
          "projectLevel": "国家级",
          "approvalYear": "2018",
          "researchPeriod": "2019-01-01 至 2022-12-31"
        },
        "relation": {
          "type": "FUNDED_BY",
          "name": "项目资助机构",
          "direction": "out",
          "properties": {
            "funded_amount": 62.0,
            "fund_category": "面上项目",
            "confidence": 1.0
          }
        },
        "relatedEntity": {
          "id": "organization_456",
          "type": "Organization",
          "name": "XX大学",
          "properties": {}
        }
      },
      {
        "project": {
          "id": "project_123",
          "projectNumber": "81101234",
          "title": "人工智能关键技术研究",
          "projectSource": "国家自然科学基金(NSFC)",
          "projectLevel": "国家级",
          "approvalYear": "2018",
          "researchPeriod": "2019-01-01 至 2022-12-31"
        },
        "relation": {
          "type": "HAS_OUTPUT",
          "name": "项目产出成果",
          "direction": "out",
          "properties": {
            "output_type": "journal_article",
            "output_title": "A Survey of Key Technologies in Artificial Intelligence",
            "output_identifier": "10.1000/example.doi",
            "confidence": 1.0
          }
        },
        "relatedEntity": {
          "id": "paper_789",
          "type": "Paper",
          "name": "A Survey of Key Technologies in Artificial Intelligence",
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

### 4.2 外层与分页字段说明

| 字段 | 类型 | 含义 |
|---|---|---|
| code | integer | 200 = 成功；422 = 参数校验失败（见第 5 节，此时 HTTP 状态码仍是 200） |
| success | boolean | 是否成功。**判断成败以本字段（或 code）为准，不能只看 HTTP 状态码** |
| msg | string | 提示信息，成功时为 "success" |
| data.pageSize | integer | 本页条数上限（回显请求值） |
| data.items | array | 关系记录列表，每个元素结构见下表 |
| data.nextCursor | string | 下一页游标；**hasMore=false 时为空字符串**，无需再传 |
| data.hasMore | boolean | 是否还有下一页。翻页循环：请求带 cursor → 拿 nextCursor → 直到 hasMore=false |

### 4.3 items 内记录字段说明

| 字段 | 类型 | 含义 |
|---|---|---|
| project.id | string | 项目在图库中的内部 ID，无业务含义，仅用于展示或去重，不要解析其内容 |
| project.projectNumber | string | 项目编号（如基金申请编号），可能为空字符串 |
| project.title | string | 项目名称 |
| project.projectSource | string | 项目数据来源名称，如 `"国家自然科学基金(NSFC)"`（国内项目）、`"美国国家科学基金(NSF)"`（国外项目）。**同时是判断 funded_amount 金额单位的依据，见 4.4 节** |
| project.projectLevel | string | 项目级别，如 `"国家级"`，可能为空字符串 |
| project.approvalYear | string | 批准年度，4 位年份字符串，如 `"2018"`，可能为空字符串 |
| project.researchPeriod | string | 研究周期，如 `"2019-01-01 至 2022-12-31"`，可能为空字符串 |
| relation.type | string | 关系类型编码，取值同 3.3 节 |
| relation.name | string | 关系类型中文名称，如 `"项目资助机构"` |
| relation.direction | string | 恒为 `"out"`（方向固定为：项目 → 关联实体） |
| relation.properties | object | 关系属性，**只返回 4.4 节列出的白名单字段**；源数据缺失的属性不出现 |
| relatedEntity.id | string | 关联实体在图库中的内部 ID，无业务含义，仅用于展示或去重 |
| relatedEntity.type | string | 关联实体类型：`Organization` / `Person` / `Keyword` / `Paper` / `Patent` / `Report` |
| relatedEntity.name | string | 关联实体名称（机构名 / 人名 / 关键词 / 论文·专利·报告标题） |
| relatedEntity.properties | object | 恒为空对象 `{}`，当前不返回实体属性 |

### 4.4 relation.properties 各关系类型的字段说明

**FUNDED_BY（项目资助机构）**——唯一含金额的关系：

| 字段 | 类型 | 含义 |
|---|---|---|
| funded_amount | number | 项目获得的**资助经费金额**（立项时批复的受资助金额，不是项目合同金额、预算总额或投资额）。**单位不是统一的，按项目来源区分：国内项目为万元（人民币），国外项目为美元，见下方单位说明**。源数据缺失时不返回该字段 |
| fund_category | string | 基金类别。国内项目如 `"面上项目"`、`"青年科学基金项目(C类)"`、`"重点项目"`；国外项目如 `"Cooperative Agreement"`、`"Continuing grant"` |
| confidence | number | 关系可信度，0～1，越大越可信 |

**funded_amount 单位说明**——单位按 `items[].project.projectSource`（项目数据来源）判断；接口不做单位换算、也不做汇率换算，返回值中不含币种字段，请调用方按来源自行判断单位：

| 项目来源（projectSource 实际取值） | funded_amount 单位 | 精度 | 示例 |
|---|---|---|---|
| 国内项目，如 `"国家自然科学基金(NSFC)"` | **万元（人民币）** | 最多 2 位小数（0.01 万元 = 100 元） | `62.0` = 62 万元人民币 |
| 国外项目，如 `"美国国家科学基金(NSF)"` | **美元（USD）** | 整数，无小数 | `24478773` = 24,478,773 美元 |

**LEADS / HAS_PARTICIPANT / HAS_KEYWORD（负责人 / 参与人 / 关键词）**：

| 字段 | 类型 | 含义 |
|---|---|---|
| confidence | number | 关系可信度，0～1，越大越可信 |

**HAS_OUTPUT（项目产出成果）**：

| 字段 | 类型 | 含义 |
|---|---|---|
| output_type | string | 成果类型编码：`journal_article`（期刊论文）/ `conference_paper`（会议论文）/ `degree_paper`（学位论文）/ `patent`（专利）/ `report`（报告） |
| output_title | string | 成果标题 |
| output_identifier | string | 成果唯一标识（论文 DOI、专利号等），可能为空字符串 |
| confidence | number | 关系可信度，0～1，越大越可信 |

### 4.5 无数据时

```json
{"code": 200, "success": true, "data": {"items": [], "pageSize": 100, "nextCursor": "", "hasMore": false}, "msg": "success"}
```

## 5. 错误响应

**重要：参数校验失败时 HTTP 状态码仍为 200，失败信息在响应体的 code / success 字段里（平台统一响应壳）。调用方判断成败必须看 success（或 code），不能只看 HTTP 状态码。** 其余错误（400 / 401 / 403 / 502 / 503）是真实 HTTP 状态码，响应体为 `{"detail": "..."}` 格式。

| 场景 | HTTP 状态码 | 响应体格式 |
|---|---|---|
| 参数校验失败：非法关系类型、pageSize 越界、请求体缺失、含未知字段等 | **200** | 统一响应壳 code=422 |
| 游标格式无效；或修改了筛选条件后仍沿用旧游标 | 400 | `{"detail": "游标格式无效"}` |
| 未认证、Token 缺失或过期；API Key Header 缺项、不匹配、过期或停用 | 401 | `{"detail": "..."}`，补齐凭证或联系管理员重新签发 |
| 凭证有效但缺少 project-relations:read 权限 | 403 | `{"detail": "..."}`，联系管理员核对授权 |
| 图数据服务不可用或查询失败 | 502 | `{"detail": "图数据服务暂时不可用，请稍后重试"}` |
| API Key 认证数据库不可用 | 503 | `{"detail": "..."}`，稍后重试并联系运维；不会放行 |

## 6. 完整 curl 示例

```bash
curl -X POST \
  'https://edu.itic-sci.com/bkg_zpt/api/v1/kg-service/project-relations/query' \
  -H 'X-Client-Id: <client_id>' \
  -H 'X-API-Key: <api_key>' \
  -H 'Content-Type: application/json' \
  -d '{"keyword": "人工智能", "relationTypes": [], "pageSize": 100}'
```

> 示例说明：该请求按项目名称模糊匹配「人工智能」，返回全部五种关系的第一页（每页 100 条）。把 `-d` 换成 `'{}'` 即查询全量数据的第一页。
