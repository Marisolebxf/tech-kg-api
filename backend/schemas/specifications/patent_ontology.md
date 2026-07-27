# 专利本体设计（第一阶段）

## 1. 业务目标

专利本体用于支撑以下业务：

1. 专家专利成果查询：查询专家发明、共同发明的专利。
2. 专家直接关系：以共同专利作为专家合作的直接证据。
3. 专家间接关系：通过专利、申请机构、权利机构和关键词发现关联路径。
4. 两点合作成果：汇总两名专家的共同专利、合作次数、时间和成果影响力。
5. 专家—企业关系：识别专家与专利申请机构、当前权利机构之间的成果合作。
6. 专家技术方向：利用专利关键词、IPC/CPC分类分析专家研究方向。

专利数据不能单独证明同事或校友关系。同事关系需要任职经历，校友关系需要教育经历。

## 2. 模型概览

- 图空间：`dev`（正式环境迁移到统一 `gkx_graph`）。
- 专利Tag：`Patent`。
- Patent VID：`patent_{patent_id}`。
- 实体类型沿用全域本体，不因当前专利表缺少关联字段而删除。
- 专利业务涉及6类既有实体；基于已确认的专利、项目和产业链数据可落地7类必要事实关系和33个Patent属性。

## 3. 实体类型

| Tag | 数据来源 | VID | 在专利业务中的作用 |
|---|---|---|---|
| `Patent` | `dwd_patent`及六张专利要素分表 | `patent_{patent_id}` | 专利成果主体 |
| `Person` | `dwd_patent.inventors` | 权威人员ID优先，否则待消歧ID | 发明人、科技专家 |
| `Organization` | applicants、assignees | 权威机构ID优先，否则待消歧ID | 申请机构、当前权利机构 |
| `Keyword` | `dwd_patent.keywords[].zhName/enName` | `keyword_{md5(normalized)}` | 专利主题和跨域主题聚合 |
| `Project` | 全域项目数据 | `project_{project_id}` | 项目实体已存在；当前七张专利表没有项目关联字段 |
| `IndustryNode` | 全域产业链数据 | `node_{node_id}` | 产业链节点已存在；当前七张专利表没有节点关联字段 |

IPC/IPCR、CPC不建实体，作为Patent属性并同步到分类明细表。`Project`和`IndustryNode`保留为既有实体，但当前不生成专利到它们的关系；`Technology`、`Award`、`Classification`、`PatentFamily`、`PatentApplication`、`Document`和专利`Event`第一阶段不建。

## 4. Patent属性

### 4.1 核心业务属性（26个）

| 属性 | 类型 | 业务含义 |
|---|---|---|
| `patent_id` | string | 专利唯一标识 |
| `publication_number` | string | 专利公布号 |
| `application_number` | string | 专利申请号 |
| `application_kind` | string | 专利申请类型 |
| `country_code` | string | 国家/地区代码 |
| `country` | string | 国家/地区名称 |
| `publication_date` | date | 公开日期 |
| `application_date` | date | 申请日期 |
| `granted_number` | string | 授权号 |
| `grant_date` | date | 授权日期 |
| `status` | string | 当前法律状态 |
| `anticipated_expiration` | date | 预计到期日 |
| `title_original` | string | 原文标题 |
| `title_en` | string | 英文标题 |
| `title_zh` | string | 中文标题 |
| `abstract_zh` | string | 中文展示摘要 |
| `language` | string | 原文语言 |
| `main_ipcr` | string | IPC/IPCR主分类 |
| `further_ipcr` | string | IPC/IPCR附加分类 |
| `main_cpc` | string | CPC主分类 |
| `further_cpc` | string | CPC附加分类 |
| `keywords` | string | 关键词检索快照 |
| `citation_nums` | int64 | 引用专利数量 |
| `cited_by_nums` | int64 | 专利被引数量 |
| `patent_value` | int64 | 专利价值 |
| `simple_family_number` | string | 简单家族号，用于成果去重 |

### 4.2 溯源属性（7个）

