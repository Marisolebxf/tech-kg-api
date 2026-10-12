# gkx 生产库抽取适配——49 Schema 绑定清单（2026-10-11 定稿，全量探针通过）

> 目标：把 yft1 e2e 的 45 个抽取脚本从 `gkx_element_yft1`（业务裸表格式）切到外部 gkx 生产格式
> 样例库（`183.240.141.251:3318/gkx`，DWD 装载层格式），**产出的实体和关系与原来一样**——
> 同 16 TAG / 33 EDGE、同属性集、同 VID 公式、同过滤口径；数据值随源库自然不同（ID 体系不同）。
>
> 硬约束（用户两次声明）：**不能动表结构、不能改表数据**。全部适配 = 只读 `querySql` + 脚本转换层。
>
> 机器可读清单：`artifacts/gkx-prod-bindings/manifest.json`（生成器 `build_manifest.py`，
> 输入 `old_bindings.json` = yft1 目录原样导出；生成器含全量断言校验）。本文是它的说明与定稿记录。
> **终版探针 43/43 通过**（列审计 51 表 + 全量 SQL 按平台包裹形式实跑 + 重查询 EXPLAIN，
> 日志 `~/.claude/jobs/6c9295e5/tmp/probe_final.log`）。
>
> **10-11 修订（干跑后）**：manifest 手工修订两处——精简列集 10 表 22 绑定（§3.6）+ 专利域
> 冗余绑定删除 4 条（§3.3 附注），161 → **157**；生成器 `build_manifest.py` 待同步此二处。

## 0. 用户拍板口径（2026-10-10）

| # | 决策点 | 结论 |
| --- | --- | --- |
| ① | 表结构动不了 | 全部走 querySql 适配，真实列 AS 旧列名 |
| ② | 产业链域列全换 | 方案 a：语义映射重建（本清单 §6，全部实测验证） |
| ③ | SUBSIDIARY_OF 源表缺失 | 可换源 → `dwd_org_subsidiary_info` |
| ④ | 外部无源的数据 | 无源即 0（删绑定，不建桩数据） |
| ⑤ | 治理口径 | source_system="gkx"（脚本侧）+ is_deleted=0 |

## 1. 脚本侧改动（源模块 + 基础设施 + 重新生成）

45 个脚本语义不变，源模块与基础设施改动：

1. `backend/script/entity_extractors_one_entity/common.py` `SOURCE_SYSTEM = "gkx_element"` → `"gkx"`
   （全库唯一定义点，写入每个实体/边的 `source_system` 属性）。
2. `backend/script/entity_extractors_one_entity/mappers.py` `patent_record`：**子表 10 属性条件化**
   ——行内出现 `titles` 列（= B 富集源）才输出 `grant_date/status/anticipated_expiration/
   title_original/title_en/title_zh/abstract_zh/citation_nums/cited_by_nums/simple_family_number`，
   A 裸表源行（无子表列）只写 p 表原生属性。配合专利域 A+B 双源绑定（§3.3），
   两源属性集不相交 → 同 Schema 并发抽取（`asyncio.gather`）下谁后写都不覆盖对方
   （平台 INSERT VERTEX 是列级 upsert，未列出的属性保留原值）。
3. **股东类型词表**（实体侧 `mappers.py` 与关系侧 `org_edges.py` 同源扩展）：外部
   `dwd_org_shareholder_info.owners_type` 是工商口径词表（企业法人/法人股东/合伙企业/
   事业法人/机关法人/自然人股东…40 万行中 32 万行 inv_org_id 为空、19.8 万行类型为空），
   yft1 只有 {单位, 企业法人} 且全部有 inv_org_id。扩展 `_ORG_TYPES`/`_PERSON_TYPES`
   双侧词表；**空类型且无 inv_org_id 不出 Person/边**（无判别依据，无源即 0 口径；
   若按行失败处理会有 17 万条涌进 T_EXTRACT_FAIL 审核队列），显式未知类型仍 raise 走行失败
   （bankruptcy/forg_shareholder 的行失败与 yft1 基线逐行一致，非 bug）。
4. **公网源库两项加固**（干跑发现的平台级问题，缺陷⑳/㉑）：
   - `backend/infra/mysql.py`：非 sqlite 引擎统一加 socket 级超时
     `connect_args={connect_timeout:10, read_timeout:600, write_timeout:600}`——NAT 静默
     断连的半开连接 `pool_pre_ping` 救不了（SELECT 1 写得进、读阻塞到天荒地老），
     600s > BELONGS 最长单批 185s；脚本层 `relation_extractors_one_relation/common.py`
     的 `mysql_engine` 同参数。
   - `backend/script/relation_extractors_one_relation/resolvers.py`：
     `load_resolver_cached()` 进程级 TTL 缓存（600s）——`transform_org_relation` 原实现
     **每批** `ExactOrganizationResolver.load()` 全拉 7 张机构表（19 万行起），公网下
     recruit 670 万行 = 6700 批 × 全量装载是灾难；单空间单进程内水位不变语义不变。
5. 重新生成：`git checkout 7a1fbba0 -- script/yunfei_restore/ && uv run python
   script/tools/build_portable_steps.py`（49/49 ok，--verify 无未定义名；生成后
   `ruff check --fix` + `ruff format --no-cache`，HEAD 由 443f5227 整理过格式）。

脚本对列的读取全走 `row.get(...)` fallback 链 + `parse_list` 四层兜底（JSON 数组 → 逗号分隔 →
中文分隔 → 单值），因此 json→text、datetime→date、数组→单值这类类型变化**无需脚本改动**。

## 2. 数据源与绑定总表

注册一个新 MySQL 数据源（管理端「配置管理 → MySQL 数据源」）：

| 字段 | 值 |
| --- | --- |
| 名称 | `gkx-prod-sample` |
| 主机 / 端口 | `183.240.141.251` / `3318`（api 容器内可直连，无需 host.docker.internal） |
| 默认库 | `gkx`（只读账号 `gkx_reader_zp`，密码部署时经环境提供，不入库） |

**156 条旧绑定 → 157 条新绑定**（+5 = 专利域 5 个 Schema 各加一条 B 富集源；CITES zh 两表
干跑后由 keep 转 rewrite；干跑后删 4 条专利域冗余绑定 → 161−4=157，见 §3.3 附注）：

| action | 条数 | 含义 |
| --- | --- | --- |
| `keep` | 76 | 普通绑定换库重绑（≤5 万行小表，平台 OFFSET 模式语义同旧）；pk 按表真实主键、time=updated_time |
| `promote` | 27 | 大表（>5 万行）升级为最小 querySql `SELECT t.* WHERE is_deleted=0`——平台对普通表恒 OFFSET（每批 `ORDER BY pk LIMIT n OFFSET m`，大表翻页越扫越深），querySql 才能走 keyset；其中 10 表 22 绑定再精简列集（§3.6） |
| `rewrite` | 46 | querySql 重写（列别名 / 拆表回拼 / 换原子列 / 语义重建 / A+B 拆分 / CITES zh 大小写别名与 JSON 炸开），全文在 manifest |
| `drop` | 6 | 外部缺表：`dwd_forg_act_contro_info`（Person+ACTUAL_CONTROLLER_OF）、`dwd_forg_beneficiary_info`（Person+BENEFICIAL_OWNER_OF）、`dwd_forg_stock_fin_info`（Event+INVOLVED_IN）→ 这些来源产 0 |
| `replace` | 2 | 换源：SUBSIDIARY_OF → `dwd_org_subsidiary_info`；BELONGS_TO_NODE → `dwd_org_industry_tags`（语义重建） |

主键二态（information_schema 实测）：9 张表主键是 **pk_id**（dwd_industry_chain_info /
dwd_industry_chain_news_info / dwd_zh_author / dwd_zh_journal / dwd_zh_paper /
dwd_zh_paper_citation / dwd_zh_paper_classification / dwd_zh_paper_reference /
dwd_zh_paper_related），其余绑定表主键均为 dwd_id。keep/promote 按表取真实主键
（生成器 `PK_OVERRIDES`）。

## 3. 读取模式与执行计划（2026-10-11 探针定稿）

### 3.1 为什么全量 keyset

平台包裹：querySql 绑定 timeColumn 留空 + pk 唯一 → **keyset 模式**
`SELECT * FROM (querySql) src WHERE src.pk > :cursor ORDER BY src.pk LIMIT :n`；
普通表绑定恒 OFFSET（无法声明分页），OFFSET 模式每批 `ORDER BY pk LIMIT n OFFSET m`
——大表翻页代价线性恶化。外部库量是 yft1 的 100–3000 倍（patent 269 万 / recruit 670 万），
所以：**小表 keep（OFFSET 可忍），大表一律升 querySql 走 keyset**。

