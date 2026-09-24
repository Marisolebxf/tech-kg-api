# 项目关系查询接口

**项目关系查询接口**** **

分页查询「项目—关系—关联实体」记录，供外部业务系统调用。调用方无需了解图空间、节点 VID、边方向或 nGQL，也不能通过本接口执行任意图查询。

## **1\. 接口地址**

|HTTP<br>POST /api/v1/kg\-service/project\-relations/query<br>Content\-Type: application/json|
|---|

|环境|地址|
|---|---|
|公网（网关）|https://edu\.itic\-sci\.com/bkg\_zpt/api/v1/kg\-service/project\-relations/query|

## **2\. 认证**

外部业务系统使用本系统分配的 client\_id 和 API Key，每个请求同时携带以下两个 Header：

|HTTP<br>X\-Client\-Id: \<client\_id\><br>X\-API\-Key: \<api\_key\><br>Content\-Type: application/json|
|---|

- 接入前向本系统管理员提供业务方名称，由管理员分配 client\_id、API Key 和有效期。调用方无需登录用户中心，应在后端保存凭证并随请求发送。原始 Key 仅在创建或轮换时显示一次，数据库仅保存 SHA\-256 哈希值。

- 默认有效期为 90 天，以管理员签发为准。过期前联系管理员轮换；轮换后旧 Key 立即失效，停用后不能调用。凭证只授予 project\-relations:read 权限，仅支持此项目关系查询接口；不能使用 TRSGraph 服务的内部 API Key。

- 原 Authorization: Bearer \<access\_token\> 及登录 Cookie 继续兼容。携带 X\-Client\-Id 或 X\-API\-Key 任意一个 Header 即优先校验 API Key；缺项或校验失败不会回退到 Bearer/Cookie。正式接入应启用 AUTH\_ENABLED=true，不依赖测试环境的关闭登录配置。

修订说明：本稿补充 API Key 接入方式，待对应后端代码部署并完成验收后生效；不代表当前测试环境已经启用。

## **3\. 请求参数**

请求体为 JSON 对象，**必传**（没有任何筛选时也至少传空对象 \{\}）。所有字段均可选：

|字段|类型|默认值|约束|说明|
|---|---|---|---|---|
|keyword|string|不筛选|≤256 字符|项目名称的子串模糊匹配（Project\.title CONTAINS）|
|relationTypes|string\[\]|\[\] = 全部|≤5 个，重复自动去重|关系类型白名单|
|pageSize|integer|100|1～200|每页返回的关系记录条数|
|cursor|string|不翻页|≤2048 字符|翻页游标，原样传回上一页的 nextCursor，不要自行构造或修改|

规则：

- 空字符串（去空格后）视为未传。

- **不传任何筛选参数（空对象 ****\{\}****）= 查询全部项目的全部关系**：按默认
pageSize=100 返回第一页，之后用 nextCursor 翻页，直到 hasMore=false
即遍历完全量数据。

- 结果排序固定为：项目 id → 关系类型 → 关联实体 id。翻页基于偏移量，遍历期间
图数据若有增删，可能出现少量重复或遗漏，对一致性敏感的调用应重查核对。

参数输入示例：

|参数|示例值|含义|
|---|---|---|
|keyword|"人工智能"|项目名称中包含「人工智能」的项目|
|relationTypes|\[\]|全部五种关系|
|relationTypes|\["LEADS"\]|只查项目负责人关系|
|relationTypes|\["LEADS", "HAS\_OUTPUT"\]|负责人 \+ 产出成果|
|pageSize|20|每页 20 条|
|cursor|"eyJ2IjoxLCJvZmZzZXQiOjEwMC\.\.\."|上一页响应里 nextCursor 的值，原样回传|

允许的 relationTypes 取值：

|类型|中文名称|关联实体类型|
|---|---|---|
|FUNDED\_BY|项目资助机构|Organization|
|LEADS|项目负责人|Person|
|HAS\_PARTICIPANT|项目参与人|Person|
|HAS\_KEYWORD|项目关键词|Keyword|
|HAS\_OUTPUT|项目产出成果|Paper、Patent、Report|

## **4\. 请求示例**

（1）查询全部项目关系（第一页，其余字段全部走默认）：

|JSON<br>\{\}|
|---|

（2）按项目名称模糊查询，只看负责人和产出成果：

|JSON<br>\{"keyword": "人工智能", "relationTypes": \["LEADS", "HAS\_OUTPUT"\], "pageSize": 50\}|
|---|

（3）只查某一种关系：