| 属性 | 类型 | 含义 |
|---|---|---|
| `source_system` | string | 来源系统 |
| `source_table` | string | 主来源表 |
| `source_record_id` | string | 来源记录ID |
| `source_url` | string | 原文地址 |
| `ingest_batch` | string | 入图批次 |
| `ingest_time` | datetime | 入图时间 |
| `source_update_time` | datetime | 来源更新时间 |

## 5. 关系类型

### 5.1 源数据事实关系

| Edge | 方向 | 关系说明 | 属性 | 属性说明 | 来源 |
|---|---|---|---|---|---|
| `INVENTED_BY` | Patent → Person | 表示某人是该专利的发明人 | `sequence` | 该人员在当前专利发明人列表中的顺序 | `dwd_patent.inventors` |
| `APPLIED_BY` | Patent → Organization/Person | 表示专利申请时的申请主体 | `sequence` | 该主体在当前专利申请人列表中的顺序 | `dwd_patent.applicants` |
| `OWNED_BY` | Patent → Organization/Person | 表示专利当前归属的权利主体 | `sequence` | 该主体在当前专利权利人列表中的顺序 | `dwd_patent.assignees` |
| `CITES` | Patent → Patent | 表示一项专利引用另一项专利 | 无 | 无 | `dwd_patent_cited.patent_citations/cited_by` |
| `HAS_KEYWORD` | Patent → Keyword | 表示专利包含某个主题关键词 | 无 | 无 | `dwd_patent.keywords` |
| `OUTPUT_OF` | Patent → Project | 表示该专利是某个项目的产出成果 | 无 | 无 | `dwd_zh_project_output.output_patents` |
| `BELONGS_TO_NODE` | Organization → IndustryNode | 表示机构归属于某个产业链节点，供专利间接关联产业链 | 无 | 无 | `dwd_org_industry_tags` |

每条边统一保存以下溯源属性：

| 属性 | 属性说明 |
|---|---|
| `source_table` | 生成该关系的来源表名 |
| `source_record_id` | 来源记录ID；JSON数组关系可使用主记录ID与数组序号组成组合键 |
| `ingest_batch` | 本次入图任务的批次号 |
| `ingest_time` | 该关系写入图数据库的时间 |

## 6. 业务查询路径

本节仅说明如何组合已存储的实体和事实边完成查询，不定义新的Edge，也不将查询结果写入图数据库。

| 业务场景 | 图查询路径 |
|---|---|
| 专家专利成果 | Person ← INVENTED_BY — Patent |
| 两名专家共同专利 | Person ← INVENTED_BY — Patent — INVENTED_BY → Person |
| 专家—企业合作 | Person ← INVENTED_BY — Patent → APPLIED_BY/OWNED_BY → Organization |
| 专家技术相似 | 比较两名专家专利的Keyword和IPC/CPC属性重合度 |
| 专家间接关系 | 通过Patent、Organization、Project、Keyword和IndustryNode进行路径分析 |
| 项目专利成果 | Patent — OUTPUT_OF → Project |
| 专家—产业链 | Patent → Organization — BELONGS_TO_NODE → IndustryNode |
| 成果影响力 | Patent.citation_nums、cited_by_nums、patent_value |

共同发明、技术相似和专家—企业合作均通过上述路径查询，不新增或物化对应Edge。`OUTPUT_OF`由项目产出表生成，`BELONGS_TO_NODE`由产业链企业标签表生成；专利通过机构间接关联产业链节点。

## 7. 不进入第一阶段图谱的数据与数据缺口

| 数据 | 保留位置 |
|---|---|
| PCT、详细优先权、分案/继续申请 | MySQL标准层 |
| agents、agency、examiners | MySQL标准层 |
| LOC、FI、UPC、F-term | MySQL标准层 |
| claims、description、完整多语言摘要 | MySQL/全文检索 |
| figures | 对象存储/文档服务 |
| 非专利引用 | MySQL标准层 |
| 完整法律/PRS事件 | MySQL标准层 |
| 专利转让历史 | MySQL标准层 |
| 完整家族成员及家族引用 | MySQL标准层 |
| 各表管理字段 | MySQL/装载审计 |

以上数据不删除，通过`patent_id`或`source_record_id`回查。