### 3.2 MySQL 9.7 的 Sort 病理与三类对策

EXPLAIN 实测：**多表 join 的 querySql 在该商业版上必然出现 Sort 节点**——hash join 打破
「输出序 = 主键序」的证明，优化器对全量 join 结果排序后才能 LIMIT → 每批流完整张表 →
O(n²/2n) 总代价（实测 patent 单源首批 90s+ 超时，NO_BNL / LIMIT 阻断 merge 均救不回来：
前者每行临时表扫描，后者宽串 GROUP BY 派生表每批物化 30s）。对策：

- **a) 单表可下推**（大多数）：pk = 裸主键别名，包裹层 merge 推回主键索引范围扫 + LIMIT
  提前截断，线性。EXPLAIN 实证（patent A 源）：`Limit → Filter(is_deleted, pk>cursor) →
  Index range scan on t using PRIMARY`，**无 Sort 无 join**。
- **b) 小结果集 join**（输出 ≤10 万行：Person / STUDIED_AT / patent B / HAS_OUTPUT 等）：
  Sort 每批只排输出行，可接受；**派生表一律加 `LIMIT 18446744073709551615` 阻止 merge**
  （merge 会把 MIN(dwd_id) 自联结拆进联结树 → 内层物化表被外层每行重扫，实测 4 亿次访问
  90s 超时）；**相关子查询禁止**（dependent subquery 阻断 merge 且每行全表扫）——换成
  GROUP_CONCAT 派生表。STUDIED_AT 最优：eb 派生表物化后走 `<auto_key>` 嵌套循环查
  找、保 s 主键序 → **免 Sort**，LIMIT 直接截断。
- **c) 大表 join**（dwd_patent 269 万 × 5 子表）：拆 **A+B 双源**，见 3.3。

### 3.3 专利域 A+B 双源绑定（5 个 Schema × 2 条）

| 源 | 驱动 | 输出列 | keyset pk | 实测 |
| --- | --- | --- | --- | --- |
| A 裸表 | `dwd_patent` 单表 + 列别名（pn→publication_number 等 20 列） | p 原生属性 | `source_row_id`(=dwd_id 别名，merge 推回 PRIMARY) | 1.0s/批 × 539 批 ≈ **9 分钟** |
| B 富集 | 5 子表 `UNION patent_id`（去重 ~9.4 万）JOIN p + 5 个 `MAX()` 聚合派生表 | p 原生 + 子表 10 列（缺子表行为 ""，老 LEFT JOIN 口径） | `source_row_id` | 46.7s/批 × ~19 批 ≈ **15 分钟**（子表 UNION 9.4 万行，非 269 万） |

并发安全：同 Schema 多源是 `asyncio.gather` **并发**的，写序不定；平台 checkpoint 按
`stepId=source:{绑定id}` 独立持久化（双绑定两行、两游标，无互踩）；A/B 属性集不相交
（脚本侧 §1.2 条件化保证），INSERT VERTEX 列级 upsert → 谁后写都不覆盖对方。
p 原生属性两源同值重写，幂等无害（仅 ingest_time 取后写者）。

**附注（干跑后删 4 条冗余，161→157）**：A+B 拆分先铺到 5 个 Schema（Patent/PatentFamily/
MEMBER_OF_FAMILY/Keyword/OrganizationBase 各 +1 条 dwd_patent 源），干跑核对输出后删 4 条——
PatentFamily 与 MEMBER_OF_FAMILY 的 **A 裸表源**（脚本只读子表富集列，A 行无子表列 → 恒 0 输出，
纯浪费读取）与 Keyword、OrganizationBase 的 **B 富集源**（B 输出行是 A 输出的严格子集）。
Patent 保留 A+B（属性集真不相交）；4 个 Schema 单源化后绑定数 157，输出不变。

### 3.4 collation 三态（实测：external 库一库混 5 种排序规则）

| 场景 | 处理 |
| --- | --- |
| patent 族 patent_id join | 全系 utf8mb4_general_ci，**不写 COLLATE**（写了反而逼 hash join 丢索引序） |
| JSON 函数结果 join | 返回 utf8mb4_bin，与维表 industry_code 天然一致，无需处理 |
| tags.company_name(0900_ai_ci) × org.name_cn(general_ci) | **单侧** `COLLATE utf8mb4_general_ci`，表达式放无索引侧（company_name），保 name_cn 索引可用 |

### 3.5 终版探针结论（probe_final.log）

- 列审计：51 张 keep/promote 表的 pk + updated_time + is_deleted 全部在；dwd_scholar 无
  academician/research_fields 列（`s.*` + 派生表别名无 Duplicate column 风险）。
- 全量 43 条去重 SQL 按平台 keyset 包裹实跑 **43/43 OK**。
- 逐条时延（首批）：单表/小 join 全部 <1s；Person 10.2s；COVERS 10.7s；HAS_OUTPUT 7.9s；
  patent B 46.7s；**BELONGS 185.4s**（表达式 pk 无法下推索引，每批全扫 tags 219 万 ×
  JSON × 8 位炸开，24 批 ≈ **74 分钟一次性成本**，链任务可接受；若嫌慢可后续把 org 端
  改由 dwd_org_base_info 主键驱动——需再探针，暂不动）。

### 3.6 精简列集读取（10 表 22 绑定，缺陷㉘治本项之一）

实体链实测发现大文本列全列读取是三重瓶颈（源库带宽、payload 体积、活动内存），而脚本
真正消费的列很窄——把 10 张大表/大文本表的 querySql 从 `t.*` 收成显式列清单
（`SELECT t.dwd_id, t.<脚本消费列…>, t.updated_time FROM … WHERE t.is_deleted=0`）：

| 表 | 绑定 Schema | 精简后列 |
| --- | --- | --- |
| `dwd_zh_report` | Report / OrganizationBase | report_id, title_cn, abstract_cn, source_url（业务 4） |
| `dwd_en_report` | Report / OrganizationBase | report_id, title_en, source_url（业务 3） |
| `dwd_org_base_info` | Organization / Person / Product / LEGAL_REP_OF | 业务 21 列（去大文本备注类） |
| `dwd_org_important_news_info` | News / HAS_NEWS | 业务 8 列 |
| `dwd_org_recruit_info` | Event / INVOLVED_IN | 业务 7 列 |
| `dwd_org_opt_judicial_case` | Event / INVOLVED_IN | 业务 12 列 |
| `dwd_org_changerecord_info` | Event / INVOLVED_IN | 业务 7 列 |
| `dwd_org_company_punish` | Event / INVOLVED_IN | 业务 12 列 |
| `dwd_org_risk_shixin` | Event / INVOLVED_IN | 业务 13 列 |
| `dwd_org_risk_zhixing` | Event / INVOLVED_IN | 业务 10 列 |

**同表跨绑定列集一致性**：同一张表被多个 Schema 绑定时（如 org_base_info ×4）必须用同一条
querySql——实体 VID 是整行稳定哈希（`stable_record_id`），任何绑定多读/少读一列都会让
同一行在两个 Schema 下算出**不同 VID**，消歧/关系端点全乱。22 条绑定按表分组共享列清单。

效果（重触发执行实测）：精简后 org_base_info 189,116 行 95 批在分钟级读完（Product 环全量
11 来源含它 25 分钟内完成）；对照精简前同表全列读取干跑首批分钟级起步、Report 域 4 万点
爬行数小时。配合写图限步调后共享图库不再持续打高水位（§9 ㉘）。

## 4. 通用改写规则（R1–R5）

- **R1 keyset**：querySql 输出唯一 pk（表主键或唯一别名），timeColumn 留空。老绑定的
  ROW_NUMBER() 窗口 pk（数据变更即漂移）、常量 wm_col 水位、CONCAT 拼串 keyset 全部废除；
  keyset 唯一性要求 pk 严格唯一（游标推进 = 末行 pk，同 pk 行在批边界会丢）——BELONGS 的
  炸开行 pk = `dwd_id*8+ix` 保唯一。
- **R2 治理行**：querySql 一律 `WHERE is_deleted = 0`（实测样本库 0 命中，纯防御）。
  普通绑定（keep）无 WHERE 通道，OFFSET 全扫语义与旧一致。
- **R3 列对齐**：真实列 `AS 旧列名`；确实没有的列 `NULL AS 旧列名`（保脚本分支确定性，
  如 SUBSIDIARY_OF 国别两列、产业链 node_type 等）。
- **R4 collation**：按 §3.4 三态处理，表达式只放无索引侧。
- **R5 extra_json 透传**：治理列/新增列随 `SELECT t.*` 进 extra_json，无害且保留溯源。

## 5. 重写要点分域速览

