# ewrdf 图空间真实数据全链路验证手册(物料级)

> 2026-10-09 v3(= v2 + 方案 B)。目标:在公网门户 `https://edu.itic-sci.com/bkg_zpt` 的部署栈上,用独立 `ewrdf` 图空间跑通**真实数据**全链路,使 **schema 管理、图谱构建、人工审核、平台总览、图谱查询**五个页面全部出现可核验的真实数据。
> v3 变更:源绑定新增**方案 B(推荐)**——一次性建专用小库 `ewrdf_test`(7 张表共 104 行,物料 `docs/ewrdf_test_seed.sql`),五个下拉全部自动选对、免 API 覆盖、脚本零改动;v2 的原库 querySql + API 覆盖路径保留为方案 A(备选)。
> 本手册自带全部物料:10 个 schema 定义、10 个可直接粘贴的抽取脚本、两案源绑定 SQL(真实 id 白名单已填好)、建库脚本、2 个串行任务、五页面验证矩阵。
> 所有源数据均为 `gkx_element` 库 `dwd_*` 数仓真实业务数据(真实工商机构/持股/高管、真实论文/作者/期刊),无 mock、无演示造数。

---

## 0. 前提(已实测确认,勿重复排查)

| 事实 | 结论 |
|---|---|
| 公网 `/bkg_zpt` 承载栈 | **dev2 栈**(web 8089/8091、api 8002、worker `tech-kg-temporal-worker-dev2`);8088"主栈"队列无 poller,下发必挂,**勿用** |
| ewrdf 空间 | 已存在(2026-09-19 平台正式创建),0 tag/0 edge,vid=FIXED_STRING(64) |
| 账号 | `642903148@qq.com`(user 241)已授权 ewrdf,登录即可切换 |
| 执行链 | 图谱库 trsgraph 共享、控制库 techkg_control@temporal-mysql-dev2、业务库 gkx_element@tech-kg-mysql(30306)、S3 operator-rustfs 共享、m3e embedding 可用 |
| 抽取空间解析优先级 | **job graphSpace > schema 绑定空间 > worker 默认 dev2** —— 触发时必须显式带 `graphSpace:"ewrdf"` |

**数据量预算(资源红线内)**:每 schema 源行 ≤ 30,总计约 **68 个实体 + 64 条边**,任务数 **2 个**(chain 类型,内部严格串行,同一时刻只有一个 schema 在写图)。单 schema 抽取 + 自动建索引预计分钟级;若逢共享图过载波可能拉长到几十分钟,属环境现象非故障。

---

## 1. 总体验证矩阵(做完后逐页核对)

| # | 页面 | 验证点 | 预期 |
|---|---|---|---|
| 1 | Schema 管理 | 目录列表(空间=ewrdf) | 10 个 schema:5 实体 + 5 关系,中文标签正确 |
| 2 | 图谱构建 | 任务列表 + 执行详情 | 2 个 chain 任务 COMPLETED;每 schema 一个抽屉,转换步有真实行数 |
| 3 | 人工审核 | 队列(空间=ewrdf) | **约 4 个真实案**:樊杰同名 T_LINK 2-3 案 + 空名作者 T_EXTRACT_FAIL 2 案;裁决后 RESOLVED |
| 4 | 平台总览 | 资产卡/今日新增/审核卡/任务卡 | 实体 ≈68、关系 ≈64;今日新增明细有真实机构名/论文题名/人名;审核卡 top5=ewrdf 案;任务卡 2 条 |
| 5 | 图谱查询 | 图控制台 nGQL + 实体检索 | 按 tag 查到点;两跳查询(高管→机构→股东、论文→作者→合著)出真实路径;实体检索能搜到"樊杰"/机构名 |

---

## 2. 数据设计(5 实体 + 5 关系,两个真实数据簇)

### 簇 A:机构域(真实工商数据)

- **6 个闭合持股对**(股东机构与被持股机构都在机构表内,保证 SHAREHOLDER_OF 两端都是实体):
  迈岭信息←富视康(100%)、中科绿谷←深圳先进技术研究院(16.67%)、计量质检院集团←计量质检研究院、平安壹账通云←深圳电商安全证书管理、三本软件←腾云物联(98%)、玖合鑫通讯←玖合鑫科技(100%)
- 机构簇 = 6 被持股方 + 6 持股方 = **12 家**;高管取 6 家被持股方的真实任职行。

### 簇 B:学者域(真实论文数据)

- **10 篇真实中文论文**(经济地理/药学/电力系统类期刊),每篇取前 2 作者 = **20 位真实作者**;
- **消歧组:樊杰 ×3**——同一姓名、3 个不同 author_id、institution 全 NULL(真实重名数据;同名无可比属性评分 0.80,必进 T_LINK 灰区);
- **失败组:空名作者 ×2**——真实数据质量缺陷行(zh_name 为空),进 T_EXTRACT_FAIL;
- 期刊 4 个:经济地理(1009219)、1006062、1004427、1004798(期刊名在 `dwd_zh_journal`,论文表该列全空,别用错表)。