|JSON<br>\{"relationTypes": \["FUNDED\_BY"\], "pageSize": 10\}|
|---|

（4）翻页取下一页（cursor 填上一页响应的 nextCursor 原值）：

|JSON<br>\{"relationTypes": \[\], "pageSize": 100, "cursor": "eyJ2IjoxLCJvZmZzZXQiOjEwMC4uLg"\}|
|---|

## **5\. 成功响应**

HTTP 200。items 的每个元素是一条关系记录；**分页单位是关系记录，不是项目**
——一个项目有 9 条关系就会占 9 条记录。接口不返回总条数，翻页终点以
hasMore=false 为准。

|JSON<br>\{<br>  "code": 200,<br>  "success": true,<br>  "data": \{<br>    "items": \[<br>      \{<br>        "project": \{<br>          "id": "project\_123",<br>          "projectNumber": "2026ABC001",<br>          "title": "人工智能关键技术研究",<br>          "projectSource": "zh\_project",<br>          "projectLevel": "国家级",<br>          "approvalYear": "2026",<br>          "researchPeriod": "2026\-2028"<br>        \},<br>        "relation": \{<br>          "type": "LEADS",<br>          "name": "项目负责人",<br>          "direction": "out",<br>          "properties": \{"confidence": 1\.0\}<br>        \},<br>        "relatedEntity": \{<br>          "id": "person\_456",<br>          "type": "Person",<br>          "name": "张三",<br>          "properties": \{\}<br>        \}<br>      \}<br>    \],<br>    "pageSize": 100,<br>    "nextCursor": "eyJ2IjoxLCJvZmZzZXQiOjEwMC4uLg",<br>    "hasMore": true<br>  \},<br>  "msg": "success"<br>\}|
|---|

字段说明：

|字段|说明|
|---|---|
|data\.pageSize|本页条数上限（回显请求值）|
|data\.nextCursor|下一页游标；hasMore=false 时为空字符串，无需再传|
|data\.hasMore|是否还有下一页|
|project\.id、relatedEntity\.id|图库内部 ID，无业务含义，仅用于展示或去重，不要解析其内容|
|relation\.direction|恒为 "out"（项目 → 关联实体）|
|relation\.properties|白名单关系属性，见下；未列出的关系属性一律不返回|
|relatedEntity\.properties|恒为空对象|

relation\.properties 白名单：FUNDED\_BY → funded\_amount / fund\_category /
confidence；LEADS / HAS\_PARTICIPANT / HAS\_KEYWORD → confidence；
HAS\_OUTPUT → output\_type / output\_title / output\_identifier / confidence。

无数据时：

|JSON<br>\{"code": 200, "success": true, "data": \{"items": \[\], "pageSize": 100, "nextCursor": "", "hasMore": false\}, "msg": "success"\}|
|---|

## **6\. 错误响应**

**重要：参数校验失败时 HTTP 状态码仍为 200，失败信息在响应体的 code / success 字段里（平台统一响应壳）。调用方判断成败必须看 success（或 code），不能只看 HTTP 状态码。其余错误（400 / 401 / 403 / 502 / 503）是真实 HTTP 状态码，响应体为 \{"detail": "\.\.\."\} 格式。**

|场景|HTTP 状态码|响应体格式|
|---|---|---|
|参数校验失败：非法关系类型、pageSize 越界、缺请求体等|**200**|统一响应壳 code=422|
|游标格式无效；或修改了筛选条件后仍沿用旧游标|400|\{"detail": "游标格式无效"\}|
|未认证、Token 缺失或过期；API Key Header 缺项、不匹配、过期或停用|401|\{"detail": "\.\.\."\}，补齐凭证或联系管理员重新签发|
|图数据服务不可用或查询失败|502|\{"detail": "图数据服务暂时不可用，请稍后重试"\}|
|凭证有效但缺少 project\-relations:read 权限|403|\{"detail": "\.\.\."\}，联系管理员核对授权|
|API Key 认证数据库不可用|503|\{"detail": "\.\.\."\}，稍后重试并联系运维；不会放行|

## **7\. 完整 curl 示例**

|Bash<br>curl \-X POST \\<br>  'https://edu\.itic\-sci\.com/bkg\_zpt/api/v1/kg\-service/project\-relations/query' \\<br>  \-H 'X\-Client\-Id: \<client\_id\>' \\<br>  \-H 'X\-API\-Key: \<api\_key\>' \\<br>  \-H 'Content\-Type: application/json' \\<br>  \-d '\{"keyword": "人工智能", "relationTypes": \[\], "pageSize": 100\}'|
|---|