### 5.1 报告域（2）
`dwd_en_report`：老 ROW_NUMBER 排序列外部已删 → `t.dwd_id AS row_pk`。Report + OrganizationBase 共用。

### 5.2 项目域（10）
zh/en project 的 output 计数 JOIN 结构原样（en 侧缺 books_count/degree_papers_count/awards_count/
output_awards 4 列 → NULL AS 兜底）；HAS_OUTPUT 的 UNION 过滤保留；FUNDED_BY/HAS_PARTICIPANT/
LEADS 的 `SELECT *` + is_deleted。

### 5.3 学者域（4，最重的结构重建）
外部 `dwd_scholar` 删掉扁平 work_experience_*（7 列）/ education_background_*（5 列），拆成
`dwd_scholar_work_experience` / `dwd_scholar_education_background`（scholar_id 外键）。重写：
- `Person/dwd_scholar`：派生表取每学者首条（`MIN(dwd_id)`）回拼 12 个旧扁平列名，
  自联结派生表加 LIMIT 阻 merge（物化后走 auto_key 查找）；academician 改
  `SUBSTRING_INDEX(GROUP_CONCAT(academician ORDER BY dwd_id DESC), ',', 1)` 派生表
  （= 老相关子查询「最后一条 talent_flag」语义；值是 int 无逗号风险）；research_fields 改
  `GROUP_CONCAT(fields ORDER BY dwd_id SEPARATOR '；')`（与老相关子查询同受
  group_concat_max_len=1024 约束，口径一致）。
- `STUDIED_AT/dwd_scholar`：只回拼教育 5 列；EXPLAIN 免 Sort（嵌套循环保序），1.0s/批。
- `AFFILIATED_WITH/dwd_scholar`：外部 dwd_scholar **有真实 scholar_org_id**（yft1 的
  NULL 桩口径本来就是 gkx_element 缺列的将就）→ 直接 `SELECT s.*` 透传，脚本走原始
  `org_{id}` 分支（恢复 yft1 之前的生产语义，机构端连通真实 dwd_org_base_info 主键）。
- `COAUTHOR_WITH`：`status=1` 过滤保留，pk=dwd_id。

### 5.4 专利域（5 Schema × A+B，见 §3.3）
老 5 表 LEFT JOIN + `JSON_EXTRACT(application_reference,'$.apno')` 全部换成外部原子列：
`apno/apdt/pbdt/kind`（dwd_patent）、`isdt`（grant_date）、`title_trans_cn`（title_zh）、
`abstract_trans_cn`（abstract_zh）、`reference_cited_count`（citation_nums）、
`simple_family_number`。`id REGEXP '^[0-9]+$'` 过滤随 id 列消失而废除。

### 5.5 forg 海外域（10 keep + 3 rewrite + 6 drop）
- 保留：base_info / product_info / executive_info / shareholder_info（列兼容）。
- 删绑：act_contro / beneficiary / stock_fin / subsidiary（见 §2 drop 行）。
- 影响：ACTUAL_CONTROLLER_OF、BENEFICIAL_OWNER_OF 两 EDGE 无源 → 0 条；Person 少 2 类
  自然人来源；Event/INVOLVED_IN 各少 1 个来源（其余来源照常）。

### 5.6 SUBSIDIARY_OF 换源（replace）
`dwd_forg_subsidiary_info`（外部缺）→ `dwd_org_subsidiary_info`（17.9 万行）：
`sub_org_id AS affiliate/affiliates_company_id`、`sub_name_cn AS affiliates_name`、国别两列 NULL。
端点解析走既有 resolver（精确唯一机构匹配），口径不变。

### 5.7 论文/引用域改写（5，干跑补漏两处结构漂移——缺陷㉒）
- `REFERENCED_BY/dwd_zh_report_paper`、`AUTHORED_BY/zh|en_author`：row_id 拼接公式不变 +
  is_deleted；zh_author 无 dwd_id → pk=pk_id。
- `CITES/dwd_zh_paper_citation`：外部列名是大写 **`DOI`**——MySQL 列名 SQL 层不区分大小写，
  但 pymysql DictCursor 行键**按声明返回**，`row.get("doi")` 取不到（干跑 0 边的根因）→
  显式列清单 `t.`DOI` AS doi`（不能 `t.*` + `t.DOI AS doi` 并存：MySQL 结果列重名检测
  大小写不敏感受 1060）。DOI 语义 = 被引方 doi（20031 行含 782 自引是真实数据）；
  citation_id_list 是完整列表但 yft1 行语义 = 每行一条边，**不做列表炸开**（会变超集，
  非同构）。
- `CITES/dwd_zh_paper_related`：yft1 预炸开（每关联项一行，doi 缺失时存 paperId）；
  外部是每论文一行 `relevant` JSON 数组（实测恒长 10）→ 0..9 数字表按位炸开
  （`pk_id*10+ix` 保 keyset 唯一），`doi ?? paperId` 兜底 = yft1 同口径。
- en 侧两表 1:1（relevant 全 NULL、单小写 doi）→ keep 原样。Paper/Journal/PUBLISHED_IN keep
  （改名全落在脚本 fallback 链上，实测无需改写）。

### 5.8 产业链域（8，见 §6）；DataSource 假绑定原样保留（自足占位）。

## 6. 产业链域语义映射定稿（方案 a）

外部两张产业链表与本地**同名但列全换**，且本地 `dwd_org_industry_chain_dtl` 外部缺表。
语义映射（全部经真实数据验证）：

### 6.1 维表 `dwd_industry_chain_info` 语义（1,273 行，12 链）

| 外部列 | 实测语义 | 用途 |
| --- | --- | --- |
| `industry_code` | 节点自身码：7 位 = 链行（12 条），9–21 位 = 节点行（1,261 条，最深 8 级） | node_id / chain_code |
| `industry_name` | 节点自身名（INB120401='零部件'） | node_name / chain_name |
| `industry_link_code` | **直接父节点码**（链行空串；1,261 非链行全有值，与编码前缀法推算完全吻合） | CHILD_OF 的 parent_id |
| `parent_code` | ⚠️ 错位列（存的是顶层链名'机器人'） | **不用** |
| `level` | 恒 0，不可信 | 用 `(CHAR_LENGTH(code)-7)/2` 派生层级 |

### 6.2 八个 Schema 的映射与实测量

| Schema | 来源 | 映射 | 样本库实测 |
| --- | --- | --- | --- |
| IndustryChain | 维表 | `industry_code AS chain_code, industry_name AS chain_name`（7 位行），pk=pk_id | **12 链** |
| IndustryNode | 维表 | `industry_code AS node_id, industry_name AS node_name`，level 按码长派生，node_type/seq/imp_level/stage/path NULL，pk=pk_id | **1,261 节点** |
| CHILD_OF | 维表 | `industry_link_code AS parent_id`（直接父），pk=pk_id | **1,261 边** |
| HAS_NODE | 维表 | `LEFT(industry_code,7) AS chain_code` | **1,261 边** |
| DOWNSTREAM_OF | 维表 | 恒空（`WHERE 1=0`；外部无 downstream 数据列） | **0 边**（九模块未用，无影响） |
| News（产业链） | news 表 | `id AS news_id, title AS news_title, abstract AS summary, publish_date AS relaese_date`，pk=pk_id | **108,052 实体** |
| COVERS_CHAIN | news×维表 | `JSON_OVERLAPS(链码单元素数组, news.industry_code)`；JSON_VALID 卫兵防无效行 | **94,560 边 / 58,520 新闻**，10.7s/批 × 19 批 |
| BELONGS_TO_NODE | tags 重建 | 见 6.3 | **≈116,180 边 / ≈27,160 org**（1/20 抽样外推） |

### 6.3 BELONGS_TO_NODE 语义重建（原 `dwd_org_industry_chain_dtl` 缺表）

`dwd_org_industry_tags`（2,197,216 行）的 `industry_link_code` 列存 **Python repr 数组串**
（`"['INB130602','INB150202']"`——单引号，**不是合法 JSON**；长度分布 11/21/31/…= 1–8 元素）。

1. `REPLACE(col, "'", '"')` 转 JSON → `JSON_VALID` 卫兵 + `LIKE '[%'` 前置（防错位行炸函数）；
2. 0..7 位按位 `JSON_EXTRACT` 炸开（UNION 数字表；出界位 NULL 被 JOIN 丢弃）——不用
   JSON_TABLE（商业版 9.7 上 JOIN 链报 1210）；
3. 节点码与维表 `industry_code` 精确 join（JSON 函数返回 utf8mb4_bin 与维表列天然一致，免 COLLATE）；
4. org 端 `dwd_org_base_info.name_cn = t.company_name COLLATE utf8mb4_general_ci`
   （单侧、表达式在无索引侧，name_cn 索引可用）→ `antitypic`（老口径 `org_{机构名}` vid）；