### Schema 清单

| schema(kind) | 中文名 | 源表 | identity/vid | name 来源 | 关键属性 |
|---|---|---|---|---|---|
| Organization(entity) | 机构 | dwd_org_base_info | org_id | name_cn | province/city/industry/regStatus |
| Officer(entity) | 高管 | dwd_org_executive_info | org_id__姓名 | executives_name | position |
| Expert(entity) | 专家 | dwd_zh_author | author_id | zh_name | institution |
| Paper(entity) | 论文 | dwd_zh_paper | id | zh_name | doi/pubYear |
| Journal(entity) | 期刊 | dwd_zh_journal | publication_id | zh_name | issn |
| EXECUTIVE_OF(relation) | 高管任职 | dwd_org_executive_info | Officer→Organization | — | position |
| SHAREHOLDER_OF(relation) | 股东持股 | dwd_org_shareholder_info | Organization→Organization | — | percentage/ownerName |
| AUTHORED_BY(relation) | 论文署名 | dwd_zh_author | Paper→Expert | — | sequence |
| PUBLISHED_IN(relation) | 发表于 | dwd_zh_paper | Paper→Journal | — | — |
| COAUTHOR_WITH(relation) | 合著 | dwd_zh_author | Expert↔Expert | — | paperId |

> 实体 schema 属性表**必须含 `name`(string)**:建 TAG 时自动建原生索引 `idx_{tag}_name` 并 REBUILD——这是消歧同名召回与实体检索按名查找的命脉。关系 schema 只建 EDGE 无索引,属正常。

---

## 3. 第一步:建 10 个 schema(全局空间切到 ewrdf)

在 Schema 管理页逐个创建(实体建"实体 schema"、关系建"关系 schema",关系需选源/目标实体 schema)。属性定义如下(name 列均为 string、required 建议勾选 name):

**Organization 机构**:name(必需)、province、city、industry、regStatus、capital
**Officer 高管**:name(必需)、position
**Expert 专家**:name(必需)、institution
**Paper 论文**:name(必需)、doi、pubYear
**Journal 期刊**:name(必需)、issn

**EXECUTIVE_OF 任职**:源=Officer,目标=Organization;属性 position
**SHAREHOLDER_OF 股东持股**:源=Organization,目标=Organization;属性 percentage、ownerName
**AUTHORED_BY 论文署名**:源=Paper,目标=Expert;属性 sequence
**PUBLISHED_IN 发表于**:源=Paper,目标=Journal
**COAUTHOR_WITH 合著**:源=Expert,目标=Expert;属性 paperId

> 建完 schema 立即建源绑定并上传脚本(见下),再触发任务——三件套齐全的 schema 才能抽取。

---

## 4. 第二步:源绑定(两案任选,推荐 B)

| | **方案 B:专用测试库(推荐)** | 方案 A:原库 querySql(备选) |
|---|---|---|
| 前置动作 | 一次性建库搬数(4.B.0,共 104 行) | 无 |
| UI 五下拉 | **全部自动选对,纯点选保存** | 时间列必须手选;4 个绑定的主键列只是占位 |
| 额外 API 调用 | **零** | 每个 schema 一次浏览器 console fetch(4.1) |
| 抽取读取量 | 每表 ≤27 行 | Journal 绑定实际翻 2000 行(见 4.A 警示) |
| 数据 | 真实数仓行快照(同源同内容,非 mock) | 原库实时行 |
| 测后清理 | `DROP DATABASE ewrdf_test;` | 无 |

### 4.B 方案 B(推荐):专用测试库 ewrdf_test

在同一个 MySQL 实例(30306)上新建库 `ewrdf_test`,把白名单行搬进去,再按**普通表**绑定。为什么可行且更省事:

- **数据源不用新建**:dev2-default 的账号是 root,库下拉 = 实例级 `SHOW DATABASES`(`backend/service/mysql_datasource.py:list_databases`),新库自动出现在下拉里,数据源仍选 dev2-default;
- **五个下拉全自动选对**:每张表把真实唯一主键放在第一列(前端 pk 自动偏好 = 有 `id` 列选 `id`,否则选第一列),时间列统一命名 `update_time`(前端时间列自动偏好只认 update_time/updated_at/modified_at/gmt_modified)——选中表后主键列/时间列自动带出,核对一眼即可保存,4.0 的三个坑全部消失;
- **普通表绑定的 LIMIT/OFFSET 全表翻页在这里无害**:最大的表也只有 27 行;
- **抽取脚本零改动**:测试表列名与脚本读取字段完全同名(row_id 等合成列已物化为真实列);Journal 表已预去重到 4 行,脚本内按 publication_id 去重的逻辑变空转但完全兼容;
- 普通表模式无水位,每次执行重读全表(几十行,秒级),重跑 = 重复抽取(INSERT VERTEX 覆盖语义),幂等可接受。

#### 4.B.0 建库搬数(一次性,只写新库,不动 gkx_element)

物料文件:**`docs/ewrdf_test_seed.sql`**(与本手册同分支)。宿主机执行:

```bash
cd <仓库检出目录>
docker exec -i tech-kg-mysql mysql --default-character-set=utf8mb4 -uroot -pgkx_element < docs/ewrdf_test_seed.sql
```

⚠ `--default-character-set=utf8mb4` 不能省:实测缺省字符集下 `owners_type='单位'` 这类中文比较命中 0 行、中文字面量输出全变 `??`(6 条持股对会直接丢)。

执行后核对行数(种子脚本头注释里有同款一行命令),预期:

| 表 | 绑定给 | 行数 |
|---|---|---|
| t_org | Organization | 12 |
| t_executive | Officer、EXECUTIVE_OF | 27 |
| t_expert | Expert | 25 |
| t_paper | Paper、PUBLISHED_IN | 10 |
| t_journal | Journal | 4(按 publication_id 预去重) |
| t_author_paper | AUTHORED_BY、COAUTHOR_WITH | 20 |
| t_shareholder | SHAREHOLDER_OF | 6 |

共 **104 行**。真实内容抽查:机构为真实工商主体(深圳市迈岭信息技术有限公司等);期刊为《经济地理》《电网技术》《电力系统保护与控制》《中国科学院院刊》;专家含樊杰同名组(消歧灰区素材)与 2 条空名行(抽取失败素材)。

#### 4.B.1 UI 五下拉选值(选完表后主键列/时间列自动带出,核对即可)

| 绑定给 | 数据源 | 库 | 表 | 主键列(自动) | 时间列(自动) |
|---|---|---|---|---|---|
| Organization | dev2-default | **ewrdf_test** | t_org | org_id | update_time |
| Officer、EXECUTIVE_OF | dev2-default | **ewrdf_test** | t_executive | row_id | update_time |
| Expert | dev2-default | **ewrdf_test** | t_expert | author_id | update_time |
| Paper、PUBLISHED_IN | dev2-default | **ewrdf_test** | t_paper | id | update_time |
| Journal | dev2-default | **ewrdf_test** | t_journal | row_id | update_time |
| AUTHORED_BY、COAUTHOR_WITH | dev2-default | **ewrdf_test** | t_author_paper | row_id | update_time |
| SHAREHOLDER_OF | dev2-default | **ewrdf_test** | t_shareholder | row_id | update_time |

7 张表覆盖 10 个 schema(共用表的各自绑一次,同方案 A 的共用 SQL 逻辑)。保存后**直接跳到第 5 节上传脚本**(脚本零改动),跳过 4.0~4.2 的全部步骤。

#### 4.B.2 测后清理(可选)

```sql
DROP DATABASE IF EXISTS ewrdf_test;
```

注意:清理前确认不再触发抽取(schema 源绑定仍指向该库,库没了再触发会读失败)。新库建在共享实例上同事可见,命名 ewrdf_test 已表明归属;控制库里的 schema 定义/绑定/任务记录不受 DROP 影响,想彻底清场再按平台页面删除 schema/任务即可。

### 4.A 方案 A(备选):原库 gkx_element + API 覆盖 querySql

> 不建测试库时的 v2 原路径。⚠ 已知量控瑕疵:Journal 的 querySql 按 4 个 publication_id 过滤,但 `dwd_zh_journal` 全表 2081 行只有 8 个刊、这 4 刊占 2000 行——该绑定每次抽取要翻 2000 行(脚本去重后仍只产出 4 个实体);方案 B 预去重后只读 4 行,已根治。

### 4.0 UI 来源绑定表单操作细则(先读,有三个坑)

来源绑定表单是**五个下拉框**:数据源 → 库 → 表 → 主键列 → 时间列(水位)。各绑定的选值:

| 绑定给 | 数据源 | 库 | 表 | 主键列 | 时间列 |
|---|---|---|---|---|---|
| Organization | dev2-default | gkx_element | dwd_org_base_info | org_id | updated_time |
| Officer、EXECUTIVE_OF | dev2-default | gkx_element | dwd_org_executive_info | org_id(占位) | updated_time |
| Expert | dev2-default | gkx_element | dwd_zh_author | author_id | updated_time |
| Paper、PUBLISHED_IN | dev2-default | gkx_element | dwd_zh_paper | id | updated_time |
| Journal | dev2-default | gkx_element | dwd_zh_journal | publication_id(占位) | updated_time |
| AUTHORED_BY、COAUTHOR_WITH | dev2-default | gkx_element | dwd_zh_author | paper_id(占位) | updated_time |
| SHAREHOLDER_OF | dev2-default | gkx_element | dwd_org_shareholder_info | org_id(占位) | updated_time |

- 数据源选 **dev2-default(host.docker.internal)**——默认数据源(id `MYSQL-430EAF90`,指向 gkx_element@30306),下拉里同名杂源很多,认准这个;
- **时间列不会自动选对**:前端自动偏好只认 update_time/updated_at/modified_at/gmt_modified,本手册的表全是 `updated_time`,必须手动在下拉里搜索选 `updated_time`;
- **"占位"主键列**:需要合成 row_id 的四个绑定(Officer/EXECUTIVE_OF、Journal、AUTHORED_BY/COAUTHOR_WITH、SHAREHOLDER_OF),正确 pkColumn 是 querySql 里的 `row_id`,UI 下拉只列物理表列选不到——先按表选真实列占位,第 4.1 步 API 覆盖时改成 `row_id`。

