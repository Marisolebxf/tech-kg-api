# 专利 SQL → Graph 映射（第一阶段）

## 1. 映射范围

| 项目 | 设计 |
|---|---|
| 来源库 | `gkx_element` |
| 目标图空间 | `dev`；正式环境迁移到统一`gkx_graph` |
| 主Tag | `Patent` |
| Patent VID | `patent_{patent_id}` |
| 关联Tag | `Person`, `Organization`, `Keyword`, `Project`, `IndustryNode` |
| Patent属性 | 26个业务属性＋7个溯源属性 |
| 关系 | 7种事实Edge |

一条`dwd_patent`记录生成一个Patent顶点。七张专利表以`patent_id`关联并补充同一个Patent，不分别创建顶点。

字段路径规则：

- 普通字段直接写字段名，如`patent_id`。
- JSON对象写为`一级字段.子字段`，如`publication_reference.pbdt`。
- JSON数组写为`一级字段[].子字段`，如`inventors[].name`。
- `title_localized`、`abstract_localized`在实际库中是直接文本，不再追加`.en`。

## 2. 来源表与目标Schema

| 来源表 | 使用字段 | 目标Schema |
|---|---|---|
| `dwd_patent` | 基础、申请、公开、分类、关键词、发明人、申请人、权利人 | Patent、Person、Organization、Keyword及相关Edge |
| `dwd_patent_title` | 标题字段 | Patent属性 |
| `dwd_patent_abstract` | 摘要字段 | Patent属性/全文检索 |
| `dwd_patent_legal` | 当前状态、授权日期、预计到期日 | Patent属性 |
| `dwd_patent_cited` | 引用计数、专利引用、被引专利 | Patent属性、CITES |
| `dwd_patent_family` | 简单家族号 | Patent属性 |
| `dwd_patent_transfer` | 第一阶段不入图 | MySQL标准层 |
| `dwd_zh_project_output` | 项目产出专利 | OUTPUT_OF |
| `dwd_org_industry_tags` | 企业所属产业链节点 | BELONGS_TO_NODE |

## 3. Patent顶点映射

### 3.1 `dwd_patent`基础属性

| 来源字段/JSON路径 | 目标属性 | 类型/转换 |
|---|---|---|
| `patent_id` | `patent_id` | string；同时生成VID `patent_{patent_id}` |
| `publication_number` | `publication_number` | string |
| `application_reference.apno` | `application_number` | string |
| `application_kind` | `application_kind` | string |
| `country_code` | `country_code` | string |
| `country` | `country` | string |
| `publication_reference.pbdt` | `publication_date` | date，统一`YYYY-MM-DD` |
| `application_reference.apdt` | `application_date` | date，统一`YYYY-MM-DD` |
| `granted_number` | `granted_number` | string |
| `language` | `language` | JSON数组归一化为字符串 |
| `main_classification_ipcr` | `main_ipcr` | string |
| `further_classification_ipcr` | `further_ipcr` | JSON数组规范化并序列化 |
| `main_classification_cpc` | `main_cpc` | string |
| `further_classification_cpc` | `further_cpc` | JSON数组规范化并序列化 |
| `keywords` | `keywords` | 完整JSON数组规范化并序列化；Keyword实体优先取`zhName`，缺失时取`enName` |
| `value` | `patent_value` | int64 |

### 3.2 `dwd_patent_title`标题属性

| 来源字段/JSON路径 | 目标属性 | 转换 |
|---|---|---|
| `titles[].lang/text` | `title_original` | 优先取原文语言对应的`text`，缺失时取首个非空`text` |
| `title_localized` | `title_en` | 直接映射英文标题文本 |
| `title_zh` | `title_zh` | 直接映射 |

### 3.3 `dwd_patent_abstract`摘要属性

| 来源字段 | 目标属性 | 转换 |
|---|---|---|
| `abstract_zh` | `abstract_zh` | 直接映射 |
| `abstracts[].lang/content`, `abstract_localized` | 不进图 | 完整原文摘要和英文摘要进入全文检索 |

### 3.4 `dwd_patent_legal`法律状态属性

| 来源字段/JSON路径 | 目标属性 | 类型/转换 |
|---|---|---|
| `status` | `status` | string |
| `dates_of_public_availability.date` | `grant_date` | date，统一`YYYY-MM-DD` |
| `anticipated_expiration` | `anticipated_expiration` | date |

### 3.5 `dwd_patent_cited`引用统计属性

| 来源字段 | 目标属性 | 类型 |
|---|---|---|
| `reference_cited` | `citation_nums` | int64 |
| `cited_by_nums` | `cited_by_nums` | int64 |

### 3.6 `dwd_patent_family`家族属性

| 来源字段 | 目标属性 | 类型 |
|---|---|---|
| `simple_family_number` | `simple_family_number` | string |

## 4. 关系映射

### 4.1 专利表直接生成的关系