5. `chain_score` NULL（外部无打分列）；pk = `t.dwd_id*8 + i.ix` 保 keyset 唯一
   （每 tags 行炸开 ≤8 行）；代价见 §3.5（~74 分钟一次性）。

实测核对：首码路径 26,156 边 / 全码展开 ≈116,180 边；tags 的链级码与 12 链 overlap 达
2,283,761 行——「0 交集」是早前拿 repr 原串比裸码的假象。数据质量注意：tags 存在少量列
错位行（industry_code 装名字等），JSON_VALID 卫兵会自然丢弃，不影响正确行。

## 7. 预期量级与耗时（样本库口径，2026-10-11 实测 + 10-12 干跑定案）

域量级（e2e 对账锚点）：

- Product：**47,956**（**VID=产品名哈希** → 图上点数 = 归一名去重数，非脚本记录行数：
  org_org_product 45,011 行去重 44,601 名 + forg_product 20,000 行去重 3,355 名，
  跨源并集 47,956±1（源侧 SQL DISTINCT 实测）；hongkong/taiwan 外部表**无产品列** → 0
  产出，aomen 0、org_base 189,116 行读入产 0（org 表不吃 product 列，基线同构，其产出
  在 Organization 环）；图侧 LOOKUP 实测 47,956 ✓。早前 85,011 = 行数口径的误读，
  作废）
- 产业链：链 12 / 节点 1,261 / CHILD_OF 1,261 / HAS_NODE 1,261 / News 108,052 /
  COVERS_CHAIN 94,560 / BELONGS_TO_NODE ≈116,180 / DOWNSTREAM_OF 0
- 学者：dwd_scholar status=1 21,308（Person 10.2s/批 × 5）；coauthor status=1 1,186,871
- 专利：dwd_patent 2,690,167（A 9 分钟 + B 15 分钟，并发下域总 ~17 分钟）
- org：base_info 192,464；subsidiary 候选 178,874
- 大表 promote keyset 线性预估：recruit 670 万 ≈ 16 分钟、judicial 338 万 ≈ 11 分钟、
  changerecord 305 万 ≈ 10 分钟（0.7s/批 × 批数）
- 海外：ACTUAL_CONTROLLER_OF / BENEFICIAL_OWNER_OF 0 边（无源）；EXECUTIVE_OF forg 侧
  19,920 行、SHAREHOLDER_OF forg 侧 39,494 行
- CITES（干跑修 bug 后）：zh_citation ≈20,031 边；zh_related 炸开 ≤10×行数（≈20 万级，干跑
  200 行→200 边、多关联项论文逐项出边验证通过）

**干跑总账（2026-10-12，dryrun3.log）**：155 条非 drop 绑定 → 147 ok + 1 空
（DOWNSTREAM_OF WHERE 1=0 设计内）+ 5 无脚本（OUTPUT_OF×2/APPLIED_BY/OWNED_BY/INVENTED_BY
= 基线 0 边口径）+ 2 行失败（bankruptcy 127/200、forg_shareholder 1/199——本地
gkx_element_yft1 基线逐行复现同样失败，口径一致）+ 0 挂死/步失败。

**零输出嫌疑全定案**（探针证据，e2e 对账时按下表口径验收）：

| 嫌疑 | 定案 | 证据 |
| --- | --- | --- |
| STUDIED_AT（早前嫌疑） | 数据低 | 深采样 200 行 22 边（教育经历填充率低） |
| PUBLISHED_IN / dwd_en_paper | 数据 0 | publication_id 0/1,387 非空 |
| Keyword / dwd_en_project | 数据 0 | keywords 0/20,000 非空 |
| FUNDED_BY / dwd_zh_project | 数据 0 | funded_institution 0/58,453 非空（全表） |
| FUNDED_BY / dwd_en_project | 数据 0 | 列 100% 非空但全英文；org 名池仅 name_cn（外部 org 表无英文名列，DISTINCT 189,068）0 命中 → 图上 Organization.name_en 恒空 |
| LEADS / en_project | 数据低 | 候选人名命中 11/1,999（0.55%，scholar+author 名池 129,263）；zh 侧 568/2,000 健康产边 |
| HAS_PARTICIPANT / en_project | 数据低 | 15/3,328（0.45%）；zh 侧 3,105/11,238 |
| HAS_OUTPUT zh+en | **基线同构 0** | 老绑定本就只喂 `id+wm_col`，`output_journal_articles` 等 JSON 驱动列从未进 mapper（yft1 基线同样 0 边，脚本能力闲置）；rewrite 同构 |

LEADS/HAS_PARTICIPANT/FUNDED_BY/HAS_OUTPUT 是**图匹配器关系**（目标端点按名池在图上
精确匹配已入库实体），边数取决于关系链触发时图内已有实体——三链必须**实体链先完成**
再触发关系链（e2e_apply 按此串行触发）。

**耗时口径修订（缺陷㉘之后）**：原估「全链 2.5–3 小时」是纯读取时延外推，未计入共享图库
限步调（100 条/0.5s）与消歧/碰撞探测的查询成本。实测含名称消歧的实体环聚合写速
~50–200 条/s（Product 域 47,956 点 25 分钟）；按此口径 Patent 2.69M ≈ 4–8h、Event ~16M
≈ 1–2 天，实体链全程**以天计**。这是共享 trs-graph 宿主（静态内存 ~87%）下的安全上限，
不是平台瓶颈；换独占图库宿主或提高 watermark（需团队决议）可解除限速。e2e 批次取
2000/批（默认 500 会到 4 万批；payload S3 中转开着，批预算 8MB）。

## 8. 验证执行（gkx_verify_1 空间，进行中）

新开验证图空间 `gkx_verify_1`，走 yft1 e2e 形式（编排器
`artifacts/gkx-prod-bindings/e2e_apply.py`，api 容器内跑；setup/resume/trigger N/status）：

1. ✅ 数据源 `gkx-prod-sample` 注册（密码经 `GKX_SAMPLE_PASSWORD` 环境注入，不落盘）。
2. ✅ 49 Schema（16 实体 + 33 关系，graphSpace=gkx_verify_1，端点 id 重映射）+ 45 脚本
   （PUT 直存，语法+入口校验；LLM 通道绕开——r2 缺陷「LLM 校验不可复现」的兜底）。