**⚠ UI 表单填不了 querySql(前端 SchemaSourceInput 无此字段),只支持整表绑定——整表绑定抽取走 LIMIT/OFFSET 全表翻页,控量即失效(Expert 源表 7906 行会被全读)。因此 UI 保存骨架后,必须按 4.1 用 API 覆盖补 querySql。**

### 4.1 API 覆盖补 querySql(UI 保存后执行,缺这步控量失效)

在门户页面按 F12 → Console 执行(同源自动带登录态;内网 8091 root 实例把前缀换成 `/api`):

```js
await fetch('/bkg_zpt/api/v1/schema-management/schemas/<schemaId>/sources', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ sources: [{
    datasourceId: 'MYSQL-430EAF90',   // dev2-default
    databaseName: 'gkx_element',
    tableName: 'dwd_org_base_info',   // 按绑定换
    pkColumn: 'org_id',               // 合成 row_id 的绑定此处改 'row_id'
    timeColumn: 'updated_time',
    querySql: '<贴下方对应 SQL,单行,去掉换行或保留均可>'
  }]})
}).then(r => r.json())
```

schemaId 在 schema 管理页该 schema 的详情里取。共需覆盖 **8 次**(10 个 schema 中 Officer/EXECUTIVE_OF、Paper/PUBLISHED_IN、AUTHORED_BY/COAUTHOR_WITH 各共用同一段 SQL,但每个 schema 都要各自覆盖一次)。验证覆盖成功:schema 详情源绑定里能看到自定义 SQL,或 `GET /api/v1/schema-management/schemas/<id>/sources` 返回的 querySql 非空。

### 4.2 各绑定的 querySql(id 白名单已填好)

每个 schema 配一个来源绑定。**必须用 querySql 模式**(普通表绑定走 LIMIT/OFFSET 全表翻页,控不住量);querySql 里带合成 `row_id` 的,pkColumn 填 `row_id`,其余 pkColumn/timeColumn 见表。

### Organization
```sql
SELECT org_id, name_cn, province, city, industry_l1_name, reg_status, registered_capital_value, updated_time
FROM gkx_element.dwd_org_base_info
WHERE org_id IN ('6316ee16a50a0a093a5859d8b5cc67a8','98e68fdf64b81709249dc23816a89c66',
 '6c25d2e2c852ba5a81d733cefaf5fe7b','69c0d92da4105991cedee6335fb44412',
 '0a14fdb97eb7d2892654ee2ef180b527','cbeac662cf32b19dcdb872790e4df8da',
 '8e04394509161ebbdf63c1813b948955','71aa92091eda2d2b872ca903d05d6d5d',
 'f21c867cb7a12e7f175c422de0e939a4','3d9ba778337dba72db8cc12a1bbb92be',
 'e9f6a720f02bb2143dd0f926b82f07f3','6ed1fec4b9de17f467edc5dd0af0c89a')
```
pkColumn=`org_id`,timeColumn=`updated_time`

### Officer 与 EXECUTIVE_OF(同一 SQL,分别绑到两个 schema)
```sql
SELECT CONCAT(org_id,'__',executives_name) AS row_id, org_id, executives_name, executives_position, updated_time
FROM gkx_element.dwd_org_executive_info
WHERE org_id IN ('6316ee16a50a0a093a5859d8b5cc67a8','6c25d2e2c852ba5a81d733cefaf5fe7b',
 '0a14fdb97eb7d2892654ee2ef180b527','8e04394509161ebbdf63c1813b948955',
 'f21c867cb7a12e7f175c422de0e939a4','e9f6a720f02bb2143dd0f926b82f07f3')
```
pkColumn=`row_id`,timeColumn=`updated_time`

### Expert
```sql
SELECT author_id, zh_name, institution, updated_time
FROM gkx_element.dwd_zh_author
WHERE author_id IN ('cafb9c466b2d74de158d995bef134639','36e40fcc42d2bec87f7c423211213dfb',
 '59dce19adb29701688a1ce9a63069aea','134066be56583f1327557f7898825a18',
 '50ef5f551c4a7fad56dcd82b2bdf6da2','d2b9bda08f8130b8dab54e1aa6ae6b98',
 '0f2f8f6e8903effb92ff99d39f936787','a7b0e09a0ff6d3337a5fee9ba4434844',
 'ff60369aa3eb6daad43d30000fa43e4b','fb9e2948f22da487fb3338ba1f4e072a',
 '73fdfa939f5bc499b86582316981b1db','53e7d89bd0f34628b6ef2f7055d8eec4',
 '24db008db3d0781a7bd6cd35a4f3922c','47330a8c229cc0b1f03129685eaa4763',
 '717546ccc349b6d95a2050122c6a7664','eb01531ab783e0f19a7fe36aad02c5cc',
 '264fb2e63afff07020233920a4d7a11b','8f7a5550dc2be9517d371be0448804f2',
 '12aea370e3b46b1dc7e6570a6cd639b9','eb7e28ffc6a0edf21580dddc0aced796',
 '2c3dfa15fa2b0f1adac5b7c835ca00dc','170795a90339520c3673f72508b5ba6f',
 'da151fbcb5e621d9b2ce6754a0859f63',
 '80960999b7bfd9f089b86c88796b3bcb','792f74d99a0bd137118b239fac5047ef')
```
pkColumn=`author_id`,timeColumn=`updated_time`
(前 20 = 论文簇作者;末 3 = 樊杰×3(消歧组);最后 2 = 空名行(失败组))

