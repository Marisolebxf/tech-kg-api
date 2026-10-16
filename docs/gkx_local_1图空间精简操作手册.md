# gkx_local_1 图空间精简操作手册（3 实体 3 关系 · 每步详解）

> **定位**：只保留 **3 个实体 + 3 个关系**，把"建 Schema → 绑来源表 → 传脚本 → 跑抽取 → 对账"每一步的可复制请求与核对点写透。
> **口径**：2026-10-16 活栈实测同步（绑定 157 条 / 脚本 46 个 / 图内 873,193 点 · 617,322 边）。
> **全量参考**：《gkx_local_1图空间全链路测试手册》（50 Schema 全清单）+ 物料包 `docs/gkx_local_1_materials/`。两份材料为 2026-10-15 快照（152 条绑定），与活栈的完整差异清单见本册[附录](#附-2026-10-16-活栈-vs-物料包差异清单)。

## 0. 环境与入口

| 项目 | 值 |
|---|---|
| 栈 | yunfei3：web `http://localhost:8093`，api `http://localhost:8004`（AUTH 关，直连免登录） |
| 图空间 | `gkx_local_1` |
| 数据源 | `MYSQL-DWD-LOCAL` → 本机 30306 库 `gkx_dwd_local`（72 表本地镜像） |
| 图库 | TRS 定制 Nebula，经 trs-graph `http://localhost:8090`（`X-API-Key: ysukeg`，`X-Graph-Space: gkx_local_1`） |
| 控制库 | 30306 `techkg_control_yunfei3`（schema/绑定/脚本/任务/执行历史） |
| 水位库 | 30306 `techkg_global.kg_script_watermark`（**updated_at 是 UTC**，与控制库 CST 差 8 小时） |

本册所有核对命令均为**只读**（SELECT / GET / SHOW STATS / FETCH），不会改动图与库。

## 1. 选样一览

| Schema | 方向 | 身份键 | 属性(必/核/溯) | 来源绑定 | 抽取脚本 | 10-16 变化 |
|---|---|---|---|---|---|---|
| `Paper` 论文 | 实体 | id | 32 (5/18/9) | **3** | paper_entity_step.py | **新增 pos2** `dwd_scholar_papers`；脚本热修 |
| `Journal` 期刊 | 实体 | id | 33 (5/18/10) | 2 | journal_entity_step.py | 无 |
| `IndustryChain` 产业链 | 实体 | id | 17 (5/4/8) | 1 | industry_chain_entity_step.py | 无 |
| `PUBLISHED_IN` 论文发表 | Paper→Journal | - | 14 (3/8/3) | 2 | published_in_relation_step.py | 无 |
| `AUTHORED_BY` 论文署名 | Paper→Person | - | 12 (3/9/0) | **4** | authored_by_relation_step.py | **新增 pos2/pos3**（scholar 关系两表） |
| `BELONGS_TO_NODE` 企业归属链节点 | Organization→IndustryNode | - | 10 (3/4/3) | 1 | belongs_to_node_relation_step.py | 无 |

选样覆盖：querySql 三种形态（裸表 / 投影裁列 / 语义映射重建）、双语源（zh+en）、多源关系、JSON 展开重 SQL，以及 10-16 全部新增绑定类型。关系端点里 `Person`/`Organization`/`IndustryNode` 不在选样（全量定义在物料包 `schemas.json`），本栈已灌好存量。

**选样当前实测（2026-10-16）**：

| 类型 | 图内数量 | 源表过滤后行数合计 |
|---|---|---|
| Paper 点 | 742,106 | 742,114（2,000+2,000+738,114） |
| Journal 点 | 2,134 | 4,207（2,081+2,126，按 publication_id 去重落图） |
| IndustryChain 点 | 2 | 2 |
| PUBLISHED_IN 边 | 4,000 | 4,000 |
| AUTHORED_BY 边 | 220,822 | 303,167（7,906+12,977+210,464+71,820，端点/去重/灰区扣留） |
| BELONGS_TO_NODE 边 | 2,943 | 2,943（精确一致） |

对账方法与口径见 [Step 5](#5-step-5-验收对账)。

## 2. Step 1 建 Schema

接口：`POST /api/v1/schema-management/schemas/entities`（实体）、`/schemas/relations`（关系）。属性四要素 `name/dataType/required/rule/category`（category ∈ core|required|provenance）。实体只需传**业务属性**——平台自动注入 5 个必填审计列（`id/name/create_time/update_time/source_table`）与 vid/溯源列，显式传入同名属性会去重合并（同名强制 required）。建完核对 `ddlStatus=succeeded`。

**实体完整范例：IndustryChain**（17 属性全量，与活栈一致）：

```bash
curl -s -X POST http://localhost:8004/api/v1/schema-management/schemas/entities \
  -H 'Content-Type: application/json' -d '{
  "schemaKey": "tag-industrychain", "name": "IndustryChain", "label": "产业链",
  "description": "产业链主链", "identityKey": "id", "graphSpace": "gkx_local_1",
  "properties": [
    {"name":"id","dataType":"string","required":true},
    {"name":"name","dataType":"string","required":true},
    {"name":"create_time","dataType":"string","required":true},
    {"name":"update_time","dataType":"string","required":true},
    {"name":"source_table","dataType":"string","required":true},
    {"name":"chain_code","dataType":"string"},
    {"name":"chain_name","dataType":"string"},
    {"name":"ingest_batch","dataType":"string"},
    {"name":"ingest_time","dataType":"string"},
    {"name":"vid","dataType":"string"},
    {"name":"source_system","dataType":"string"},
    {"name":"source_record_id","dataType":"string"},
    {"name":"source_url","dataType":"string"},
    {"name":"source_update_time","dataType":"string"},
    {"name":"confidence","dataType":"string"},
    {"name":"match_method","dataType":"string"},
    {"name":"match_evidence","dataType":"string"}
  ]}'
```

**关系完整范例：BELONGS_TO_NODE**（10 属性；`sourceSchemaId`/`targetSchemaId` 用两端实体的真实 id）：

```bash
curl -s -X POST http://localhost:8004/api/v1/schema-management/schemas/relations \
  -H 'Content-Type: application/json' -d '{
  "schemaKey": "edge-belongs-to-node", "name": "BELONGS_TO_NODE", "label": "企业归属产业链节点",
  "description": "企业挂到产业链节点", "graphSpace": "gkx_local_1",
  "sourceSchemaId": "<Organization 的 id>", "targetSchemaId": "<IndustryNode 的 id>",
  "properties": [
    {"name":"create_time","dataType":"string","required":true},
    {"name":"update_time","dataType":"string","required":true},
    {"name":"source_table","dataType":"string","required":true},
    {"name":"chain_score","dataType":"double"},
    {"name":"source_record_id","dataType":"string"},
    {"name":"ingest_batch","dataType":"string"},
    {"name":"ingest_time","dataType":"string"},
    {"name":"confidence","dataType":"string"},
    {"name":"match_method","dataType":"string"},
    {"name":"match_evidence","dataType":"string"}
  ]}'
```

其余 4 个选样 Schema 的 body 同法（`Paper` key=`tag-paper` 32 属性、`Journal` key=`tag-journal` 33 属性、`PUBLISHED_IN` key=`edge-published-in` 14 属性、`AUTHORED_BY` key=`edge-authored-by` 12 属性）——物料包 `schemas.json` 每条的 properties 就是现成素材。核对：`GET /api/v1/schema-management/schemas/{id}`。

## 3. Step 2 绑来源表

接口：`PUT /api/v1/schema-management/schemas/{id}/sources`，body `{"sources":[...]}`，**数组顺序即 position，整组全量替换**。字段：`datasourceId/databaseName/tableName/pkColumn/timeColumn/querySql`；querySql 缺省（裸表）= 全列直读，给了 = 只读 SQL。

querySql 三种形态：**① 投影裁列**（控 Temporal 历史体积 + `is_deleted=0` 过滤，最常见）、**② 语义映射重建**（列名整体换算）、**③ 恒等占位**（`DataSource` 绑 `placeholder`：`SELECT 1 AS id, '1970-01-01 00:00:01' AS wm_col`，本册选样不含）。

以下 6 组 body 与活栈同义（`{id}` 换成 Step 1 建出的 id）。含 querySql 的（SQL 里有单引号/换行）先落 JSON 文件再 `curl -d @` 引用，避免 shell 转义吃字符；querySql 内换行写作 `\n`（JSON 转义，灌入后即真换行）。

**Paper（3 绑定：双语裸表 + 新增 scholar_papers 裁列）**：

```bash
cat > bind_paper.json <<'EOF'
{"sources":[
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_en_paper",
   "pkColumn":"dwd_id","timeColumn":"updated_time"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_zh_paper",
   "pkColumn":"pk_id","timeColumn":"updated_time"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_scholar_papers",
   "pkColumn":"dwd_id",
   "querySql":"SELECT dwd_id, id, doi, zh_name, en_name, paper_url, publication_en_name AS publication_id, DATE_FORMAT(cover_date_start, '%Y') AS cover_year_start, updated_time FROM dwd_scholar_papers WHERE is_deleted = 0"}
]}
EOF
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/sources \
  -H 'Content-Type: application/json' -d @bind_paper.json
```

> pos2 是 10-16 新增：一表扛 73.8 万论文（`is_deleted=0` 后 738,114 行），`publication_en_name` 映射成 `publication_id`、`cover_date_start` 折成年。

**Journal（2 绑定：双语裸表，无 SQL）**：

```bash
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/sources \
  -H 'Content-Type: application/json' -d '{"sources":[
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_zh_journal",
   "pkColumn":"pk_id","timeColumn":"updated_time"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_en_journal",
   "pkColumn":"dwd_id","timeColumn":"updated_time"}
]}'
```

**IndustryChain（1 绑定：语义映射重建，形态②）**：

```bash
cat > bind_chain.json <<'EOF'
{"sources":[
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_industry_chain_info",
   "pkColumn":"row_pk",
   "querySql":"SELECT t.pk_id AS row_pk,\n       t.industry_code AS chain_code, t.industry_name AS chain_name\nFROM dwd_industry_chain_info t\nWHERE t.is_deleted = 0 AND CHAR_LENGTH(t.industry_code) = 7"}
]}
EOF
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/sources \
  -H 'Content-Type: application/json' -d @bind_chain.json
```

**PUBLISHED_IN（2 绑定：裸表，边列直接取自论文表的期刊外键）**：

```bash
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/sources \
  -H 'Content-Type: application/json' -d '{"sources":[
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_zh_paper",
   "pkColumn":"pk_id","timeColumn":"updated_time"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_en_paper",
   "pkColumn":"dwd_id","timeColumn":"updated_time"}
]}'
```

**AUTHORED_BY（4 绑定：形态①裁列；pos2/pos3 是 10-16 新增）**：

```bash
cat > bind_authored.json <<'EOF'
{"sources":[
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_zh_author",
   "pkColumn":"pk_id",
   "querySql":"SELECT *, CONCAT(paper_id, '__', author_id) AS row_id\nFROM dwd_zh_author WHERE is_deleted = 0"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_en_author",
   "pkColumn":"dwd_id",
   "querySql":"SELECT *, CONCAT(paper_id, '__', author_id) AS row_id\nFROM dwd_en_author WHERE is_deleted = 0"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_scholar_paper_relation",
   "pkColumn":"dwd_id",
   "querySql":"SELECT r.dwd_id, r.paper_id, r.scholar_id AS author_id, r.updated_time FROM dwd_scholar_paper_relation r JOIN dwd_scholar_papers p ON r.paper_id = p.id AND p.is_deleted = 0 JOIN dwd_scholar s ON r.scholar_id = s.scholar_id AND s.status = 1 WHERE r.is_deleted = 0"},
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_scholar_paper_relation_element",
   "pkColumn":"row_id",
   "querySql":"SELECT CONCAT(r.paper_id, '__', r.scholar_id) AS row_id, r.paper_id, r.scholar_id AS author_id, r.update_time FROM dwd_scholar_paper_relation_element r JOIN dwd_scholar_papers p ON r.paper_id = p.id AND p.is_deleted = 0 WHERE r.status = 1"}
]}
EOF
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/sources \
  -H 'Content-Type: application/json' -d @bind_authored.json
```

> 双表口径差异：本地表 `dwd_scholar_paper_relation` 软删列是 `is_deleted`、scholar 在档判 `s.status=1`；element 库镜像表 `..._element` 用 `r.status=1` 且无 `updated_time`（有 `update_time`，无时间后缀）。JOIN `dwd_scholar_papers` 保证只出图内存在的论文。过滤后行数：7,906 / 12,977 / 210,464 / 71,820。

**BELONGS_TO_NODE（1 绑定：JSON 数组展开重 SQL，逐段解读）**：

```bash
cat > bind_btn.json <<'EOF'
{"sources":[
  {"datasourceId":"MYSQL-DWD-LOCAL","databaseName":"gkx_dwd_local","tableName":"dwd_org_industry_chain_dtl",
   "pkColumn":"row_pk",
   "querySql":"SELECT t.dwd_id * 8 + i.ix AS row_pk,\n       o.org_id AS antitypic, v.industry_code AS node_id,\n       NULL AS chain_score\nFROM dwd_org_industry_tags t\nJOIN dwd_org_base_info o\n  ON o.name_cn = t.company_name COLLATE utf8mb4_general_ci\nJOIN (SELECT 0 AS ix UNION SELECT 1 UNION SELECT 2 UNION SELECT 3\n      UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7) i\n  ON t.industry_link_code LIKE '[%'\n AND JSON_VALID(REPLACE(t.industry_link_code, '\\'', '\"'))\n AND JSON_EXTRACT(REPLACE(t.industry_link_code, '\\'', '\"'), CONCAT('$[', i.ix, ']')) IS NOT NULL\nJOIN dwd_industry_chain_info v\n  ON v.is_deleted = 0\n AND v.industry_code = JSON_UNQUOTE(\n       JSON_EXTRACT(REPLACE(t.industry_link_code, '\\'', '\"'), CONCAT('$[', i.ix, ']'))\n     )\nWHERE t.is_deleted = 0"}
]}
EOF
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/sources \
  -H 'Content-Type: application/json' -d @bind_btn.json
```

拆解（querySql 与栈上逐字一致；`'\''` 是 SQL 字符串里表示单引号字符本身的写法）：

- 源表 `dwd_org_industry_tags.industry_link_code` 是 `'['a','b',...]` 型**伪 JSON**（单引号）→ `REPLACE` 成双引号再 `JSON_VALID/JSON_EXTRACT`；
- 8 路 `ix` 内联表把数组**纵向展开**成多行（一企业挂多节点），`JSON_EXTRACT(...IS NOT NULL)` 充当 join 条件截断越界下标；
- `t.dwd_id * 8 + i.ix` 合成**行唯一主键** row_pk；`COLLATE utf8mb4_general_ci` 对齐两表排序规则让 name_cn 走索引；
- 终表 `dwd_org_industry_chain_dtl` 名义上是绑定表，实际数据由本 SQL 现算——"绑定表 ≠ 直读表"的极端形态。展开后精确 2,943 行 = 图内边数。

**水位语义**（3 行记住）：裸表按 `timeColumn` 记水位、querySql 绑定走水位/keyset 游标（存 `techkg_global.kg_script_watermark`，`definition_id=schema-extract-tag-/edge-<slug>`、`step_id=source:<绑定id>` 每绑定一行）；每次只读水位后的增量、全批成功才推进；无时间列的绑定首跑全量后无增量可拾，重处理靠 backfill（Schema 详情页「历史数据回填」）或 bump `updated_time`。

## 4. Step 3 传脚本

接口：`PUT /api/v1/schema-management/schemas/{id}/script`，multipart 字段名 `script`，文件名须与登记一致：

```bash
curl -s -X PUT http://localhost:8004/api/v1/schema-management/schemas/{id}/script \
  -F 'script=@docs/gkx_local_1_materials/scripts/industry_chain_entity_step.py'
```

选样 6 个脚本（物料包 `docs/gkx_local_1_materials/scripts/` 均有原文件；均由 `script/tools/build_portable_steps.py` 自包含生成，**勿手改**）：

| 脚本 | 大小(B) | 要点 |
|---|---|---|
| paper_entity_step.py | 7,753 | **10-16 栈上热修**：`publication_year` 回退取 `cover_year_start`（DWD 源表无该列）；物料包已同步 |
| journal_entity_step.py | 7,281 | 按 `publication_id` 去重落图（源表是论文×期刊打平样本） |
| industry_chain_entity_step.py | 6,782 | 7 位行业码 → 链实体 |
| published_in_relation_step.py | 4,859 | 论文行内期刊外键直接出边 |
| authored_by_relation_step.py | 5,237 | 四源统一 `paper_id/author_id` 口径出边 |
| belongs_to_node_relation_step.py | 5,215 | 消费 Step 2 展开好的行 |

脚本契约（与平台 `kg.schema.extract` 管道的唯一接口）：

```python
from kg_sdk import step

@step("industry_chain")     # 步名=函数声明名；入口统一叫 emit
def emit(payload):          # payload: rows(本批源行)+source(绑定元数据)
    return {                # 实体写图必须走 nGQL INSERT VERTEX 语义(平台代写)
        "entities": [{"id": vid, "props": {...}}],
        "edges":    [{"fromId": ..., "toId": ..., "props": {...}}],
        "failures": [{"recordId": ..., "error": ...}],   # 逐行毒行隔离→T_EXTRACT_FAIL 审核案
    }
```

上传后核对（只读）：`GET /schemas/{id}` 的 `script` 字段应有 `filename/sizeBytes/etag`。上传通道本身带语法+入口静态检查与 LLM 审核，被拒会报原因。另注意全空间有 4 个**无脚本**关系（APPLIED_BY/INVENTED_BY/OUTPUT_OF/OWNED_BY，图内边数 0，属设计内）。

## 5. Step 4 跑抽取

建任务：`POST /api/v1/workflow-system/jobs`。chain 型（`schemaIds` 2–20 个**严格串行**，顺序即执行顺序，任一环失败整链 FAILED）；extract 型单 Schema（`schemaId`）。公共字段 `batchSize`(1–5000)、`schedule:{kind:"once"|"cron",timezone}`、`runNow:true` 立即触发。

**选样链**（先实体后关系；实体/关系 id 换成自己空间建出的）：

```bash
curl -s -X POST http://localhost:8004/api/v1/workflow-system/jobs \
  -H 'Content-Type: application/json' -d '{
  "name": "gkx_local_1-精简样例链", "taskType": "chain", "graphSpace": "gkx_local_1",
  "schemaIds": ["<IndustryChain>", "<Journal>", "<Paper>", "<PUBLISHED_IN>", "<AUTHORED_BY>", "<BELONGS_TO_NODE>"],
  "batchSize": 2000, "schedule": {"kind": "once", "timezone": "Asia/Shanghai"}, "runNow": true
}'
```

gkx_local_1 现存三条链（实体链 16 / 关系链A 14 / 关系链B 13，batchSize 2000）+ 逐 Schema 单独触发的执行（`job_id` 为 NULL，走 Schema 维度直触）。**2026-10-16 下午实录**（新增绑定就是这样灌进图的，`techkg_control_yunfei3.workflow_executions`）：

| 时间(CST) | definition | 终态 | 结果 |
|---|---|---|---|
| 14:54:43 | tag-paper | COMPLETED | +738,106 论文（pos2 新绑定） |
| 15:01:19 | tag-person | COMPLETED | Person 30,097→47,116（署名边端点补齐） |
| 15:07:41 | edge-authored-by | **FAILED** | 首跑失败 |
| 15:11:41 | edge-authored-by | COMPLETED | 重试成功：边 18,583→220,822 |
| 15:20:24 | edge-beneficial-owner-of | COMPLETED | 0→6,374 |
| 15:20:44 | edge-actual-controller-of | **ABNORMAL** | 含 1 条失败记录转人工审核——ABNORMAL≠失败，图已写入 50 条 |

语义三则：**幂等**（图写入门是列级 upsert，重跑空读快过不重复写）；**增量**（只有绑了时间列的表拾 `updated_time>水位` 新行）；**失败行**（转 T_EXTRACT_FAIL 审核案，页面一键重跑）。索引重建失败即整链 FAILED（`SCHEMA_EXTRACT_BUILD_INDEX=0` 可显式关）。

## 6. Step 5 验收对账

**① 源侧行数**（只读，30306 直连或页面 SQL 控制台）：

```sql
SELECT COUNT(*) FROM gkx_dwd_local.dwd_zh_paper;                -- 2,000
SELECT COUNT(*) FROM gkx_dwd_local.dwd_en_paper;                -- 2,000
SELECT COUNT(*) FROM gkx_dwd_local.dwd_scholar_papers WHERE is_deleted=0;  -- 738,114
SELECT COUNT(*) FROM gkx_dwd_local.dwd_zh_journal;              -- 2,081
SELECT COUNT(*) FROM gkx_dwd_local.dwd_en_journal;              -- 2,126
SELECT COUNT(*) FROM gkx_dwd_local.dwd_industry_chain_info
 WHERE is_deleted=0 AND CHAR_LENGTH(industry_code)=7;           -- 2
-- AUTHORED_BY 四源过滤行数:7,906 / 12,977 / 210,464 / 71,820(见 Step 2 注)
-- BELONGS_TO_NODE 展开后:2,943(Step 2 SQL 包一层 COUNT 即得)
```

**② 图内计数**（只读；`SHOW STATS` 读最近一次统计作业快照——大改数据后先 `SUBMIT JOB STATS` 再查）：

```bash
curl -s -X POST http://localhost:8090/api/v1/query/read \
  -H 'X-API-Key: ysukeg' -H 'X-Graph-Space: gkx_local_1' -H 'Content-Type: application/json' \
  -d '{"query":"SHOW STATS"}'
```

选样当前值：Paper **742,106** / Journal **2,134** / IndustryChain **2** / PUBLISHED_IN **4,000** / AUTHORED_BY **220,822** / BELONGS_TO_NODE **2,943**（全空间 873,193 点 · 617,322 边）。

**③ 对齐判读**：IndustryChain 与 BELONGS_TO_NODE **精确一致**；Paper 差 8（742,114→742,106，同名消歧 T_LINK 灰案扣留 + 毒行）；Journal 源 4,207 → 图 2,134 是脚本按 `publication_id` 去重的**设计口径**；AUTHORED_BY 源 303,167 → 图 220,822 为端点存在性 + 去重 + 灰区扣留。**图 ≤ 源行合计属预期**，反常的只有"图 > 源"。

**④ 抽样属性比对**（溯源列回指绑定表）：

```ngql
USE gkx_local_1;
FETCH PROP ON Paper "<源表 dwd_id>" YIELD properties(vertex) AS p;
-- zh_name/doi 等应与源行一致;source_table 应为 gkx_dwd_local.dwd_zh_paper / dwd_en_paper / dwd_scholar_papers
```

**⑤ 水位核对**（注意 UTC/CST 差 8 小时）：

```sql
SELECT definition_id, step_id, watermark, updated_at
FROM techkg_global.kg_script_watermark
WHERE definition_id IN ('schema-extract-tag-paper','schema-extract-tag-journal',
  'schema-extract-tag-industry-chain','schema-extract-edge-published-in',
  'schema-extract-edge-authored-by','schema-extract-edge-belongs-to-node');
-- paper 应 3 行(3 绑定)、authored-by 应 4 行;多出的旧行是历史绑定重试留痕
```

检索索引（实体检索页能不能搜到）与审核案处置见全量手册 §7.4/§7.5，此处不展开。

## 附: 2026-10-16 活栈 vs 物料包差异清单

物料包/全量手册定格 10-15（152 绑定），活栈现为 **157**。完整 delta（全量重建时按此补齐，或直接用 `pack_materials.py` 换新转储重打）：

1. **Paper 新增 pos2** `dwd_scholar_papers`（pos0/1 由 zh,en 改为 **en,zh** 顺序）——SQL 见 Step 2。
2. **AUTHORED_BY 新增 pos2/pos3**（`dwd_scholar_paper_relation` / `dwd_scholar_paper_relation_element`）——SQL 见 Step 2。
3. **ACTUAL_CONTROLLER_OF 新增 pos0** `dwd_forg_act_contro_info`（pk=id）：
   ```sql
   SELECT *, row_pk AS id FROM dwd_forg_act_contro_info
   ```
4. **BENEFICIAL_OWNER_OF 新增 pos0** `dwd_forg_beneficiary_info`（pk=id）：
   ```sql
   SELECT *, row_pk AS id FROM dwd_forg_beneficiary_info
   ```
5. **Patent 族 6 条 querySql 时间列改名**（`t.created_time→t.create_time`、`t.updated_time→t.update_time`，10-16 专利时间列对齐规范）：Patent pos0/1、PatentFamily pos0、Keyword pos5、OrganizationBase pos13、MEMBER_OF_FAMILY pos0。
6. **脚本热修 2 个已同步物料包**：paper_entity_step.py（7,367→7,753）、coauthor_with_relation_step.py（5,561→6,182，`relation_time` 用行更新时间代理，否则直接关系模块限时查询全空）。
7. Schema 定义（50 个属性级）与活栈**零差异**。