3. ✅ 绑定 47 Schema / 155 条灌入（专利域 A+B 落库即缺陷㉓的修复验证）。
4. ✅ 干跑闭环（§7 总账）。
5. ⏳ 三链任务（batchSize 2000）：`gkx验证-实体链`（16）→ `关系链A`（14）→ `关系链B`（13），
   串行触发，实体链先行（图匹配器关系依赖图内实体）。
   - **首跑（05:10:37–13:36）**：Report/Project TAG 补建后 trs-graph 查询通道仍
     TagNotFound ~12 分钟（缺陷㉕），13:29:55 恢复写入、Report 落 1686 点后，worker
     事件循环拥塞引发 task 超时级联 → 执行冻结（缺陷㉖㉗）。
   - **恢复（14:00–14:08）**：部署 to_thread 修复（双容器）+ 重启 worker + terminate
     冻结执行 + 重触发（workflow id `chain-9e84ebcd9fb1-588b115d…`，水位断点续跑）；
     新执行 workflow task 0 超时，Report 3997 点且持续推进。
   - 首批抽查通过：VID=`report_{report_id}`、source_system="gkx"、match_method=
     source_primary_key、confidence=1.0、source_update_time 透传 ✅；`name=""` 是
     平台对 NOT NULL 列的兜底（脚本不输出 name，基线同口径）。
   - **老口径确认（非缺陷）**：report step 输出 `title`，而 yft1 目录 Report 只声明
     `title_cn/title_en` → 平台 `filtered()` 按 active_props 静默丢弃，基线同构
     （目录与脚本两侧同版本，行为一致；yft1 时代「脚本输出未声明属性被丢」的既有口径）。
   - **第二次执行（to_thread 修复后）**：Report 5,187→39,977 / 项目 78,453 落图，至
     Product 环撞上共享图库内存高水位整链 FAILED（缺陷㉘）。
   - **㉘ 三件套治理（已部署 api+worker 双容器）**：水位专用退避重试 + 写图限步调 +
     消歧/碰撞名单分块（§9）；精简列集手术（§3.6）+ 专利域删 4 条冗余绑定（§3.3 附注）
     经 `rebind_sources.py`（sources-only 重绑，不重建链任务）落库：13 Schema / 97 条。
   - **第四次重触发（水位断点续跑，执行 `chain-…-fcdf0e75`）**：科技成果/项目环 0 新行
     （游标已推，幂等验证 ✓）；Product 环 11 来源 25 分钟完成，脚本记录 65,011 条落图
     去重为 **47,956 点**（VID=名哈希，§7 修正口径；含 org_base 189,116 行精简列集
     分钟级读完产 0 产品的基线同构验证）；高水位退避从
     28–50 次/5min 降到 3 次/5min，宿主内存稳定 54–57Gi。Worker 热重启升级在飞执行的
     活动代码（不 terminate 不重触发，平台 activity 版本不钉死的特性验证 ✓）。
   - **监控时钟假象备忘**：监控脚本宿主时钟曾被 NTP 校正跳变（打点 15:2x → 23:2x 突变），
     排障时以 `docker inspect State.StartedAt`（UTC 真值）/ Temporal `start_time` 对时，
     别信监控打点的墙钟。
   - **第五次重触发（执行 `chain-…-b835fe6a`，㉙ 一段修复后）**：fcdf 执行在 Product 环尾部
     冻结（所有来源完成、#744 execute_transform Scheduled 33+ 分钟无 Started，见 §9 ㉙）；
     terminate 后部署 STS=300s 并重触发。新执行 90 秒内 703 事件正常推进，
     hongkong 等 OFFSET 来源全量重读（幂等 upsert），Product 环 36 秒完成
     （written=0 重放口径）推进至 Person 环；15:53–16:04 又逢图库高水位退避
     （4 槽占满排队背压，18 次 STS 超时），**16:04:21 整链 FAILED**——实锤
     STS 超时不受 RetryPolicy 保护（18 次超时无一任务烧到第 2 次重试仍终败），
     一段修复不成立，见 §9 ㉙ 二段结论。
   - **第六次重触发（执行 `chain-…-5fda90af`，㉙ 二段治本后）**：STS=300s + workflow 层
     重调度封装（§9）部署双容器并重启 worker 后重触发（16:43:54 UTC）；5 分钟 1290
     事件正常推进，scheduled 事件 STS=300s 全部上线、0 timed_out，推进到 Person 环
     （en_author 1,387 实体首写，过了第五次执行死点）。
   - **㉙ 修复自带的枚举名 bug → workflow task 连败 → ㉗ 楔死复现**：16:58 起首个 STS
     超时落到重调度封装上，封装内 `TimeoutType.SCHEDULE_TO_START` 引用了不存在的
     成员名（该 SDK 的 api 枚举是 protobuf EnumTypeWrapper，成员名带
     `TIMEOUT_TYPE_` 前缀）→ AttributeError 使 **workflow task** 连败 15 次
     （16:58–17:01），此后服务端进入㉗楔死形态：signal 被收下不落历史、无新
     workflow task、poller 健康，等 25 分钟+热修部署也不自愈。热修成员名
     （`TIMEOUT_TYPE_SCHEDULE_TO_START`）部署双容器 + terminate + **第七次重触发**
     （执行 `chain-…-dd6cad08`，17:26:49 UTC）：90 秒 493 事件、已完成环靠游标幂等
     秒过、直入 Person 环、0 workflow task 失败。教训：**workflow 层新代码上线后，
     首个 STS 超时才会执行到异常分支——deploy 后必须人工造一次背压/超时验证分支
     可达，否则 bug 藏到深夜**；㉗ 的楔死触发面比「task 超时」宽，**workflow task
     连败同样触发**（复现 runbook 同款：terminate + 重触发）。
   - **第七次执行收尾（21:11:52 UTC 整链 FAILED，缺陷㉚）**：Person 环推进到
     rows 308,319 / written 143,702（scholar 21,308/18,693、forg_executive 20,000/16,772、
     6/16 源完成，shareholder 42k/400k 长尾在写），㉙ 封装累计吸收 422 次 STS 排队
     超时（worker 告警与 history TIMED_OUT 1:1 吻合，无重放重复计数）；19:30–21:00
     图库高压期（水位退避 158/30m）两个 `resolve_entity_batch` 任务在 300s STC 内
     跑不完（召回 16 块查询 + 水位退避 10×20s 包络超窗口），RetryPolicy 5 次烧尽
     → STC 型 ActivityError 上抛（㉙ 封装按设计只兜 STS）→ 整链 FAILED。修复 =
     resolve STC 300→900s、detect_extract_collisions 120→300s（§9 ㉚），部署双容器
     + **第八次重触发**（执行 `chain-…-577de132`，21:43:31 UTC）：90 秒 332 事件、
     resolve STC=900s 上线、0 失败。教训：**STS 排队兜住了，但 STC 窗口必须 ≥
     活动内所有退避包络之和**（水位退避是 ㉘ 加的，当时没复核各活动 STC 余量）。
   - **第八次执行 FAILED（23:07:05 UTC，缺陷㉛）**：Person 环写到 rows 12,000/
     written 7,055 后，23:01 一个 `resolve_entity_batch`（attempt 4）遇水位
     application failure（`use space failed: Used memory hits the high watermark`）
     终败——19:30 起的高压窗持续 2h+，㉘ 的活动内退避（10×20s）+ RetryPolicy 5 次
     ≈ 20 分钟总容忍被打穿（㉚ 把 STC 放宽到 900s 只是把「超时烧尽」换成「退避烧尽
     后应用错误终败」，分钟级退避包络对小时级压力窗结构性不够）。修复 = ㉛ workflow
     层水位重发起（§9）部署双容器 + **第九次重触发**（执行 `chain-…-0acd667c`，
     23:29:08 UTC）：90 秒 326 事件 0 失败，重发起后首批消歧召回即在水位退避中
     （新分支的实战检验窗口）。
   - **排队预算 48→96（04:12 UTC 热部署，㉙ 预算二次放宽）**：第九次执行实测存在
     **单任务饥饿型排队**——一个 `resolve_entity_batch` 调用连续换位重发 33 轮
     （165+ 分钟，03:54–04:03 UTC 每 ~4.5 分钟 +1）无投递，同期兄弟任务在 1–8 深度
     正常轮转。㉙ 的换位旁路在持续过载的匹配层下对个体任务不保证公平，48 次
     （4h）预算按此速率 ~70 分钟内打穿 → STS 型终败。放宽到 96 次（8h）+ worker
     重启扰动匹配层（顺带热升级在飞执行）。部署后 /96 标签即时生效、最大深度
     回落到 29/96、链 RUNNING 0 失败（3 型/9 型/13 型全零）。
   - **第九次执行 FAILED（05:1x UTC，缺陷㉜）**：水位压力窗慢磨期（4 槽全在
     resolve 退避里，written 冻结 40+ 分钟），EV#4187 `ACT_FAILED retry=4`：
     `query/read 400: Storage Error: RPC failure, probably timeout`——storaged
     过载的第二种瞬态签名，不在水位正则内，㉘/㉛ 两层防线漏过 → RetryPolicy 烧尽
     整链 FAILED（链死在压力窗退去前一刻，随后水位计数归零）。修复 = 瞬态正则
     扩签名（§9 ㉜）部署双容器 + **第十次重触发**（执行 `chain-…-76bd0d3b`，
     05:20:40 UTC）：100 秒 411 事件、65 活动正常流转、0 超时 0 失败（压力窗已退）。
   - **第十次执行 FAILED（05:53 UTC，㉜ 第三签名）**：起飞全绿（100 秒 411 事件
     65 活动 0 失败），但 05:31:01 UTC `trsgraph` 容器被**干净重启**（ExitCode=0
     非 OOM 非 crash，人为/运维 bounce）——Nebula 重启窗口内 EV#507/513 两个
     活动 `query/read 500: java.net.ConnectException: Connection refused` 终败
     整链。㉜ 新标签已实战命中 5 次（RPC failure 类被正确退避），但连接层签名
     不在正则内又漏过。修复 = `_GRAPH_TRANSIENT_RE` 并入 `Connection (refused|
     reset)`（错误族收敛第三签名）部署双容器 + **第十一次重触发**（执行
     `chain-…-94d177c5`，05:55:12 UTC）：100 秒 317 事件 51 活动 0 失败 0 超时。
   - **第十一次执行 FAILED（宿主扩容迁移窗，㉜ 第四签名）**：执行起飞后不久宿主
     整栈迁移重启，graphd 未上线窗口内 EV#525 `query/read 500: create session
     failed` retry=4 终败整链。修复 = 正则并入 `create session failed`（02:43
     UTC 10-12 部署双容器）。
   - **宿主扩容迁移（~06:46 UTC 10-11，用户告知「服务器应该扩容了」）**：机器
     62Gi/16C → **125Gi / 32 vCPU AMD EPYC**，kernel 5.15.0-113 → -186，盘
     97G 不变；全部容器随宿主重启，仓库/工具幸存，链死 ~20h 后才被巡检发现。
   - **水位线回退发现（只报不动）**：迁移用 stock 镜像重建 trsgraph 后，
     `system_memory_high_watermark_ratio` 三份 conf 与运行时 flag 全部回落
     **0.8**——2026-09-30 团队决议的 0.9 只活在旧容器里（conf-in-image 改法
     不随镜像走）。新机 0.8 = 100Gi 绝对阈值（当前用量 ~22Gi），短期无害；
     恢复 0.9 = 改 conf + 重启 trsgraph + 同步 tech-kg-db Dockerfile，属共享
     基础设施团队动作，**待拍板，未擅动**。
   - **第十二次执行秒败（半截部署，非图库错误）**：EV#9 `ACT_FAILED retry=4:
     No module named 'biz.dependencies.shared_configs'`（19 个事件，首个活动
     即倒）——并行会话提交 9c7980ca 给 `load_schema_extract_plan` 加了该惰性
     import（经 merge 进本分支，宿主 temporal_workflows.py 与双容器 md5 一致），
     但 02:43 热部署只 cp 了 temporal_workflows.py 一个文件，新模块没跟上。
     修复 = `biz/dependencies/shared_configs.py` cp 双容器 + 28 个 import 闭包
     全量冒烟 + worker 重启 + **第十三次重触发**（执行 `chain-…-791a08ce`，
     02:53:06 UTC）：100 秒 337 事件 65 活动流转 0 失败。教训：**共享宿主上
     并行会话合过代码后，热部署单文件前先 md5 三方核对（宿主/api/worker）并
     扫部署文件的惰性 import 闭包**。
   - **第十三次执行·共享图库「死亡循环」事件（03:0x–03:4x UTC 10-12，用户转同事
     AI 反馈）**：Person 环 shareholder 长尾写图期，消歧同名召回的多列 OR 巨查
     （4 名字列 × 150 名/块 × 16 块 × 4 并发槽）在共享 trsgraph 上全 tag 扫
     （Person 147k 点），storaged CPU 394%→1772%、10 分钟 92 次 RPC 超时退避；
     同期 trsgraph 容器（**cap 64GiB**）OOMKilled 一次（03:20 同事 `docker restart`
     干净重启）+ dev2 同事的 `LOOKUP OFFSET 24000` / `Event SKIP 15400` 大查询
     共载。处置：`pause_extraction` 暂停链（在飞活动排空，重试风暴停）→ 定位为
     名字列无索引（§9 ㉝）→ gkx_verify_1 补 7 个名字列 TAG INDEX + REBUILD
     （jobs 2509-2513/2527-2528 全 FINISHED；OR 查询 0.85s→0.018s = 47×）→
     图库 CPU 回落 12% 后 `resume_extraction`。恢复后链健康：Person 环 rows
     154k / written 103.9k 推进，事件 2841→3053 增长中，0 workflow task 失败，
     图库 CPU 67% / 内存 4.4GiB / 64GiB。期间 `get_progress` 曾报
     `[TMPRL1100] Nondeterminism`——实为探针硬编码**第九次执行** id：旧 run 死于
     ㉜ 新签名，扩正则后其历史不可重放（§9 ㉝ 附带发现），当前执行查询正常。
   - **第十三次执行被 history-service 强杀（06:25:19 UTC，缺陷㉞）+ 第十四次重触发**：
     末环大源（975b9bb6，已写 2,280,000 行）推进中，链在 **51,201 事件**处被
     Temporal 服务器以 `identity=history-service, reason='Workflow history count
     exceeds limit.'` TERMINATED（auto-setup 1.29.2 默认 historyCountLimit≈50k；
     该 Temporal 为共享容器，配置不擅调）。处置 = runbook 同款直接重触发
     （按任务名反查 jobId：GET /workflow-system/jobs → POST …/trigger；
     e2e state 文件已被 /tmp 清空，不再依赖）。**第十四次执行**
     （`chain-…-c5487975`，06:4x UTC）：95 秒 722 事件、活动流转、0 失败——
     已完成环秒过、大源从游标续读。按 ~355 行/s 与每轮 ~50k 事件 ≈ 300 万行
     写入推算，剩余 ~1,600 万行 Event 域需 5–6 轮重触发循环（写入速率才是
     真瓶颈 ≈ 12h，循环空转可控）。
   - **环境备忘（容器 /tmp 会丢）**：04:14–04:46 UTC 间 api 容器 /tmp 被清
     （`/tmp/gkx-e2e/` 状态目录与探针脚本全没了，原因未查明——api 容器本轮未被
     重启）。处置：探针从宿主 `~/.claude/jobs/6c9295e5/tmp/` 重 `docker cp`；
     state.json 不用重跑 setup——`jobIds` 用 jobs API 按「gkx验证-实体链/关系链A/
     关系链B」反查重建（schema/绑定/脚本都在库里，state 只是 id 映射）。
   - **环境备忘**：同栈有两条历史 cron 任务会在链跑期间周期触发——`来个周期`
     （job-c0bcd1fd6ae6，cron 4×/天，抽 schema-extract-program，每次 0 行 no-op、
     游标已在尾）与 `222`（job-c81a067836c9，每日一抽）；definitionId 不同水位不
     互踩，负载可忽略，勿误判为链的干扰源。
   - **重放口径备忘（对账时勿误判）**：已落图数据重读后 `written=0` 是**增量写入计数**
     语义——重放行全部经消歧并入已有实体（merge 不计 written），非数据丢失；
     Product 环第五次执行 36 秒完成（hongkong 补读 40,000 行 written=0）即此形态。
     对账一律以图侧计数（LOOKUP/SHOW STATS）为准，不看执行详情的 written。
   - **STS 背压实测**：4 活动槽位（TEMPORAL_MAX_CONCURRENT_ACTIVITIES=4）在水位
     退避期被慢活动占满 → 排队任务 STS 到期**立即终败**（实测 18 次超时无一进入
     RetryPolicy 第 2 次重试，16:04:21 整链 FAILED）。单调 STS 时长无解（短=背压误伤、
     长=楔子久等），治本为 workflow 层重调度（§9 ㉙）：STS=300s 快速换任务位 +
     24 次重调度预算 = 2h 排队容忍。
