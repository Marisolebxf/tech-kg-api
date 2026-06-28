# 知识图谱构建统一规范

版本：v1.0.0
更新日期：2026-06-28
维护人：tech-kg-api 团队

---

## 目录

1. [概述](#1-概述)
2. [实体类型定义](#2-实体类型定义)
3. [关系类型定义](#3-关系类型定义)
4. [VID 唯一标识规则](#4-vid-唯一标识规则)
5. [MySQL 到图数据库映射规则](#5-mysql-到图数据库映射规则)
6. [模块结果回写规范](#6-模块结果回写规范)
7. [新增实体/关系维护流程](#7-新增实体关系维护流程)

---

## 1. 概述

### 1.1 背景

本项目数据源为第三方 MySQL 数据库（`gkx`，93 张表，12 个数据域），通过实体对齐、实体消歧、规则抽取和大模型分析，从 MySQL 原始表中抽取实体和关系，写入 TRSGraph 图数据库，供九个知识推理模块使用。

### 1.2 数据流

```
MySQL(gkx) 原始数据
    ↓ 实体对齐 + 消歧 + 规则抽取 + 大模型分析
TRSGraph 图数据库（统一 Schema）
    ↓ 九个模块推理
推理结果 → 写回图数据库（完善边）+ 写回 MySQL（间接关系表）
    ↓ 前端展示
```

### 1.3 规范目的

- 统一实体类型命名，避免"高校/学校/机构"等多种叫法
- 统一实体属性字段，避免 `org_name`/`institution_name`/`unit_name` 同义多字段
- 统一关系类型和属性，确保九个模块共用同一套边类型
- 统一 VID 规则，避免同一实体被不同模块重复建点
- 统一 MySQL 映射规则，明确哪些表映射为哪些实体/关系
- 统一模块结果回写格式，避免每个模块各自定义结果结构

### 1.4 九个模块清单

| # | 模块代码 | 模块名称 | 主要输入 | 主要产出关系 |
|---|---------|---------|---------|------------|
| 1 | `expert_direct_relation` | 科技专家/人才直接关系 | Scholar + 图谱数据 | direct_relation |
| 2 | `expert_indirect_relation` | 科技单节点间接关系 | Scholar + 图谱数据 | indirect_relation |
| 3 | `expert_cooperation_achievement` | 科技两点合作成果 | 两个 Scholar | cooperation_output |
| 4 | `expert_colleague_relation` | 科技专家同事关系 | Scholar + 机构任职数据 | colleague |
| 5 | `expert_alumni_relation` | 科技专家校友关系 | Scholar + 教育背景数据 | alumni |
| 6 | `expert_paper_cooperation` | 科技专家论文合作关系 | Scholar + 论文数据 | paper_cooperation |
| 7 | `expert_enterprise_relation` | 重点关注科技企业关系 | Scholar + 企业数据 | enterprise_related |
| 8 | `industry_chain_topn_event` | 科技产业链点TOP-N事件关系 | 产业链节点 + 事件数据 | node_key_event |
| 9 | `industry_chain_panorama` | 科技产业链全景图 | 全产业链数据 | 多种关系聚合 |

---

## 2. 实体类型定义

### 2.1 实体类型总览

| # | 实体类型 | 中文名 | VID 前缀 | 来源 MySQL 数据域 |
|---|---------|--------|---------|-----------------|
| 1 | **Scholar** | 人才/学者 | `SCH` | scholar（6 表） |
| 2 | **ZhPaper** | 中文论文 | `ZPP` | chinese_paper（4 表） |
| 3 | **EnPaper** | 外文论文 | `EPP` | foreign_paper（6 表）+ paper_common（2 表） |
| 4 | **Patent** | 专利 | `PAT` | patent（9 表） |
| 5 | **ZhProject** | 国内项目 | `ZPJ` | domestic_project（2 表） |
| 6 | **EnProject** | 国外项目 | `EPJ` | foreign_project（2 表） |
| 7 | **DomInstitution** | 国内机构（含企业） | `DIN` | domestic_organization（41 表） |
| 8 | **ForInstitution** | 国外机构（含企业） | `FIN` | foreign_organization（10 表） |
| 9 | **IndustryChain** | 产业链 | `ICH` | industry_chain（5 表） |
| 10 | **ChainNode** | 产业链节点 | `ICN` | industry_chain（5 表） |
| 11 | **Technology** | 技术/知识单元 | `TEC` | 从论文关键词、专利 IPC、报告主题提取 |
| 12 | **Industry** | 行业 | `IND` | 产业链节点分类、机构行业标签 |
| 13 | **Policy** | 政策 | `POL` | policy（4 表） |
| 14 | **Event** | 事件 | `EVT` | 产业资讯、新闻挖掘 |
| 15 | **Region** | 地区 | `REG` | 机构地址、人才流动 |
| 16 | **Product** | 产品 | `PRD` | 机构产品信息 |

### 2.2 统一命名原则

| 原则 | 说明 | 示例 |
|------|------|------|
| 中文/外文分开 | 论文、项目、机构按来源分国内/国外两种实体类型 | ZhPaper vs EnPaper |
| 机构包含企业 | 不单独建"企业"实体类型，企业是 Institution 的 sub_type | DomInstitution(sub_type=enterprise) |
| 属性名 snake_case | 所有图数据库属性统一用下划线命名 | `name_zh`, `paper_nums` |
| 同义属性统一 | 同一含义只保留一个属性名 | 统一用 `org_name`，不用 `institution_name`/`unit_name` |

### 2.3 Scholar（人才/学者）

图数据库标签：`Scholar`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| scholar_id | string | 是 | 学者唯一ID | dwd_scholar | scholar_id |
| name_zh | string | 是 | 中文姓名 | dwd_scholar | name_zh |
| name_en | string | 是 | 英文姓名 | dwd_scholar | name_en |
| avatar_url | string | 否 | 头像URL | dwd_scholar | avatar |
| bio | string | 否 | 英文简介 | dwd_scholar | bio |
| bio_zh | string | 否 | 中文简介 | dwd_scholar | bio_zh |
| paper_nums | int | 是 | 论文数量 | dwd_scholar | paper_nums |
| citation_nums | int | 是 | 被引数量 | dwd_scholar | citation_nums |
| h_index | int | 是 | H指数 | dwd_scholar | h_index |
| is_academician | boolean | 否 | 是否院士 | dwd_scholar_talent_flag | academician |
| research_directions | string | 否 | 研究方向(JSON) | dwd_scholar_research_direction | fields |
| current_org_name | string | 否 | 当前机构名称 | dwd_scholar | scholar_org_name_zh |

### 2.4 ZhPaper（中文论文）

图数据库标签：`ZhPaper`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| paper_id | string | 是 | 论文唯一ID | dwd_zh_paper | id |
| title | string | 是 | 论文标题 | dwd_zh_paper | ch_name |
| authors | string | 否 | 作者列表(JSON) | dwd_zh_author | zh_name |
| doi | string | 否 | DOI号 | dwd_zh_paper | doi |
| abstract | string | 否 | 摘要 | dwd_zh_paper | ch_abstract |
| keywords | string | 否 | 关键词 | dwd_zh_paper | keywords |
| publish_date | string | 否 | 发表日期 | dwd_zh_paper | cover_date_start |
| citation_nums | int | 否 | 被引次数 | dwd_scholar_paper_relation | citations |
| paper_url | string | 否 | 论文链接 | dwd_scholar_papers | paper_url |
| journal_name | string | 否 | 期刊名称 | dwd_zh_journal | journal_name |

### 2.5 EnPaper（外文论文）

图数据库标签：`EnPaper`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| paper_id | string | 是 | 论文唯一ID | dwd_en_paper | id |
| title | string | 是 | 论文标题 | dwd_en_paper | en_name |
| authors | string | 否 | 作者列表(JSON) | dwd_en_author | en_name |
| doi | string | 否 | DOI号 | dwd_en_paper | doi |
| abstract | string | 否 | 摘要 | dwd_en_paper | en_abstract |
| keywords | string | 否 | 关键词 | dwd_en_paper | keywords |
| publish_date | string | 否 | 发表日期 | dwd_en_paper | cover_date_start |
| citation_nums | int | 否 | 被引次数 | dwd_en_paper_cited_by | citation_nums |
| paper_url | string | 否 | 论文链接 | dwd_en_paper | paper_url |
| journal_name | string | 否 | 期刊名称 | dwd_en_journal | journal_name |

### 2.6 Patent（专利）

图数据库标签：`Patent`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| publication_number | string | 是 | 公布号(唯一ID) | ods_patent | publication_number |
| title | string | 否 | 专利标题 | ods_patent | title_localized |
| abstract | string | 否 | 摘要 | ods_patent | abstract_localized |
| application_number | string | 否 | 申请号 | ods_patent | application_number |
| filing_date | string | 否 | 申请日期 | ods_patent | filing_date |
| grant_date | string | 否 | 授权日期 | ods_patent | grant_date |
| ipc | string | 否 | IPC分类号(JSON) | ods_patent | ipc |
| citation_nums | int | 否 | 引用数量 | ods_patent | citation_nums |

### 2.7 ZhProject（国内项目）

图数据库标签：`ZhProject`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| project_number | string | 是 | 项目编号(唯一ID) | ods_zh_project | project_number |
| title | string | 是 | 项目名称 | ods_zh_project | title |
| project_source | string | 否 | 项目来源 | ods_zh_project | project_source |
| project_level | string | 否 | 项目级别 | ods_zh_project | project_level |
| fund_category | string | 否 | 基金类别 | ods_zh_project | fund_category |
| funded_amount | float | 否 | 资助金额 | ods_zh_project | funded_amount |
| discipline | string | 否 | 学科 | ods_zh_project | discipline |
| project_host | string | 否 | 项目负责人 | ods_zh_project | project_host |

### 2.8 EnProject（国外项目）

图数据库标签：`EnProject`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| project_number | string | 是 | 项目编号(唯一ID) | ods_en_project | project_number |
| title | string | 是 | 项目名称 | ods_en_project | title |
| project_source | string | 否 | 项目来源 | ods_en_project | project_source |
| project_level | string | 否 | 项目级别 | ods_en_project | project_level |
| fund_category | string | 否 | 基金类别 | ods_en_project | fund_category |
| funded_amount | float | 否 | 资助金额 | ods_en_project | funded_amount |
| discipline | string | 否 | 学科 | ods_en_project | discipline |
| project_host | string | 否 | 项目负责人 | ods_en_project | project_host |

### 2.9 DomInstitution（国内机构，含企业）

图数据库标签：`DomInstitution`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| org_id | string | 是 | 机构唯一ID | dwd_org_reg_info | org_id |
| name_zh | string | 是 | 中文名称 | dwd_org_reg_info | name_cn |
| name_en | string | 否 | 英文名称 | dwd_org_reg_info | name_en |
| sub_type | string | 是 | 机构子类型 | 见下方枚举 | — |
| social_credit_code | string | 否 | 统一社会信用代码 | dwd_org_reg_info | social_credit_code |
| province | string | 否 | 所在省份 | dwd_org_reg_info | province |
| city | string | 否 | 所在城市 | dwd_org_reg_info | city |
| address | string | 否 | 地址 | dwd_org_reg_info | address |
| incorporation_year | int | 否 | 成立年份 | dwd_org_reg_info | incorporation_year |
| listing_status | string | 否 | 上市状态 | dwd_org_stock_base | listing_status |
| stock_code | string | 否 | 股票代码 | dwd_org_stock_base | stock_code |
| univ_type | string | 否 | 高校类型(仅高校) | dwd_org_hels_info | univ_type |
| industry | string | 否 | 所属行业 | dwd_org_tag_info | org_tag |
| org_desc | string | 否 | 机构描述 | dwd_org_hels_info | org_desc |

**sub_type 枚举值：**

| sub_type 值 | 中文名 | 说明 | 来源表 |
|-------------|--------|------|--------|
| `university` | 高校 | 国内高等院校 | dwd_org_hels_info |
| `research_institute` | 科研院所 | 国内科研机构 | dwd_org_hels_info |
| `enterprise` | 企业 | 国内企业/公司 | dwd_org_reg_info |
| `government` | 政府机关 | 政府部门 | dwd_org_reg_info |

### 2.10 ForInstitution（国外机构，含企业）

图数据库标签：`ForInstitution`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| org_id | string | 是 | 机构唯一ID | dwd_forg_base_info | ename_en |
| name_zh | string | 否 | 中文名称 | dwd_forg_base_info | — |
| name_en | string | 是 | 英文名称 | dwd_forg_base_info | ename_en |
| sub_type | string | 是 | 机构子类型 | 固定为 `foreign_enterprise` | — |
| country | string | 否 | 所在国家 | dwd_forg_base_info | address |
| start_year | int | 否 | 成立年份 | dwd_forg_base_info | start_year |
| industry | string | 否 | 所属行业 | dwd_forg_industry | industry |
| employees_num | int | 否 | 员工数量 | dwd_forg_base_info | employees_num |
| address | string | 否 | 地址 | dwd_forg_base_info | address |
| org_desc | string | 否 | 机构描述 | dwd_forg_profile | profile |

### 2.11 IndustryChain（产业链）

图数据库标签：`IndustryChain`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| chain_code | string | 是 | 产业链唯一代码 | dwd_industry_chain_info | chain_code |
| chain_name | string | 是 | 产业链名称 | dwd_industry_chain_info | chain_name |
| data_source | string | 否 | 数据来源 | dwd_industry_chain_info | data_source |

### 2.12 ChainNode（产业链节点）

图数据库标签：`ChainNode`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| chain_code | string | 是 | 所属产业链代码 | dwd_industry_chain_info | chain_code |
| chain_name | string | 否 | 所属产业链名称 | dwd_industry_chain_info | chain_name |
| node_id | string | 是 | 节点唯一代码 | dwd_industry_chain_info | node_id |
| node_name | string | 是 | 节点名称 | dwd_industry_chain_info | node_name |
| node_type | int | 否 | 节点类型 | dwd_industry_chain_info | node_type |
| level | int | 否 | 节点层级 | dwd_industry_chain_info | level |
| parent_id | string | 否 | 父级节点代码 | dwd_industry_chain_info | parent_id |
| node_path | string | 否 | 节点路径 | dwd_industry_chain_info | node_path |

### 2.13 Technology（技术/知识单元）

图数据库标签：`Technology`

> 技术是可复用的知识单元（算法/材料/工艺/方法等），从论文关键词、专利IPC分类、报告主题中提取。

| 属性名 | 类型 | 必填 | 中文说明 | 来源 |
|--------|------|------|---------|------|
| name | string | 是 | 技术名称(标准化) | 提取标准化 |
| name_en | string | 否 | 英文名称 | 提取 |
| source_type | string | 是 | 来源类型 | 枚举见下方 |
| description | string | 否 | 技术描述 | 提取 |
| related_domains | string | 否 | 关联领域(JSON) | 提取 |

**source_type 枚举值：** `keyword`（论文关键词）、`ipc`（专利IPC分类）、`report_topic`（报告主题）、`industry_field`（产业领域）

### 2.14 Industry（行业）

图数据库标签：`Industry`

| 属性名 | 类型 | 必填 | 中文说明 | 来源 |
|--------|------|------|---------|------|
| name | string | 是 | 行业名称 | 产业链节点分类 |
| level | string | 否 | 层级 | 一级/二级/三级 |
| parent_industry | string | 否 | 上级行业名称 | 产业链层级 |
| description | string | 否 | 行业描述 | 提取 |

### 2.15 Policy（政策）

图数据库标签：`Policy`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| policy_id | string | 是 | 政策唯一ID | ods_zh_policy | lngid |
| title | string | 是 | 政策标题 | ods_zh_policy | title |
| organ | string | 否 | 发布机关 | ods_zh_policy | organ |
| industry | string | 否 | 关联行业 | ods_zh_policy | industry |
| keywords | string | 否 | 关键词 | ods_zh_policy | keyword |
| publish_time | string | 否 | 发布时间 | ods_zh_policy | publish_time |
| policy_type | string | 否 | 政策类型 | ods_zh_policy | policy_type |

### 2.16 Event（事件）

图数据库标签：`Event`

> 事件是从资讯或新闻中挖掘出来的突发事件。

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| event_id | string | 是 | 事件唯一ID | dwd_industry_chain_news_info | news_id |
| title | string | 是 | 事件标题 | dwd_industry_chain_news_info | title |
| event_date | string | 否 | 事件日期 | dwd_industry_chain_news_info | relaese_date |
| summary | string | 否 | 事件摘要 | dwd_industry_chain_news_info | summary |
| source | string | 否 | 信息来源 | dwd_industry_chain_news_info | source |
| related_chain_code | string | 否 | 关联产业链代码 | dwd_industry_chain_news_info | chain_code |

### 2.17 Region（地区）

图数据库标签：`Region`

| 属性名 | 类型 | 必填 | 中文说明 | 来源 |
|--------|------|------|---------|------|
| name | string | 是 | 地区名称 | 机构地址、人才流动 |
| level | string | 是 | 地区级别 | 枚举见下方 |
| parent_region | string | 否 | 上级地区 | 行政区划 |
| longitude | float | 否 | 经度 | dwd_org_reg_info |
| latitude | float | 否 | 纬度 | dwd_org_reg_info |

**level 枚举值：** `country`（国家）、`province`（省）、`city`（市）、`district`（区县）

### 2.18 Product（产品）

图数据库标签：`Product`

| 属性名 | 类型 | 必填 | 中文说明 | 来源表 | 来源字段 |
|--------|------|------|---------|--------|---------|
| product_name | string | 是 | 产品名称 | dwd_org_org_product_info | main_prod |
| company_name | string | 否 | 所属企业名称 | dwd_org_industry_chain_prod_dtl | company_name |
| industry | string | 否 | 所属行业 | dwd_org_industry_chain_prod_dtl | chain_name |
| description | string | 否 | 产品描述 | 提取 |

---

## 3. 关系类型定义

### 3.1 关系分类

所有关系分为两类：

- **基础关系（basic）**：从 MySQL 原始数据直接映射，无需算法推理
- **推理关系（inferred）**：由九个模块通过规则/算法/大模型推理产出

### 3.2 基础关系属性规范

所有基础关系边携带的标准属性：

| 属性名 | 类型 | 说明 |
|--------|------|------|
| source_table | string | 来源 MySQL 表名 |
| source_field | string | 来源字段名 |

### 3.3 推理关系属性规范

**所有推理关系边必须携带以下属性：**

| 属性名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| score | float | 是 | 置信度，取值 0.0-1.0 |
| evidence | string | 否 | 证据来源，JSON 数组格式，如 `["SCH:A001", "SCH:B002"]` |
| path | string | 否 | 多跳路径描述（仅间接关系使用），如 `"A→B→C"` |
| algorithm_version | string | 是 | 产出该关系的算法版本号，如 `"v1.0.0"` |
| module_code | string | 是 | 产出该关系的模块代码，如 `"expert_colleague_relation"` |
| status | string | 是 | 状态：`active`(有效) / `revoked`(已撤销) / `pending_review`(待审核) |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 最后更新时间 |

### 3.4 人才链关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 | 来源/模块 |
|---|---------|--------|-----------|------|----------|
| R01 | paper_cooperation | 论文合作关系 | Scholar → Scholar | 基础+推理 | dwd_scholar_coauthor + 模块6 |
| R02 | patent_cooperation | 专利合作关系 | Scholar → Scholar | 基础 | ods_patent（发明人共现） |
| R03 | project_collaboration | 项目共同承担 | Scholar → Scholar | 基础 | ods_zh_project（participants） |
| R04 | colleague | 同事关系 | Scholar → Scholar | 推理 | 模块4 |
| R05 | alumni | 校友关系 | Scholar → Scholar | 推理 | 模块5 |
| R06 | indirect_relation | 间接关联关系 | Scholar → Scholar | 推理 | 模块2 |
| R07 | direct_relation | 直接关系 | Scholar → Scholar | 推理 | 模块1 |
| R08 | authors_zh_paper | 作者关系(中文) | Scholar → ZhPaper | 基础 | dwd_scholar_paper_relation |
| R09 | authors_en_paper | 作者关系(外文) | Scholar → EnPaper | 基础 | dwd_scholar_paper_relation |
| R10 | invents | 发明人关系 | Scholar → Patent | 基础 | ods_patent |
| R11 | leads_project | 主持/参与关系 | Scholar → ZhProject / EnProject | 基础 | ods_*_project.project_host |
| R12 | participates | 参与关系 | Scholar → ZhProject / EnProject | 基础 | ods_*_project(participants) |
| R13 | works_at | 任职关系 | Scholar → DomInstitution / ForInstitution | 基础 | dwd_scholar.scholar_org_id |
| R14 | advises | 顾问关系 | Scholar → DomInstitution / ForInstitution | 推理 | 文本抽取 |
| R15 | rd_cooperates | 研发合作关系 | Scholar → DomInstitution / ForInstitution | 推理 | 文本抽取 |
| R16 | researches | 研究领域关系 | Scholar → Technology | 基础 | dwd_scholar_research_direction |
| R17 | talent_mobility | 流动关系 | Scholar → Region | 推理 | 工作经历变迁分析 |

### 3.5 论文/专利关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 | 来源 |
|---|---------|--------|-----------|------|------|
| R18 | proposes_tech | 提出关系 | ZhPaper / EnPaper / Patent → Technology | 推理 | 关键词/IPC提取 |
| R19 | uses_tech | 使用关系 | ZhPaper / EnPaper / Patent → Technology | 推理 | 关键词/IPC提取 |
| R20 | cites | 引用关系 | ZhPaper / EnPaper → ZhPaper / EnPaper | 基础 | dwd_en_paper_cited_by |
| R21 | publishes_patent | 申请关系 | DomInstitution / ForInstitution → Patent | 基础 | ods_patent（assignee） |

### 3.6 机构关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 | 来源 |
|---|---------|--------|-----------|------|------|
| R22 | publishes_paper | 发布关系 | DomInstitution / ForInstitution → ZhPaper / EnPaper | 基础 | 作者单位关联 |
| R23 | undertakes_project | 承担关系 | DomInstitution / ForInstitution → ZhProject / EnProject | 基础 | ods_*_project.funded_institution |
| R24 | institution_cooperation | 合作关系 | DomInstitution / ForInstitution → DomInstitution / ForInstitution | 推理 | 文本/投资抽取 |
| R25 | institution_competition | 竞争关系 | DomInstitution / ForInstitution → DomInstitution / ForInstitution | 推理 | 行业+地域分析 |
| R26 | invests | 投资关系 | Investor(Institution) → Enterprise(Institution) | 基础 | dwd_org_invest_info |
| R27 | masters_tech | 掌握关系 | Enterprise(Institution) → Technology | 推理 | 专利/产品分析 |
| R28 | belongs_to_industry | 从属关系 | Enterprise(Institution) → Industry | 基础 | dwd_org_tag_info |
| R29 | product_applies | 应用关系 | Product → Industry | 推理 | 产品-行业关联 |
| R30 | cooperation_output | 合作成果 | Scholar → ZhPaper / EnPaper / Patent / ZhProject / EnProject | 推理 | 模块3 |

### 3.7 产业链关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 | 来源/模块 |
|---|---------|--------|-----------|------|----------|
| R31 | chain_contains | 包含关系 | IndustryChain → ChainNode | 基础 | dwd_industry_chain_info |
| R32 | node_key_expert | 关键专家关系 | ChainNode → Scholar | 基础+推理 | dwd_org_industry_chain_dtl + 推理 |
| R33 | node_key_enterprise | 重点企业关系 | ChainNode → DomInstitution(sub_type=enterprise) | 基础 | dwd_org_industry_chain_dtl |
| R34 | node_key_event | 关键事件关系 | ChainNode → Event | 推理 | 模块8 |
| R35 | upstream_downstream | 上下游关系 | DomInstitution → DomInstitution | 推理 | 产业链分析 |
| R36 | chain_patent | 专利关联 | ChainNode → Patent | 基础 | dwd_org_industry_chain_pat_dtl |

### 3.8 技术链关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 | 来源 |
|---|---------|--------|-----------|------|------|
| R37 | tech_industrialization | 产业化关系 | Technology → Enterprise(Institution) | 推理 | 技术-企业关联分析 |
| R38 | tech_drives_industry | 驱动关系 | Technology → Industry | 推理 | 技术-行业关联 |
| R39 | enterprise_rd_tech | 研发关系 | Enterprise(Institution) → Technology | 推理 | 专利分析 |
| R40 | enterprise_implements_tech | 实现关系 | Enterprise(Institution) → Technology | 推理 | 专利分析 |
| R41 | enterprise_uses_tech | 使用关系 | Enterprise(Institution) → Technology | 推理 | 专利/产品分析 |
| R42 | enterprise_provides_product | 提供关系 | Enterprise(Institution) → Product | 基础 | dwd_org_org_product_info |
| R43 | tech_cross_relation | 交叉关联关系 | Technology → Technology | 推理 | 共现分析 |
| R44 | tech_subordinate | 从属关系 | Technology → Technology | 推理 | IPC层级分析 |

### 3.9 政策关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 |
|---|---------|--------|-----------|------|
| R45 | policy_supports_industry | 支持关系 | Policy → Industry | 推理 |
| R46 | policy_supports_tech | 支持关系 | Policy → Technology | 推理 |
| R47 | policy_supports_enterprise | 支持关系 | Policy → DomInstitution / ForInstitution | 推理 |
| R48 | policy_talent_incentive | 扶持激励关系 | Policy → Scholar | 推理 |
| R49 | policy_talent_recruit | 引进培育关系 | Policy → Scholar | 推理 |
| R50 | policy_encourages_paper | 鼓励产出关系 | Policy → ZhPaper / EnPaper | 推理 |
| R51 | policy_protects_patent | 保护关系 | Policy → Patent | 推理 |
| R52 | policy_approves_project | 立项支持关系 | Policy → ZhProject | 推理 |
| R53 | policy_funds_project | 资金扶持关系 | Policy → ZhProject | 推理 |
| R54 | policy_guides_foreign_project | 合作引导关系 | Policy → EnProject | 推理 |
| R55 | policy_regulates_dom_institution | 监管规范关系 | Policy → DomInstitution | 推理 |
| R56 | policy_guides_dom_institution | 指导约束关系 | Policy → DomInstitution | 推理 |
| R57 | policy_encourages_for_institution | 合作鼓励关系 | Policy → ForInstitution | 推理 |
| R58 | policy_regulates_for_institution | 准入规范关系 | Policy → ForInstitution | 推理 |
| R59 | policy_guides_chain | 布局引导关系 | Policy → IndustryChain | 推理 |
| R60 | policy_upgrades_chain | 升级支持关系 | Policy → IndustryChain | 推理 |
| R61 | policy_supports_tech_chain | 构建支持关系 | Policy → Technology | 推理 |
| R62 | policy_drives_innovation | 创新驱动关系 | Policy → Technology | 推理 |
| R63 | policy_supplements | 配套关系 | Policy → Policy | 推理 |
| R64 | policy_replaces | 替代修订关系 | Policy → Policy | 推理 |
| R65 | policy_subordinate | 层级从属关系 | Policy → Policy | 推理 |
| R66 | policy_revokes | 废止关系 | Policy → Policy | 推理 |
| R67 | policy_triggers_event | 触发关联关系 | Policy → Event | 推理 |
| R68 | policy_constrains_event | 规范约束关系 | Policy → Event | 推理 |

### 3.10 事件关系

| # | 关系类型 | 中文名 | 起点 → 终点 | 类别 |
|---|---------|--------|-----------|------|
| R69 | event_involves | 参与/主体关系 | Event → Scholar / DomInstitution / ForInstitution | 推理 |
| R70 | event_relates | 关联关系 | Event → ZhPaper / EnPaper / Patent / ZhProject / EnProject | 推理 |

---

## 4. VID 唯一标识规则

### 4.1 格式规范

所有图数据库节点的唯一标识符（VID）格式为：

```
{TYPE_PREFIX}:{SOURCE_ID}
```

- `TYPE_PREFIX`：实体类型的前缀缩写（3字符，大写）
- `SOURCE_ID`：来源系统中的唯一标识符
- VID 中的 `:` 必须转义为 `%3A`（避免与分隔符冲突）

### 4.2 VID 格式速查表

| 实体类型 | TYPE_PREFIX | VID 格式 | 示例 |
|---------|-------------|---------|------|
| Scholar | `SCH` | `SCH:{scholar_id}` | `SCH:A000123456` |
| ZhPaper | `ZPP` | `ZPP:{id}` | `ZPP:100234` |
| EnPaper | `EPP` | `EPP:{id}` | `EPP:200567` |
| Patent | `PAT` | `PAT:{publication_number}` | `PAT:CN123456789A` |
| ZhProject | `ZPJ` | `ZPJ:{project_number}` | `ZPJ:NSFC12345` |
| EnProject | `EPJ` | `EPJ:{project_number}` | `EPJ:EPSRC67890` |
| DomInstitution | `DIN` | `DIN:{org_id}` | `DIN:91110000MA123` |
| ForInstitution | `FIN` | `FIN:{org_id}` | `FIN:GOOGL` |
| IndustryChain | `ICH` | `ICH:{chain_code}` | `ICH:AI` |
| ChainNode | `ICN` | `ICN:{chain_code}:{node_id}` | `ICN:AI:node_001` |
| Technology | `TEC` | `TEC:{normalized_name}` | `TEC:machine_learning` |
| Industry | `IND` | `IND:{name}` | `IND:artificial_intelligence` |
| Policy | `POL` | `POL:{source_prefix}:{id}` | `POL:ZHW:abc123` |
| Event | `EVT` | `EVT:{event_id}` | `EVT:evt_001` |
| Region | `REG` | `REG:{level}:{name}` | `REG:province:北京市` |
| Product | `PRD` | `PRD:{product_name}` | `PRD:麒麟芯片` |

### 4.3 碰撞预防规则

- 同一实体在图数据库中只能有**一个 VID**，不同模块不能为同一实体创建重复节点
- 写入图数据库前必须先查询 VID 是否已存在，已存在则更新属性，不存在则新建
- `Technology` 的 `normalized_name` 需统一处理：小写、去空格、特殊字符替换为下划线
- `Region` 的 `name` 需使用标准行政区划名称（如"北京市"而非"北京"）
- `Policy` 的 `source_prefix` 枚举：`ZHW`（维普国内）、`ENP`（国外政策）、`ZHT`（国内政策6）、`ZHP`（拓尔思政策）

---

## 5. MySQL 到图数据库映射规则

### 5.1 实体映射

| MySQL 数据域 | 表数量 | 映射目标实体类型 | 说明 |
|-------------|--------|-----------------|------|
| scholar（6表） | 6 | Scholar | 主键 `scholar_id`，6 表通过 `scholar_id` 关联 |
| chinese_paper（4表） | 4 | ZhPaper | 主键 `id`，作者表通过 `paper_id` 关联 |
| foreign_paper（6表） | 6 | EnPaper | 主键 `id`，引用表通过 `paper_id` 关联 |
| paper_common（2表） | 2 | ZhPaper / EnPaper | 作者机构关联表，辅助链接 |
| patent（9表） | 9 | Patent | 主键 `publication_number`，专利族通过 `family_id` 关联 |
| domestic_project（2表） | 2 | ZhProject | 主键 `project_number` |
| foreign_project（2表） | 2 | EnProject | 主键 `project_number` |
| domestic_organization（41表） | 41 | DomInstitution | 主键 `org_id`，41 表通过 `org_id` 关联 |
| foreign_organization（10表） | 10 | ForInstitution | 主键 `ename_en` |
| industry_chain（5表） | 5 | IndustryChain + ChainNode | 产业链表同时映射两种实体 |
| policy（4表） | 4 | Policy | 4 张来源表各有 source_prefix |
| report（2表） | 2 | 辅助（不直接建实体） | 报告数据辅助提取 Technology |

### 5.2 关系映射（基础关系）

| 基础关系 | MySQL 来源表 | 链接方式 |
|---------|------------|---------|
| authors_zh_paper | dwd_scholar_paper_relation | Scholar VID ← `scholar_id`，ZhPaper VID ← `paper_id` |
| authors_en_paper | dwd_scholar_paper_relation | 同上，按论文来源区分 |
| invents | ods_patent | Scholar VID ← 发明人姓名匹配，Patent VID ← `publication_number` |
| works_at | dwd_scholar | Scholar VID ← `scholar_id`，DomInstitution VID ← `scholar_org_id` |
| leads_project | ods_zh_project / ods_en_project | Scholar VID ← `project_host` 姓名，Project VID ← `project_number` |
| participates | ods_zh_project / ods_en_project | Scholar VID ← `participants` 解析，Project VID ← `project_number` |
| paper_cooperation | dwd_scholar_coauthor | Scholar VID ← `scholar_id`，Scholar VID ← `coauthor_scholar_id` |
| cites | dwd_en_paper_cited_by | EnPaper VID ← `paper_id`，EnPaper VID ← `cited_paper_id` |
| publishes_patent | ods_patent | DomInstitution VID ← `assignee` 匹配，Patent VID ← `publication_number` |
| undertakes_project | ods_zh_project / ods_en_project | DomInstitution VID ← `funded_institution` 匹配，Project VID ← `project_number` |
| invests | dwd_org_invest_info | Investor VID ← 投资方，Enterprise VID ← 被投方（均用 `org_id`） |
| chain_contains | dwd_industry_chain_info | IndustryChain VID ← `chain_code`，ChainNode VID ← `chain_code:node_id` |
| node_key_enterprise | dwd_org_industry_chain_dtl | ChainNode VID ← `chain_code:node_id`，DomInstitution VID ← `antitypic` |
| chain_patent | dwd_org_industry_chain_pat_dtl | ChainNode VID ← `chain_code:node_id`，Patent VID ← `apno` |
| enterprise_provides_product | dwd_org_org_product_info | DomInstitution VID ← `org_id`，Product VID ← `main_prod` |
| researches | dwd_scholar_research_direction | Scholar VID ← `scholar_id`，Technology VID ← `fields` 提取 |

### 5.3 特殊映射说明

**机构子类型判断规则：**

| 条件 | sub_type | 说明 |
|------|----------|------|
| 存在 `dwd_org_hels_info` 记录且 `univ_type` 非空 | `university` | 高校 |
| 存在 `dwd_org_hels_info` 记录且 `univ_type` 为空 | `research_institute` | 科研院所 |
| 不在 `dwd_org_hels_info` 中，在 `dwd_org_reg_info` 中 | `enterprise` | 企业 |
| 机构名称包含政府关键词 | `government` | 政府机关 |

**发明人关系匹配：**
- `ods_patent` 表中发明人字段为文本，需与 `dwd_scholar.name_zh`/`name_en` 做模糊匹配
- 匹配成功后建立 `Scholar → Patent` 的 `invents` 关系

---

## 6. 模块结果回写规范

### 6.1 回写流程

```
模块推理产出关系
    ↓
先写入 MySQL 结果表（持久化、可审计）
    ↓
按结果表记录更新/新增图数据库边
```

### 6.2 结果表命名规则

表名模式：`kg_result_{module_code}`

| 模块代码 | 结果表名 |
|---------|---------|
| expert_direct_relation | `kg_result_expert_direct_relation` |
| expert_indirect_relation | `kg_result_expert_indirect_relation` |
| expert_cooperation_achievement | `kg_result_expert_cooperation_achievement` |
| expert_colleague_relation | `kg_result_expert_colleague_relation` |
| expert_alumni_relation | `kg_result_expert_alumni_relation` |
| expert_paper_cooperation | `kg_result_expert_paper_cooperation` |
| expert_enterprise_relation | `kg_result_expert_enterprise_relation` |
| industry_chain_topn_event | `kg_result_industry_chain_topn_event` |
| industry_chain_panorama | `kg_result_industry_chain_panorama` |

### 6.3 结果表统一 DDL

所有九个模块的结果表使用**完全相同的字段结构**：

```sql
CREATE TABLE IF NOT EXISTS kg_result_{module_code} (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    head_vid            VARCHAR(128)  NOT NULL COMMENT '起点实体 VID',
    tail_vid            VARCHAR(128)  NOT NULL COMMENT '终点实体 VID',
    relation_type       VARCHAR(64)   NOT NULL COMMENT '图谱边类型（见第3章）',
    score               FLOAT         NOT NULL DEFAULT 0.0 COMMENT '置信度 0.0-1.0',
    evidence            JSON          COMMENT '证据来源 ID 列表',
    path                VARCHAR(512)  COMMENT '多跳路径（仅间接关系）',
    algorithm_version   VARCHAR(32)   NOT NULL COMMENT '算法版本号',
    status              VARCHAR(16)   NOT NULL DEFAULT 'active' COMMENT 'active/revoked/pending_review',
    batch_id            VARCHAR(64)   COMMENT '批次运行标识',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_edge (head_vid, tail_vid, relation_type),
    INDEX idx_tail (tail_vid),
    INDEX idx_status (status),
    INDEX idx_batch (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模块 {module_code} 推理结果';
```

### 6.4 产业事件辅助表

模块8（industry_chain_topn_event）除了通用结果表外，还需要一个事件详情表：

```sql
CREATE TABLE IF NOT EXISTS kg_result_industry_event (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_vid           VARCHAR(128)  NOT NULL COMMENT '事件实体 VID',
    chain_code          VARCHAR(128)           COMMENT '所属产业链代码',
    node_id             VARCHAR(128)           COMMENT '关联产业链节点 ID',
    event_title         VARCHAR(512)           COMMENT '事件标题',
    event_date          DATE                   COMMENT '事件日期',
    event_summary       TEXT                   COMMENT '事件摘要',
    event_source        VARCHAR(256)           COMMENT '事件来源',
    related_vids        JSON          COMMENT '关联实体 VID 列表',
    score               FLOAT         COMMENT '影响力评分',
    module_code         VARCHAR(64)   NOT NULL COMMENT '产出模块',
    algorithm_version   VARCHAR(32)   NOT NULL COMMENT '算法版本号',
    status              VARCHAR(16)   NOT NULL DEFAULT 'active',
    batch_id            VARCHAR(64)   COMMENT '批次运行标识',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_event (event_vid, module_code),
    INDEX idx_chain (chain_code),
    INDEX idx_node (node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产业链 TOP-N 事件详情';
```

### 6.5 回写规范

1. **同一对实体不能重复写入**：`UNIQUE KEY (head_vid, tail_vid, relation_type)` 保证
2. **推理关系必须携带标准属性**：`score`、`algorithm_version`、`module_code`、`status` 为必填
3. **使用 batch_id 标识每次运行**：便于回溯和撤销
4. **撤销旧结果**：新的 batch 写入后，旧 batch 的 `status` 更新为 `revoked`
5. **先写 MySQL 再写图数据库**：确保数据持久化，图数据库可作为缓存加速层

---

## 7. 新增实体/关系维护流程

### 7.1 新增流程

```
1. 确认需求：是否已有同义实体/关系类型？
   ↓ 查阅本规范第2章/第3章
2. 评估影响：新实体/关系会影响哪些模块？
   ↓ 查阅九个模块关系清单
3. 定义规范：
   - 新增实体：定义类型名、VID 前缀、属性列表、来源表
   - 新增关系：定义关系名、起止点实体、属性、来源/模块
4. 更新本文档
5. 通知相关模块负责人
```

### 7.2 禁止事项

- 禁止各模块私自新增实体类型或关系类型
- 禁止使用未经规范定义的属性名（如 `org_name` 和 `institution_name` 不能同时存在）
- 禁止为同一实体创建不同格式的 VID
- 禁止在推理关系中缺失 `score`、`algorithm_version`、`module_code`、`status` 字段

### 7.3 现有代码同步

后续各模块开始实现时，需按本规范：

1. 更新 `backend/service/common/entity_extraction.py` 中的 `ENTITY_TYPES`，与本规范第2章实体类型对齐
2. 更新 `backend/service/common/relation_extraction.py` 中的关系类型列表，与本规范第3章对齐
3. 在 `backend/schemas/graph_schema.py` 中实现校验函数，供各模块调用