### Paper 与 PUBLISHED_IN(同一 SQL 分别绑)
```sql
SELECT id, zh_name, doi, cover_year_start, publication_id, updated_time
FROM gkx_element.dwd_zh_paper
WHERE id IN ('1002153099575427075','1002153099575427078','1002153099575427082','1002153099575427088',
 '1002153099575427093','1002613259049631753','1005773515376295936','1005773515376295942',
 '1012001490740445188','1012001490740445198')
```
pkColumn=`id`,timeColumn=`updated_time`

### Journal
```sql
SELECT CONCAT(publication_id,'__',paper_id) AS row_id, publication_id, zh_name, issn, updated_time
FROM gkx_element.dwd_zh_journal
WHERE publication_id IN ('1009219','1006062','1004427','1004798')
```
pkColumn=`row_id`,timeColumn=`updated_time`(同一期刊多行,脚本内按 publication_id 去重)

### AUTHORED_BY 与 COAUTHOR_WITH(同一 SQL 分别绑)
```sql
SELECT CONCAT(paper_id,'__',author_id) AS row_id, paper_id, author_id, author_sequence, zh_name, updated_time
FROM gkx_element.dwd_zh_author
WHERE author_sequence<=2 AND paper_id IN ('1002153099575427075','1002153099575427078','1002153099575427082',
 '1002153099575427088','1002153099575427093','1002613259049631753','1005773515376295936',
 '1005773515376295942','1012001490740445188','1012001490740445198')
```
pkColumn=`row_id`,timeColumn=`updated_time`

### SHAREHOLDER_OF
```sql
SELECT CONCAT(org_id,'__',inv_org_id) AS row_id, org_id, inv_org_id, owners_name, ownership_percentage, updated_time
FROM gkx_element.dwd_org_shareholder_info
WHERE owners_type='单位'
  AND org_id IN ('6316ee16a50a0a093a5859d8b5cc67a8','6c25d2e2c852ba5a81d733cefaf5fe7b',
   '0a14fdb97eb7d2892654ee2ef180b527','8e04394509161ebbdf63c1813b948955',
   'f21c867cb7a12e7f175c422de0e939a4','e9f6a720f02bb2143dd0f926b82f07f3')
  AND inv_org_id IN ('98e68fdf64b81709249dc23816a89c66','69c0d92da4105991cedee6335fb44412',
   'cbeac662cf32b19dcdb872790e4df8da','71aa92091eda2d2b872ca903d05d6d5d',
   '3d9ba778337dba72db8cc12a1bbb92be','6ed1fec4b9de17f467edc5dd0af0c89a')
```
pkColumn=`row_id`,timeColumn=`updated_time`

---

## 5. 第三步:上传抽取脚本(10 个,直接粘贴)

脚本契约:`from kg_sdk import step` + `@step def extract(payload)`,吃 `payload["rows"]`,输出实体 `{"entities":[{"id":vid,"props":{...}}],"failures":[{"recordId","error"}]}` / 边 `{"edges":[{"fromId","toId","props":{...}}],"failures":[...]}`。逐行异常进 failures(毒行隔离),不抛出。函数名不得叫 transform/workflow。