6. ⏳ 跑完对账：§7 锚点逐项 + 抽查 VID 公式/属性集（能用前端就用前端——8093 平台 UI
   看任务进度与图查询）。监控：`~/.claude/jobs/6c9295e5/tmp/chain_monitor.log`
   （每 5 分钟任务状态 + LOOKUP 直数 + 高水位计数 + worker 错误尾）。

## 9. 本轮新增缺陷（沿用 yft1-r2 编号续排）

- **⑳ 平台无 socket 超时，公网半开连接挂死**：NAT 静默断连后 `pool_pre_ping` 无效
  （SELECT 1 写得进、读永久阻塞），干跑 INVOLVED_IN/company_illegal 挂死复现。
  修复：`infra/mysql.py` 统一 `connect_args`（connect 10s / read+write 600s，> BELONGS
  单批 185s），脚本层 `mysql_engine` 同步。已部署 api+worker 双容器。
- **㉑ 机构 resolver 每批全量装载**：`transform_org_relation` 每批 `load()` 全拉 7 张机构
  表——本地无所谓，公网源库 recruit 6.7M 行 = 6700 批 × 全量装载。修复：
  `load_resolver_cached()` 进程级 TTL（600s），单进程水位语义不变。
- **㉒ pymysql 行键大小写敏感 × MySQL 列名 SQL 层不敏感**：外部大写 `DOI` 列
  `row.get("doi")` 取不到（zh_citation 0 边）；且结果列重名检测大小写不敏感（`t.*` +
  `t.DOI AS doi` → 1060）。修复：显式列清单 + 别名（§5.7）。
- **㉓ `kg_schema_source` 唯一键不含 query_sql**：同表多条 querySql 绑定（专利域 A+B）
  PUT sources 即 500（应用层去重已含 querySql，DB 约束拦住第二行）。修复：唯一约束降为
  普通索引（db_model + `techkg_control_yunfei3` ALTER + 双容器部署）；真重复由
  sources 全量替换入口的应用层校验拦截。
- **㉔ 新建图空间后 Schema DDL 静默建丢**：CREATE SPACE 返回 ≠ schema 可见，传播延迟
  秒级到十秒级；`execute_schema_ddl` 3 次 × 1-2s 退避扛不住（gkx_verify_1 实测首两批
  Report/Project TAG 建丢），且 ddl_status=failed 只记定义行、创建 API 仍 200 → 抽取
  阶段才发现 TAG 不存在。修复：退避 5 次 × 2-10s（schema_ddl.py，链跑完后部署容器）；
  e2e_apply ③④ 显式断言 ddlStatus。本次 Report/Project 已用平台同款 `run_schema_ddl`
  手工补建 + name 索引 REBUILD，定义行 ddl_status 已纠正。