| Edge | 起点 | 终点 | 关系属性 | 来源字段 |
|---|---|---|---|---|
| `INVENTED_BY` | `patent_{patent_id}` | 匹配后的Person VID | `sequence` | `dwd_patent.inventors[].name/sequence` |
| `APPLIED_BY` | `patent_{patent_id}` | 匹配后的Organization/Person VID | `sequence` | `dwd_patent.applicants[].name/sequence` |
| `OWNED_BY` | `patent_{patent_id}` | 匹配后的Organization/Person VID | `sequence` | `dwd_patent.assignees[].name/sequence` |
| `CITES` | 引用方Patent VID | 被引用方Patent VID | 无 | `dwd_patent_cited.patent_citations/cited_by` |
| `HAS_KEYWORD` | `patent_{patent_id}` | `keyword_{md5(normalized)}` | 无 | `dwd_patent.keywords[].zhName/enName` |

#### 主体匹配规则

1. Person和Organization优先匹配全域权威ID。
2. 未匹配时使用规范化名称生成待消歧桩。
3. 原始名称不写入边属性，保留在来源表和装载审计中。

#### CITES方向规则

- `patent_citations`：当前专利为引用方，数组中的专利为被引用方。
- `cited_by`：数组中的专利为引用方，当前专利为被引用方。
- 只生成`CITES`，不重复生成`CITED_BY`。
- 目标专利无法可靠识别时不建边，保留原始数据待处理。

### 4.2 项目表生成的关系

| Edge | 起点 | 终点 | 关系属性 | 来源字段 |
|---|---|---|---|---|
| `OUTPUT_OF` | 匹配到的Patent VID | `project_{id}` | 无 | `dwd_zh_project_output.id`, `output_patents[].patent_number` |

匹配规则：

1. `dwd_zh_project_output.id`定位Project。
2. `patent_number`统一大小写并去除空格、连接符。
3. 依次精确匹配Patent的`patent_id`、`publication_number`、`granted_number`。
4. 无法可靠匹配时不建边。

### 4.3 产业链表生成的关系

| Edge | 起点 | 终点 | 关系属性 | 来源字段 |
|---|---|---|---|---|
| `BELONGS_TO_NODE` | 匹配到的Organization VID | `node_{industry_link_code}` | 无 | `dwd_org_industry_tags.company_name/credit_code/industry_link_code` |

匹配规则：

1. `company_name/credit_code`定位全域Organization。
2. `industry_link_code`定位IndustryNode。
3. 无法可靠匹配Organization时不建边。
4. Patent通过`APPLIED_BY/OWNED_BY → Organization → BELONGS_TO_NODE`间接关联产业链。

## 5. 边溯源属性

所有Edge统一保存：

| 属性 | 来源/规则 |
|---|---|
| `source_table` | 实际生成该关系的来源表 |
| `source_record_id` | 来源主键；JSON数组关系使用主记录ID＋数组序号 |
| `ingest_batch` | ETL运行批次 |
| `ingest_time` | ETL写入时间 |

## 6. Patent溯源属性映射

| 目标属性 | 来源/规则 |
|---|---|
| `source_system` | 固定`gkx_element` |
| `source_table` | 固定`dwd_patent` |
| `source_record_id` | `dwd_patent.patent_id` |
| `source_url` | 当前无统一地址，置空 |
| `ingest_batch` | ETL运行批次 |
| `ingest_time` | ETL写入时间 |
| `source_update_time` | `dwd_patent.update_time` |

## 7. 分类字段处理（不建实体和边）

IPC/IPCR、CPC保留为Patent属性，并展开到MySQL/分析层分类明细表：

| 明细字段 | 来源 |
|---|---|
| `patent_id` | `dwd_patent.patent_id` |
| `scheme` | 固定`IPCR`或`CPC` |
| `classification_code` | 主分类或附加分类号 |
| `is_main` | 主分类=true，附加分类=false |
| `sequence` | 附加分类数组顺序 |
| `source_record_id` | 来源记录ID |

## 8. 第一阶段不入图的数据

| 字段组 | 保存位置 |
|---|---|
| PCT、详细优先权、分案/继续申请 | MySQL标准层 |
| agents、agency、examiners | MySQL标准层 |
| LOC、FI、UPC、F-term | MySQL标准层 |
| claims、description、完整多语言摘要 | MySQL/全文检索 |
| figures | 对象存储/文档服务 |
| 非专利引用 | MySQL标准层 |
| 完整法律/PRS事件 | MySQL标准层 |
| `dwd_patent_transfer` | MySQL标准层 |
| 完整家族成员及家族引用 | MySQL标准层 |
| 各表管理字段 | MySQL/装载审计 |

以上数据不删除，通过`patent_id`或`source_record_id`回查。

## 9. 数据转换约束

1. `patent_id`非空且唯一。
2. JSON数组先展开为明细，再创建边。
3. 人员和机构先规范化、判断主体类型并消歧。
4. 日期统一为`YYYY-MM-DD`。
5. 空数组统一为`[]`，空值不写字符串`null`。
6. 关键词和IPC/CPC统一格式。
7. 相同VID和相同来源关系重复装载时幂等覆盖。
8. 当前装载代码已按本设计写入33个Patent属性；关系Edge由后续独立任务装载。