### 5.1 Organization
```python
"""Organization(机构)抽取:dwd_org_base_info 行 → 机构实体。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures = [], []
    for row in payload.get("rows") or []:
        try:
            name = (row.get("name_cn") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 name_cn")
            entities.append({
                "id": str(row["org_id"]),
                "props": {
                    "name": name,
                    "province": row.get("province") or "",
                    "city": row.get("city") or "",
                    "industry": row.get("industry_l1_name") or "",
                    "regStatus": row.get("reg_status") or "",
                    "capital": str(row.get("registered_capital_value") or ""),
                },
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("org_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.2 Officer
```python
"""Officer(高管)抽取:dwd_org_executive_info 行 → 高管实体(vid=org_id__姓名)。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        try:
            name = (row.get("executives_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 executives_name")
            vid = f"{row['org_id']}__{name}"
            if vid in seen:  # 同一人在同一机构多行(多职位),合并为一个实体
                continue
            seen.add(vid)
            entities.append({
                "id": vid,
                "props": {"name": name, "position": row.get("executives_position") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.3 Expert
```python
"""Expert(专家)抽取:dwd_zh_author 行 → 专家实体。空名行进 failures(真实数据质量缺陷→T_EXTRACT_FAIL)。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        rid = str(row.get("author_id") or "")
        try:
            name = (row.get("zh_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 zh_name(源行数据质量缺陷)")
            if rid in seen:  # 同一作者多行(多篇论文),合并
                continue
            seen.add(rid)
            entities.append({
                "id": rid,
                "props": {"name": name, "institution": row.get("institution") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": rid, "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.4 Paper
```python
"""Paper(论文)抽取:dwd_zh_paper 行 → 论文实体。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures = [], []
    for row in payload.get("rows") or []:
        try:
            name = (row.get("zh_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 zh_name")
            entities.append({
                "id": str(row["id"]),
                "props": {
                    "name": name,
                    "doi": row.get("doi") or "",
                    "pubYear": str(row.get("cover_year_start") or ""),
                },
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.5 Journal
```python
"""Journal(期刊)抽取:dwd_zh_journal 行(一论文一行)按 publication_id 去重 → 期刊实体。"""
from kg_sdk import step


@step
def extract(payload):
    entities, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        try:
            pid = str(row.get("publication_id") or "")
            name = (row.get("zh_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 zh_name")
            if pid in seen:
                continue
            seen.add(pid)
            entities.append({
                "id": pid,
                "props": {"name": name, "issn": row.get("issn") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"entities": entities, "failures": failures}
```

### 5.6 EXECUTIVE_OF
```python
"""EXECUTIVE_OF(高管任职)边:Officer→Organization,一人一机构一条(position 取首行)。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures, seen = [], [], set()
    for row in payload.get("rows") or []:
        try:
            name = (row.get("executives_name") or "").strip()
            if not name:
                raise ValueError("缺少必需名称字段 executives_name")
            officer_vid = f"{row['org_id']}__{name}"
            if officer_vid in seen:
                continue
            seen.add(officer_vid)
            edges.append({
                "fromId": officer_vid,
                "toId": str(row["org_id"]),
                "props": {"position": row.get("executives_position") or ""},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.7 SHAREHOLDER_OF
```python
"""SHAREHOLDER_OF(股东持股)边:股东机构→被持股机构(单位股东,两端都是 Organization 实体)。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    for row in payload.get("rows") or []:
        try:
            if not (row.get("inv_org_id") and row.get("org_id")):
                raise ValueError("缺少端点机构 id")
            edges.append({
                "fromId": str(row["inv_org_id"]),
                "toId": str(row["org_id"]),
                "props": {
                    "percentage": str(row.get("ownership_percentage") or ""),
                    "ownerName": row.get("owners_name") or "",
                },
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.8 AUTHORED_BY
```python
"""AUTHORED_BY(论文署名)边:Paper→Expert。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    for row in payload.get("rows") or []:
        try:
            if not (row.get("paper_id") and row.get("author_id")):
                raise ValueError("缺少 paper_id/author_id")
            edges.append({
                "fromId": str(row["paper_id"]),
                "toId": str(row["author_id"]),
                "props": {"sequence": str(row.get("author_sequence") or "")},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("row_id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.9 PUBLISHED_IN
```python
"""PUBLISHED_IN(发表于)边:Paper→Journal。"""
from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    for row in payload.get("rows") or []:
        try:
            if not (row.get("id") and row.get("publication_id")):
                raise ValueError("缺少论文 id/期刊 publication_id")
            edges.append({
                "fromId": str(row["id"]),
                "toId": str(row["publication_id"]),
                "props": {},
            })
        except Exception as exc:
            failures.append({"recordId": str(row.get("id") or ""), "error": f"{type(exc).__name__}: {exc}"[:1000]})
    return {"edges": edges, "failures": failures}
```

### 5.10 COAUTHOR_WITH
```python
"""COAUTHOR_WITH(合著)边:Expert↔Expert,同一论文的前 2 作者两两成对(脚本内派生)。"""
from collections import defaultdict

from kg_sdk import step


@step
def extract(payload):
    edges, failures = [], []
    by_paper = defaultdict(list)
    for row in payload.get("rows") or []:
        if row.get("paper_id") and row.get("author_id"):
            by_paper[str(row["paper_id"])].append(str(row["author_id"]))
    for paper_id, authors in by_paper.items():
        unique = list(dict.fromkeys(authors))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                a, b = sorted([unique[i], unique[j]])
                edges.append({"fromId": a, "toId": b, "props": {"paperId": paper_id}})
    return {"edges": edges, "failures": failures}
```

---

## 6. 第四步:建 2 个任务并触发(chain 串行,资源压力最小)

图谱构建页建任务,类型选 **chain(多 Schema 串行)**,`graphSpace` 显式 `ewrdf`,`batchSize=10`(每批 10 行,小批慢写保护图服务):

1. **任务 1「ewrdf-实体链」**:schemaIds 顺序 = `[Organization, Officer, Expert, Paper, Journal]`
2. **任务 2「ewrdf-关系链」**:schemaIds 顺序 = `[EXECUTIVE_OF, SHAREHOLDER_OF, AUTHORED_BY, PUBLISHED_IN, COAUTHOR_WITH]`

**先触发任务 1,等它 COMPLETED 再触发任务 2**(边端点依赖实体先落图)。chain 内部严格串行:同一时刻只有一个 schema 在写图;任一环执行级失败整链 FAILED(逐行 failures 不算失败,只进审核)。执行详情页每个 schema 一个抽屉,可看各环节真实行数。

API 等价操作(可选):
```bash
curl -X POST http://localhost:8002/api/v1/workflow-system/jobs -H 'Content-Type: application/json' -d \
'{"taskType":"chain","name":"ewrdf-实体链","graphSpace":"ewrdf","batchSize":10,
  "schemaIds":["<Organization的schemaId>","<Officer的schemaId>","<Expert的schemaId>","<Paper的schemaId>","<Journal的schemaId>"]}'
curl -X POST http://localhost:8002/api/v1/workflow-system/jobs/<jobId>/trigger
```
(schemaId 在 schema 管理页每个 schema 的详情里;勿用 /task-center/trigger 全量扫)

---

## 7. 第五步:人工审核(预期 ~4 个真实案)

任务 1 完成后,运营中心 → 人工审核队列(空间=ewrdf),应出现:

| 案件 | 来源 | 预期 |
|---|---|---|
| 实体对齐裁决(T_LINK)×2~3 | 樊杰 ×3:第 1 个直接落图;第 2、3 个与已落"樊杰"同名比较,institution 全 NULL 无可比属性,评分 0.80 落灰区 [0.65,0.85) | 每个扣留行各自成案,案内可见候选"樊杰"与待判实体 |
| 抽取失败重跑(T_EXTRACT_FAIL)×2 | 2 条空名作者行进 failures(recordId=author_id) | 失败记录列可查源行 |

**裁决操作**(production submit,任何 action 终态 RESOLVED):
- T_LINK 任选其一体验:`entityVerdict=merge`(真改目标节点属性,两樊杰并一个点)、`create`(按 _incoming.vid 落图)、`reject`(图零写入);驳回证据在 `GET /api/v1/manual-reviews/production/{id}/audit-logs`;
- T_EXTRACT_FAIL:点「重跑」(`rerun-extract-failures`)→ 新执行 triggerSource=RERUN;**注意这两行是真实空名行,重跑仍会失败**(数据本身缺陷),失败回滚 OPEN 属正常,正好验证重跑链路。

> 裁决写图按 case 建案时烙定的 ewrdf 空间,不受当前空间切换影响;但审完前别切走空间,防误操作。

---

## 8. 第六步:五页面验证

### 8.1 Schema 管理页
空间=ewrdf:10 个 schema(机构/高管/专家/论文/期刊 + 5 关系),中文名、属性、脚本、源绑定齐全。

### 8.2 图谱构建页
2 个 chain 任务 COMPLETED;点开执行详情,每个 schema 抽屉显示真实转换行数(如 Organization 12 行、Expert 25 行/2 失败)。

### 8.3 人工审核页
裁决后队列状态 RESOLVED;审计日志可查 DECISION_SUBMITTED。

### 8.4 平台总览页(空间=ewrdf)
- 资产卡:实体 ≈68、关系 ≈64(以实际为准;SUBMIT JOB STATS 空间级异步,数字滞后一步就刷新页面);
- 今日新增:明细行应有真实机构名(深圳市迈岭信息技术有限公司等)、论文题名(土地流转和社会化服务对农业全要素生产率的影响实证分析等)、人名(张利国/樊杰等);
- 人工审核卡:top5 显示 ewrdf 自己的案;图谱构建任务卡:2 条。

### 8.5 图谱查询(图控制台,只读)
```bash
# 以下经图网关执行(X-Graph-Space: ewrdf),浏览器图控制台等价
# 1) 按标签查点
MATCH (v:`Organization`) RETURN v.name, v.province LIMIT 12
# 2) 两跳:高管 → 任职机构 → 股东
MATCH (o:Officer)-[:EXECUTIVE_OF]->(g:Organization)<-[:SHAREHOLDER_OF]-(s:Organization)
RETURN o.name, o.position, g.name, s.name, s.percentage? LIMIT 10
# 实际用 GO 更稳:
GO 1 TO 2 STEPS FROM '<某高管vid>' OVER EXECUTIVE_OF REVERSELY, SHAREHOLDER_OF YIELD DISTINCT id($$) AS endpoint
# 3) 论文 → 作者 / 期刊
MATCH (p:Paper)-[:AUTHORED_BY]->(e:Expert) RETURN p.name, e.name LIMIT 20
MATCH (p:Paper)-[:PUBLISHED_IN]->(j:Journal) RETURN p.name, j.name LIMIT 10
# 4) 同名实体(消歧现场)
MATCH (v:`Expert`) WHERE v.Expert.name == '樊杰' RETURN id(v), v.institution
```
- **实体检索页**:先确认 ewrdf 索引已建(任务 1 收尾自动建,`kg_entity` 集合按空间分区;若提示"尚未构建实体索引"则页面点一次重建,ewrdf 量小秒级);搜"樊杰"、"深圳先进技术研究院"、"经济地理"应出真实结果。

---

## 9. 风险与红线

| 项 | 说明 |
|---|---|
| 资源红线 | 方案 B 只绑 `ewrdf_test` 的 7 张小表(共 104 行);方案 A 只用本手册的 id 白名单 querySql(总量 ~130 行)。batchSize=10,chain 串行,**勿对 gkx_element 的 dwd_* 大表做全表绑定**;共享图过载波时抽取变慢属正常,勿反复重启 |
| 静默写错空间 | 触发任务必须显式 `graphSpace:"ewrdf"`;不带时最坏写进 worker 默认空间 dev2 |
| 共享环境 | 控制库曾有未知清理者删 schema(2026-09-23);业务库全栈共享——方案 A **只读** gkx_element 白名单行,方案 B 的写只落在新建 `ewrdf_test` 库;别人的数据(尤其 review_widgets 等)不碰 |
| vid 上限 | ewrdf vid=FIXED_STRING(64):机构/作者 32 位、论文 19 位、Officer 复合 vid ~44 字节,均安全;自增字段别超 64 |
| T_DIRECT | 现行抽取链不产生 T_DIRECT;若在库里看到存量 T_DIRECT 案,勿在 ewrdf 测 accept(非 RBAC 下会写默认空间) |
| 幂等重跑 | 方案 A:querySql 按 (time, pk) keyset 水位增量,首次跑读白名单全集、重跑只读变更行;想全量重灌需先删 watermark(schema 源绑定保存处)。方案 B:普通表绑定无水位,每次执行重读全表 104 行(秒级),重跑 = 重复抽取覆盖写,天然幂等 |

---

## 10. 附录

### A. id 白名单的选簇 SQL(想换一批数据时用)
```sql
-- 机构簇:6 个闭合持股对(两端都在机构表,且被持股方有高管行)
SELECT s.org_id, s.inv_org_id, o1.name_cn, o2.name_cn, s.ownership_percentage
FROM gkx_element.dwd_org_shareholder_info s
JOIN gkx_element.dwd_org_base_info o1 ON o1.org_id = s.org_id
JOIN gkx_element.dwd_org_base_info o2 ON o2.org_id = s.inv_org_id
WHERE s.owners_type = '单位'
  AND EXISTS (SELECT 1 FROM gkx_element.dwd_org_executive_info e WHERE e.org_id = s.org_id)
LIMIT 6;

-- 论文簇:有≥2署名的论文 10 篇(期刊信息要 JOIN dwd_zh_journal 取,论文表 publication_zh_name 全空)
SELECT a.paper_id, p.zh_name FROM
 (SELECT paper_id FROM gkx_element.dwd_zh_author WHERE zh_name<>''
   GROUP BY paper_id HAVING COUNT(DISTINCT author_id)>=2 ORDER BY paper_id LIMIT 10) a
JOIN gkx_element.dwd_zh_paper p ON p.id = a.paper_id;

-- 消歧组:真实重名作者(institution 为 NULL → 评分 0.80 进灰区)
SELECT zh_name, COUNT(DISTINCT author_id) ids FROM gkx_element.dwd_zh_author
WHERE institution IS NULL AND zh_name<>'' GROUP BY zh_name HAVING ids>=3 ORDER BY ids DESC LIMIT 5;

-- 失败组:真实空名行
SELECT author_id, paper_id FROM gkx_element.dwd_zh_author WHERE zh_name IS NULL OR zh_name='' LIMIT 2;
```

### B. 真实性凭证(2026-10-09 实测)
- dwd_org_base_info 1,674 行(真实工商机构)、dwd_org_executive_info 5,600 行、dwd_org_shareholder_info 含真实持股比例;
- dwd_zh_paper 2,000 行、dwd_zh_author 7,906 行(真实论文/作者/机构署名);
- 樊杰 14 个不同 author_id(institution 全 NULL)、空名作者 6 行——均为库中真实存在的数据。

### C. 机制依据(代码相对路径)
- 脚本契约:`backend/script/extract_transform_common.py`(entities/edges/failures 项格式、毒行隔离);
- @step 唯一入口、chain 任务类型、querySql 水位/pk keyset、T_EXTRACT_FAIL 逐行建案:`CLAUDE.md` 平台喂数批次抽取节;
- 抽取空间解析(job graphSpace > schema 行 > env 默认):`backend/service/temporal_workflows.py` `_extract_schema`;
- 实体 TAG 自动 name 索引 `idx_{tag}_name`:`backend/service/schema_ddl.py`;
- 实体检索单集合 kg_entity 按空间分区、新空间首检需建索引:`backend/service/entity_search.py`;
- 消歧同名召回(Nebula MATCH 非 Milvus):`backend/service/entity_disambiguation.py`;
- 审核 case 空间烙定 + 队列 graphSpace 过滤:`backend/service/manual_review_production.py`。