- **㉕ TAG 补建后写入通道仍分钟级 TagNotFound，write_records 重试窗口扛不住**：
  Nebula 侧 TAG 已存在（SHOW TAGS/DESCRIBE 直查 OK、索引 REBUILD OK），但 trs-graph
  查询通道对 DESCRIBE/INSERT 仍报 TagNotFound/No schema found **~12 分钟**
  （13:16→13:29 实测）。`write_records` 重试 5 次 × backoff≤30s ≈ 96s 窗口，若 worker
  空闲重试早燃尽 → 活动永久失败 → 整链 FAILED；本次侥幸存活（worker 事件循环拥塞顺带
  延迟了活动重投递，见㉖，13:29:55 起恢复 200 全量落图）。写入期 schema 可见性竞态
  与㉔（创建期）同族不同点：建议 write 路径对 TagNotFound/No schema found 单列
  重试策略（如 10 次 × 30s ≈ 5 分钟窗口），或 `write_with_self_heal` 扩展
  「TAG 缺失时按目录 DDL 自愈」。
- **㉖ worker 单事件循环被同步 I/O 串行化（已修，热部署生效）**：`write_records`/
  `read_source_batch` 等 `async def` 活动内部全同步阻塞 I/O（逐记录 HTTP INSERT、
  公网 MySQL 读），单事件循环上互斥 → TMPRL1104 workflow task 实测 70s、活动重投递
  延迟 12 分钟「假死」。修复：四个热路径活动的阻塞段整体下放 `asyncio.to_thread`
  （read_source_batch 读段 / write_records 逐记录写段 / resolve_entity_batch 同名召回 /
  detect_extract_collisions MATCH 探测）——活动体不参与 workflow 重放，热部署安全；
  修复后新执行 22 个 workflow task 全按时完成 0 超时。
- **㉗ workflow task 超时级联 → eviction 泄漏 → 执行冻结（无新任务调度）**：
  旧 worker 上 4 次 workflow_task_timed_out（10s STC）后，服务器**不再排新的
  workflow task**（history 停在 timed_out 无 204 事件，signal 被收下但不落历史），
  执行 RUNNING 但永久冻结 30+ 分钟；旧 worker 侧同时出现 `Failed running eviction
  job ... slot may remain forever used`（guarded_reader 的 finally 在取消时要往已满
  队列塞哨兵，塞不进 → 任务卡在 cancelling → eviction 失败循环）。恢复：terminate
  冻结执行 + 按水位断点重触发（平台幂等设计：Report 已写 1686 点为列级 upsert，
  重读无害；同时验证了断点续跑路径）。根因是㉖的连锁（task 超时→退避→eviction
  竞态），㉖修复后超时路径未再复现；**但 10-11 再次复现，触发面是 workflow task
  连败**（㉙ 修复自带枚举名 bug 使 wf task AttributeError 15 连败 3.5 分钟），败后
  同样进入「signal 被收下不落历史、无新 workflow task、poller 健康、热修部署也不
  自愈」的楔死（25 分钟无恢复，terminate + 第七次重触发解决，见 §8）。即楔死触发
  面不止 task 超时——任何 workflow task 连败（应用 bug / 非确定性错）都可能进该
  形态；guarded_reader 取消路径的队列满塞哨兵问题属平台遗留
  （本次未改——workflow 代码不可热更），复现时按「terminate + 重触发」runbook 处理。
- **㉘ 共享图库内存高水位打穿活动重试窗口 → 整链 FAILED**：trs-graph 与多个部署共享
  宿主（静态内存 ~87%），实体链全速写入（~1400 条/s 聚合）+ 消歧/碰撞的 2000 名单条
  MATCH 巨查把 storaged/graphd 推过 `system_memory_high_watermark_ratio=0.9`（2026-09-30
  团队决议值，不可擅动），此后**任何**查询（含 use space）报
  `Used memory hits the high watermark(0.900000)`；活动默认重试 5×≤30s ≈ 96s 窗口
  耗尽 → 整链 FAILED（第二次执行实锤）。水位压力是瞬态的（storaged 刷盘/查询上下文
  释放后分钟级回落），故修三处（`service/temporal_workflows.py` + `entity_disambiguation.py`，
  已部署双容器，重触发执行验证生效）：
  1. **水位专用退避** `_with_watermark_retry`：写图连接/DESCRIBE/逐条写图 18×20s、消歧
     召回 10×20s、碰撞探测 4×20s（各自卡在活动 STC 内），非水位错误原样上抛；
  2. **写图限步调** `SCHEMA_EXTRACT_WRITE_PACE_EVERY/SLEEP`（默认 100 条/0.5s，单活动
     ~110 条/s、4 并发聚合 ~450 条/s；0.35s 实测仍锯齿打线故收紧 0.5）；
  3. **消歧/碰撞名单分块**（150 名/条）：`recall_same_name` 与 `detect_extract_collisions`
     原先各把整批 2000 名塞单条 IN 巨查（+properties(v)），查询内存随名单线性膨胀——
     分块后单查询形状有界，且每块各自 LIMIT 200 比旧「全批一条任意截断 LIMIT 200」更完整。
  治本配套 = §3.6 精简列集（读侧减负）+ §7 耗时口径修订。水位回落自愈语义与游标幂等
  兼容：完成来源游标已推重读 0 行，中断来源全量重读（精简后代价小）。
- **㉙ 活动排队两段坑：匹配层楔子冻结 × STS 超时不进 RetryPolicy**（两段修复，终态
  为 workflow 层重调度）：
  1. **一段（无 STS → 永久冻结）**：fcdf 执行 Product 环全部来源完成、仅剩 hongkong 的
     一个 `execute_transform`（事件 #744）在 worker 热重启（15:17:30）同刻调度后
     **33+ 分钟无人认领**——worker poller 健康（DescribeTaskQueue last_access 10s 前）、
     input 仅 1KB（S3 claim-check 生效）、同型活动 168 个仅此 1 个不投递、无超时事件
     兜底 → `asyncio.gather` 上的来源协程永久挂起，整链冻结（服务端 matching 同期反复
     报 "Workflow task already started"，属 Temporal 匹配层与 worker 重启的竞态卡单）。
  2. **二段（STS 到期立即终败，不受 RetryPolicy 保护）**：一段后加 STS=300s 重触发
     （b835fe6a），运行 11 分钟后 16:04:21 整链 FAILED——高水位退避期 4 个活动槽位被
     慢活动占满（正常背压），排队任务 STS 到期即**活动终败**，18 次超时无一任务烧到
     RetryPolicy 第 2 次重试（Temporal 文档行为：ScheduleToStart 超时立即终败活动、
     不进重试策略）。即 **单调 STS 时长无解**：短 → 背压期排队任务被误伤整链 FAILED
     （300s 实测 5–11 分钟死）；长 → 匹配层楔子要等更久才自愈。
  **治本（已部署双容器，第六次执行 5fda90af 验证 STS=300s 上线）**：
  `schedule_to_start_timeout=300s` 快速换任务位 + workflow 层 `_execute_activity`
  重调度封装（`temporal_workflows.py`，全部 18 个调用点）——catch
  `ActivityError` 且 `failure.cause.timeout_failure_info.timeout_type ==
  SCHEDULE_TO_START` 时**重新发起**同一活动（新任务号重新进匹配队列，绕开卡死的
  匹配槽），预算 24 次 × 5 分钟 = 2h 排队容忍；匹配楔子经换位自愈，槽位背压在预算内
  续排队。异常驱动的循环在重放时按历史确定性复现，重放安全；其他失败原样上抛。
  **预算 24→48→96（4h→8h，第八/第九次执行期间热部署）**：16 源 × (reader+3 worker)
  并发争 4 个活动槽，叠加图库高压窗，实测任务链可连续排队 12+ 轮（4 条链同时打到
  12/24 评估线）——2h 容忍不够，08 执行起放宽到 48 次；09 执行又实锤**单任务饥饿型**
  排队（某 resolve 调用 33 轮换位重发 165+ 分钟无投递，同期兄弟任务 1–8 深度正常
  轮转）——换位旁路对持续过载下的个体任务不保证公平，48 结构性不够 → 96（8h）。
  常数上界改动对历史重放决策无影响（已记录的重调度全在小预算区间，新旧代码同判
  continue），可热部署不重触发（worker 重启即热升级在飞执行）。
  恢复按 ㉗ runbook：terminate + 重触发（水位幂等）。排障指纹：history 里
  `ACTIVITY_TASK_SCHEDULED` 无 `STARTED` 且无 timed_out、DescribeTaskQueue poller
  活着、worker 日志安静 = 匹配层楔子；批量 `TIMED_OUT(timeout_type=2)` 且
  attempt=1 直接终败 = STS-绕过重试策略（本条二段）。
- **㉚ 活动内退避包络超过 STC 窗口 → RetryPolicy 烧尽整链 FAILED**：㉘ 给写图/
  召回/碰撞探测加了水位专用长退避（resolve 召回 10×20s + 16 块×150 名分块查询、
  碰撞探测 4×20s），但没复核各活动 STC 余量——`resolve_entity_batch` STC=300s 在
  图库高压期合法跑超（水位退避 180s + 查询时间），重试同撞墙，5 次耗尽后 STC 型
  ActivityError 上抛（㉙ 封装只兜 STS 不兜 STC，按设计）→ 整链 FAILED（第七次执行
  21:11:52，两个任务 retry_state=4 MAXIMUM_ATTEMPTS_REACHED 实锤）。修复：
  resolve STC 300→**900s**、detect_extract_collisions 120→**300s**（留 3 倍/
  2.5 倍余量），部署双容器 + 第八次重触发验证上线。排障指纹：`TIMED_OUT`
  `timeout_type=1`（STC）且 `retry_state=4` = 活动合法超窗口烧尽重试（区别于
  ttype=2 的 STS 排队）。通用规则：**改活动内退避参数时，同步复核该活动
  start_to_close_timeout ≥ 退避总包络 + 正常执行时间**。
- **㉛ 高水位压力窗超活动内退避总包络 → application failure 终败整链**：㉘ 的
  活动内水位退避（各活动 4–18 次 × 20s）+ RetryPolicy 5 次 ≈ **20 分钟**总容忍，
  只够「分钟级瞬态窗」；实测共享宿主高压窗可持续 **2h+**（19:30–21:00、22:00–23:00
  连续两窗），活动内退避烧尽后以应用错误终败（第八次执行 23:01 实锤：
  `resolve_entity_batch` retry=4 报 `use space failed: Used memory hits the high
  watermark`），㉙ 封装按设计只兜 STS、㉚ 只放宽 STC，都接不住这一型。修复
  （workflow 层，`_execute_activity` 加第二分支）：catch ActivityError 且失败链
  （本体+3 层 cause）文案命中瞬态正则时 `workflow.sleep(120s)` 再重发起——sleep
  是 durable timer，**不占活动槽位**（终败活动已释放槽）、不烧 RetryPolicy；
  预算 30 次 × (120s + 活动内退避包络) ≈ 2–3h 压力窗容忍，与 STS 预算独立计数。
  幂等活动（读源/消歧/INSERT VERTEX upsert）重发起安全；水位游标语义与重触发同
  （未完成的来源全量重读，列级 upsert 无害）。排障指纹：history `ACTIVITY_TASK_
  FAILED` 且 failure 链含 "high watermark" + 整链 FAILED = 本型；修复后 worker 日志
  会出现「图库内存高水位终败（第 n/30 次），workflow 层歇 120s 后重发起」。
- **㉜ 图库通道瞬态错误第二/第三签名漏过两层防线 → 终败整链**：㉘ 只按水位
  单签名建防线，同因异签名的瞬态错误从缝里漏过——
  1. **第二签名（storaged RPC 超时）**：高压窗尾部 `Storage Error: RPC failure,
     probably timeout`（HTTP 400 内嵌），第九次执行 05:1x UTC 实锤 EV#4187
     retry=4 终败（链死在压力窗退去前一刻）；
  2. **第三签名（图库栈重启窗口）**：`trsgraph` 容器被干净重启（ExitCode=0 非
     OOM，05:31 UTC 实锤）的分钟级窗口内 `query/read 500: java.net.
     ConnectException: Connection refused`，第十次执行两个活动 retry=4 终败；
  3. **第四签名（graphd 迁移/重启窗）**：宿主扩容整栈迁移重启窗口内
     `query/read 500: create session failed`，第十一次执行 EV#525 retry=4 终败。
  修复（两层防线统一按错误族识别）：`_GRAPH_TRANSIENT_RE =
  high watermark|RPC failure|Connection (refused|reset)|create session failed`，
  ㉘ 活动内退避与 ㉛
  workflow 层 sleep 重发起共用；重试次数/包络不变（㉚ 的 STC 复核结论仍成立）。
  排障指纹：`ACTIVITY_TASK_FAILED` 且 failure 链含 Storage/RPC/Connect 字样 +
  整链 FAILED = 本型；修复后落入「遇图库瞬态错误（高水位/存储 RPC 超时）」退避
  日志（㉜ 第二签名已实战命中 5 次）。教训：**按错误文案逐签名建防线时，同因
  异签名的瞬态错误会从缝里漏过——识别条件按「错误族」而非单条文案收敛**。

- **㉝ 消歧同名召回的多名字列 OR 查询无索引 → 全 tag 扫打爆共享 storaged
  （「死亡循环」事件根因，2026-10-12 实锤）**：平台对 TAG 只自动建 `name` 单列
  索引；`recall_same_name` 按目录 DESCRIBE 对**全部**名字列（Person =
  name/name_cn/name_en/name_zh）发 `WHERE col1 IN […] OR col2 IN […] …`，
  多列 OR 使 name 索引失效 → 每 150 名块全扫 147k Person 点，16 块/批 × 4 并发
  槽把 storaged CPU 打满（394%→1772%；宿主内存反而 101Gi free——**是 CPU 问题
  不是内存问题**），storaged RPC 超时 → 活动重试风暴 → 图库更忙（与 trsgraph
  重启窗互相放大，即同事 AI 观测到的「你杀我、我拉你」）。**治本 = DDL 补名字列
  索引**（gkx_verify_1：Person 3 + Organization 2 + Journal 2 共 7 个 `col(64)`
  TAG INDEX + REBUILD；此后优化器对 OR 各列分别走 index seek，0.85s→0.018s =
  47×），**零代码改动、召回语义不变**（多列召回必要：3 个测试名经 name 索引
  0 命中、OR 四列 3 行命中）。**基础设施错配（待团队拍板，未擅动）**：trsgraph
  容器 cap = 64GiB 而宿主 125Gi——Nebula 水位线按宿主内存算（0.8×125Gi=100Gi），
  cgroup OOMKill 必然先于水位阀触发（03:0x 容器 OOMKilled 实锤），安全阀结构性
  失效；修复二选一：容器 cap 提至 ≥ 水位绝对值（如 96GiB），或水位按容器可用
  内存调整 + Dockerfile 同步 commit。**附带发现（排障乌龙 + 重放坑）**：㉜ 扩
  正则后，死于新增签名的旧执行（第九次）历史**不可重放**——query/update 报
  `[TMPRL1100] Nondeterminism`（新代码在旧终败点会走 sleep 重发起分支，Timer
  machine 撞上历史里的 WorkflowExecutionFailed）；已终败 run 无实际影响，但
  排障探针必须拿**当前执行** id，且对旧 run 的 replay 类操作（update/信号）
  在该场景不可用。

- **㉞ Temporal 历史事件数硬限（≈50k/执行）→ history-service 强杀长链（TERMINATED）**：
  第十三次执行在 51,201 事件处被服务器以 `reason='Workflow history count exceeds
  limit.'`（identity=history-service）终止——auto-setup 1.29.2 的默认
  historyCountLimit，非人为操作（yft1-r2 审计「Temporal 事件硬限」的实锤复现，
  小数据量 yft1 从未炸到）。触发面：单链全环事件累计 + ㉙ STS 重调度事件放大；
  **单 Schema 抽取同样中招**（recruit 670 万行 ≈ 54k 事件，独跑也超限）。
  处置（runbook 扩充）：`status=TERMINATED` 且 reason 为 history count →
  **直接重触发**——水位幂等断点续跑，每轮可吃 ~50k 事件 ≈ 300 万行写入；
  已完成环秒过、在飞源丢 ≤1 批幂等重做。治本方向（平台代码，待做）：链接近
  事件限时 continue-as-new（启动态全在平台 DB，CAN 换新历史、同 workflow id），
  或调大 dynamic config historyCountLimit（共享 Temporal 容器，团队动作）。
  排障指纹：histogram 出现 **type 27 = WORKFLOW_EXECUTION_TERMINATED**（事件映射
  表补一条）+ describe close_time；worker 日志尾随一条
  `Activity not found on completion … workflow execution already completed`
  （终杀后活动补完，写入已落地，幂等无害，勿当损伤）。

已知风险：外部库走公网，大表分批拉取耗时波动；BELONGS 每批 185s（24 批）是已知长尾，
若触发平台 activity 超时（read timeout 600s 内安全），可把该绑定单独拆任务跑。
