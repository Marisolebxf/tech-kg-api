# 九大业务模块 MySQL 表结构

> 整理日期：2026-09-22。DDL 与行数取自 dev 共享 MySQL（`host.docker.internal:30306`，库 `gkx_element`）实测 `SHOW CREATE TABLE` / `COUNT(*)`。

## 结论速览

- 九大业务模块运行时的**主数据源是图库**（trs-graph / Nebula，space=`dev2`），其中 **7 个模块完全不碰 MySQL**。
- 只有 **模块 7「重点关注科技企业关系」子系统**（构建/标注/背景分析/挖掘）与 **公共下拉接口 `/kg-construction/options`** 读 MySQL，且全部走 `infra/gkx.py` 的 **gkx 只读会话**（禁止写入）。
- 代码里 gkx 会话的目标库名是 `gkx_local`（`PAPER_COOP_MYSQL_*` / `LOCAL_MYSQL_*` 环境变量）；**dev 共享 MySQL 上没有 `gkx_local` 库，上述表实际都在 `gkx_element` 库**。因此 dev2 部署上所有 gkx 读都会报 `Unknown database 'gkx_local'` 而降级（options 学者/企业下拉为空、企业关系兜底建点失效、背景分析 MySQL 维度缺失），属环境配置问题而非表缺失。

## 模块 ↔ 表映射

| # | 模块（前端路由） | 后端服务 | MySQL 表（运行时） | 用途 |
|---|---|---|---|---|
| 1 | 科技专家/人才直接关系（/expert-direct） | `service/expert_direct_relation.py` | 无（纯图库） | — |
| 2 | 科技单节点间接关系（/node-indirect） | `service/expert_indirect_relation_api.py` | 无（纯图库） | — |
| 3 | 科技两点合作成果（/two-point-achievement） | `service/expert_cooperation_achievement.py` | 无（纯图库） | — |
| 4 | 科技专家同事关系（/expert-colleague） | `service/expert_colleague_relation.py` | 无（纯图库） | — |
| 5 | 科技专家校友关系（/expert-alumni） | `service/expert_alumni_relation.py` | 无（纯图库） | — |
| 6 | 科技专家论文合作关系（/paper-cooperation） | `service/expert_paper_cooperation_api.py` | 无（纯图库；`PAPER_COOP_MYSQL_*` 只是 gkx 会话工厂的连接参数名） | — |
| 7 | 重点关注科技企业关系（/enterprise-relation） | `service/expert_enterprise_relation.py` + `relation_detail_annotation` + `enterprise_background_analysis` + `expert_enterprise_mining` | 见下表 | 见下表 |
| 8 | 科技产业链点TOP-N事件（/industry-chain-event） | `service/industry_chain_topn_event.py` 等 | 无（纯图库） | — |
| 9 | 科技产业链全景图（/industry-chain-panorama） | `service/industry_chain_panorama.py` | 无（纯图库） | — |
| 公共 | 测试参数下拉 `GET /kg-construction/options` | `service/kg_options.py` | `dwd_scholar`、`dwd_org_stock_base`、`dwd_org_base_info` | 学者/企业下拉候选（任一失败返回空数组不阻塞） |

### 模块 7 明细（重点关注科技企业关系子系统）

| 表 | 使用方（DAO 方法） | 业务用途 |
|---|---|---|
| `dwd_scholar` | `GkxScholarDAO.get_by_id`；`kg_options._scholars` | 构建时图库无该学者 → 从 gkx 取真实画像兜底建 `Scholar` 图节点；options 学者下拉 |
| `dwd_scholar_research_direction` | `GkxScholarDAO.get_research_directions` | 挖掘：研究方向 → 技术领域匹配（CPC 候选） |
| `dwd_org_base_info` | `OrganizationDAO/GkxOrganizationDAO.get_by_id`、`get_by_name`、`list`；`kg_options._enterprises` | 企业注册信息主表：兜底建 `Organization` 节点、背景分析基础信息、options 企业下拉 |
| `dwd_org_stock_base` | 同上（注册表未命中时回退） | 上市公司信息（stock_code/listed_status 等） |
| `dwd_org_org_product_info` | `OrganizationDAO.get_products` | 背景分析-核心技术维度：经营范围/业务描述/主营产品 |
| `dwd_org_tag_info` | `OrganizationDAO.get_tags` | 背景分析-行业地位维度：企业标签（org_tag/tag_level）。**dev 库无此表，运行时该维度降级为空** |
| `dwd_org_stock_finance_info` | `OrganizationDAO.get_stock_finance`（按 occur_period 倒序） | 背景分析-经营财务维度：上市公司财务指标 |
| `dwd_org_annual_financial_info` | `OrganizationDAO.get_annual_finance`（按 year 倒序） | 背景分析-经营财务维度：年报财务 |
| `dwd_org_industry_chain_dtl` | `OrganizationDAO.get_industry_chain`（按 `antitypic`=org_id 查） | 背景分析：企业所属产业链环节 |
| `dwd_org_industry_chain_prod_dtl` | `OrganizationDAO.get_chain_products` | 背景分析：企业产业链主营产品 |
| `dwd_patent` | `PatentDAO.list_by_assignee` / `count_by_cpc_section`（按 `first_current_assignee_name`） | 背景分析-核心技术维度：企业专利与 CPC 分类统计 |
| （动态扫描）全部含 `org_id`+`name_cn` 列的 `dwd_org_*` 表并集 | `GkxOrganizationDAO.list_name_id`（进程级缓存） | 挖掘：企业候选池（dev 库实测 19 张表，见文末） |

> ETL-only 表（`dwd_scholar_coauthor`、`dwd_industry_chain_info`、`dwd_industry_chain_news_info`、`ods_patent*` 等）由 `script/`、`organization_ETL/` 入图脚本使用，九大模块运行时不读，本文不展开。

## 表结构（实测 DDL）

### dwd_scholar（学者，2,175 行）

```sql
CREATE TABLE `dwd_scholar` (
  `scholar_id` varchar(32) NOT NULL COMMENT '学者ID',
  `name_en` varchar(128) NOT NULL COMMENT '英文姓名',
  `name_zh` varchar(128) NOT NULL COMMENT '中文姓名',
  `avatar` varchar(256) NOT NULL COMMENT '头像',
  `scholar_org_name_en` varchar(4096) DEFAULT NULL COMMENT '英文机构',
  `scholar_org_name_zh` varchar(1024) DEFAULT NULL COMMENT '中文机构',
  `bio` longtext COMMENT '个人简介/学术简介',
  `bio_zh` longtext COMMENT '个人简介/学术简介（中文）',
  `work_experience_date` varchar(100) DEFAULT NULL COMMENT '工作经历起止时间',
  `work_experience_institution_en` varchar(255) DEFAULT NULL COMMENT '工作经历单位英文',
  `work_experience_department_en` varchar(255) DEFAULT NULL COMMENT '工作经历院系英文',
  `work_experience_position_en` varchar(255) DEFAULT NULL COMMENT '工作经历职务英文',
  `work_experience_institution_zh` varchar(255) DEFAULT NULL COMMENT '工作经历单位中文',
  `work_experience_department_zh` varchar(256) DEFAULT NULL COMMENT '工作经历院系中文',
  `work_experience_position_zh` varchar(255) DEFAULT NULL COMMENT '工作经历职务中文',
  `education_background_date` varchar(100) DEFAULT NULL COMMENT '教育背景起止时间',
  `education_background_institution_en` varchar(500) DEFAULT NULL COMMENT '教育机构英文',
  `education_background_degree_en` varchar(255) DEFAULT NULL COMMENT '教育学位英文',
  `education_background_institution_zh` varchar(500) DEFAULT NULL COMMENT '教育机构中文',
  `education_background_degree_zh` varchar(255) DEFAULT NULL COMMENT '教育学位中文',
  `paper_nums` int NOT NULL COMMENT '论文数量',
  `citation_nums` int NOT NULL COMMENT '被引数量',
  `h_index` int NOT NULL COMMENT 'H指数',
  `status` int NOT NULL COMMENT '状态',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  `update_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_name_en` (`name_en`),
  KEY `idx_name_zh` (`name_zh`),
  KEY `idx_scholar_org_name_en` (`scholar_org_name_en`(191)),
  KEY `idx_scholar_org_name_zh` (`scholar_org_name_zh`(191)),
  KEY `idx_paper_nums` (`paper_nums`),
  KEY `idx_citation_nums` (`citation_nums`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者';
```

### dwd_scholar_research_direction（学者研究方向，2,155 行）

```sql
CREATE TABLE `dwd_scholar_research_direction` (
  `scholar_id` varchar(32) NOT NULL COMMENT '学者ID',
  `fields` text COMMENT '研究方向（逗号分隔，代码里按 "," 切分）',
  `create_time` datetime NOT NULL COMMENT '创建时间',
  `update_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者研究方向';
```

### dwd_org_base_info（机构基本信息，1,674 行）

```sql
CREATE TABLE `dwd_org_base_info` (
  `org_id` varchar(255) NOT NULL COMMENT '机构id',
  `name_cn` varchar(255) NOT NULL COMMENT '机构名称',
  `external_id` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `province` varchar(255) DEFAULT NULL COMMENT '所在省份',
  `city` varchar(255) DEFAULT NULL COMMENT '所在城市',
  `area` varchar(255) DEFAULT NULL COMMENT '所在区县',
  `address` text COMMENT '公司地址',
  `addr_lng` varchar(255) DEFAULT NULL COMMENT '地址对应经度',
  `addr_lat` varchar(255) DEFAULT NULL COMMENT '地址对应维度',
  `postal_code` varchar(255) DEFAULT NULL COMMENT '邮政编码',
  `email` text COMMENT '电子邮箱',
  `lerep` varchar(255) DEFAULT NULL COMMENT '法定代表人',
  `reg_status` varchar(255) DEFAULT NULL COMMENT '登记状态',
  `registration_org` varchar(255) DEFAULT NULL COMMENT '登记机关',
  `incorporation_year` decimal(20,0) DEFAULT NULL COMMENT '成立年份',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期',
  `start_date` varchar(255) DEFAULT NULL COMMENT '经营期限自',
  `end_date` varchar(255) DEFAULT NULL COMMENT '经营期限至',
  `org_type` varchar(255) DEFAULT NULL COMMENT '机构类型',
  `listing_status` varchar(255) DEFAULT NULL COMMENT '上市状态',
  `listing_date` datetime DEFAULT NULL COMMENT '上市日期',
  `registered_capital_value` decimal(20,2) DEFAULT NULL COMMENT '注册资本(本币元)',
  `capital_currency` varchar(255) DEFAULT NULL COMMENT '币种',
  `industry` varchar(255) DEFAULT NULL COMMENT '最深一级的行业名称',
  `industry_l1_name` varchar(255) DEFAULT NULL COMMENT '一级行业名称',
  `industry_l1_code` varchar(255) DEFAULT NULL COMMENT '一级行业编码',
  `industry_l2_name` varchar(255) DEFAULT NULL COMMENT '二级行业名称',
  `industry_l2_code` varchar(255) DEFAULT NULL COMMENT '二级行业编码',
  `industry_l3_name` varchar(255) DEFAULT NULL COMMENT '三级行业名称',
  `industry_l3_code` varchar(255) DEFAULT NULL COMMENT '三级行业编码',
  `industry_l4_name` varchar(255) DEFAULT NULL COMMENT '四级行业名称',
  `industry_l4_code` varchar(255) DEFAULT NULL COMMENT '四级行业编码',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='机构基本信息';
```

### dwd_org_stock_base（上市企业基本信息，5,945 行）

```sql
CREATE TABLE `dwd_org_stock_base` (
  `stock_code` varchar(255) NOT NULL COMMENT '股票代码',
  `stock_noun` varchar(255) DEFAULT NULL COMMENT '股票简称',
  `stock_type` varchar(255) NOT NULL COMMENT '上市板块',
  `org_id` varchar(255) NOT NULL COMMENT '机构id',
  `name_cn` varchar(255) NOT NULL COMMENT '机构名称',
  `external_id` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `listed_date` datetime DEFAULT NULL COMMENT '上市日期',
  `listed_status` varchar(255) NOT NULL COMMENT '上市状态',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业基本信息';
```

### dwd_org_org_product_info（经营信息，1,184 行）

```sql
CREATE TABLE `dwd_org_org_product_info` (
  `org_id` varchar(255) NOT NULL COMMENT '机构id',
  `name_cn` varchar(255) NOT NULL COMMENT '机构名称',
  `external_id` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `main_activities` text COMMENT '公司经营范围',
  `description` text COMMENT '业务描述',
  `main_prod` varchar(1120) DEFAULT NULL COMMENT '主营产品',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营信息';
```

### dwd_org_tag_info（企业标签 —— dev 库缺表）

ORM 模型 `db_model/domestic_organization.py::DwdOrgTagInfo` 定义了 `org_id` / `org_tag` / `tag_level` 等列，`OrganizationDAO.get_tags` 供背景分析「行业地位」维度使用。**dev 共享库（gkx_element）中该表不存在**，运行时 `get_tags` 抛错被各维度独立容错捕获，行业地位维度降级为空。生产 gkx 库若存在此表则自动生效。

### dwd_org_stock_finance_info（上市企业主要财务指标，5,553 行）

```sql
CREATE TABLE `dwd_org_stock_finance_info` (
  `org_id` varchar(255) NOT NULL COMMENT '机构id',
  `name_cn` varchar(255) NOT NULL COMMENT '机构名称',
  `stock_code` varchar(255) NOT NULL COMMENT '股票代码',
  `external_id` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `occur_period` varchar(255) NOT NULL COMMENT '数据期',
  `total_assets` decimal(20,2) DEFAULT NULL COMMENT '资产总额(元)',
  `fixed_assets` decimal(20,2) DEFAULT NULL COMMENT '固定资产总额(元)',
  `total_liabilities` decimal(20,2) DEFAULT NULL COMMENT '负债总额(元)',
  `operating_revenue` decimal(20,2) DEFAULT NULL COMMENT '营业收入(元)',
  `main_business_revenue` decimal(20,2) DEFAULT NULL COMMENT '主营业务收入(元)',
  `total_profit` decimal(20,2) DEFAULT NULL COMMENT '利润总额(元)',
  `pure_profit` decimal(20,2) DEFAULT NULL COMMENT '净利润(元)',
  `total_tax_paid` decimal(20,2) DEFAULT NULL COMMENT '纳税总额(元)',
  `oper_cash_flow` decimal(20,2) DEFAULT NULL COMMENT '经营活动现金流(元)',
  `owners_equity` decimal(20,2) DEFAULT NULL COMMENT '所有者权益合计(元)',
  `employees_number` decimal(20,0) DEFAULT NULL COMMENT '从业人数',
  `research_development_amount` decimal(20,2) DEFAULT NULL COMMENT '研发投入金额(元)',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_occur_period` (`occur_period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业主要财务指标';
```

### dwd_org_annual_financial_info（年报财务信息，5,452 行）

```sql
CREATE TABLE `dwd_org_annual_financial_info` (
  `org_id` varchar(255) NOT NULL COMMENT '机构id',
  `name_cn` varchar(255) NOT NULL COMMENT '机构名称',
  `external_id` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `year` decimal(20,0) NOT NULL COMMENT '年报年度',
  `total_assets` decimal(20,2) DEFAULT NULL COMMENT '资产总额',
  `total_liabilities` decimal(20,2) DEFAULT NULL COMMENT '负债总额',
  `operating_revenue` decimal(20,2) DEFAULT NULL COMMENT '营业收入',
  `main_business_revenue` decimal(20,2) DEFAULT NULL COMMENT '主营业务收入',
  `total_profit` decimal(20,2) DEFAULT NULL COMMENT '利润总额',
  `pure_profit` decimal(20,2) DEFAULT NULL COMMENT '净利润',
  `total_tax_paid` decimal(20,2) DEFAULT NULL COMMENT '纳税总额',
  `owners_equity` decimal(20,2) DEFAULT NULL COMMENT '所有者权益合计',
  `employees_number` decimal(20,0) DEFAULT NULL COMMENT '从业人数',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='年报财务信息';
```

### dwd_org_industry_chain_dtl（产业关联企业信息，2,951 行）

```sql
CREATE TABLE `dwd_org_industry_chain_dtl` (
  `chain_code` varchar(255) NOT NULL COMMENT '产业链代码',
  `chain_name` varchar(255) NOT NULL COMMENT '产业链名称',
  `node_id` varchar(255) NOT NULL COMMENT '节点代码',
  `node_name` varchar(255) NOT NULL COMMENT '节点名称',
  `antitypic` varchar(255) NOT NULL COMMENT '企业id（DAO 按 antitypic=org_id 查询）',
  `credit_code` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `chain_score` decimal(20,2) DEFAULT NULL COMMENT '产业链评分',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业关联企业信息';
```

### dwd_org_industry_chain_prod_dtl（产业链企业关联产品信息，6,059 行）

```sql
CREATE TABLE `dwd_org_industry_chain_prod_dtl` (
  `chain_code` varchar(255) NOT NULL COMMENT '产业链代码',
  `chain_name` varchar(255) NOT NULL COMMENT '产业链名称',
  `antitypic` varchar(255) NOT NULL COMMENT '企业id（DAO 按 antitypic=org_id 查询）',
  `company_name` varchar(500) DEFAULT NULL COMMENT '企业名称',
  `credit_code` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `tech_product` varchar(255) NOT NULL COMMENT '主营产品名称',
  `tech_product_seq` decimal(20,0) DEFAULT NULL COMMENT '主营产品排序',
  `data_source` varchar(255) NOT NULL COMMENT '数据来源',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链企业关联产品信息';
```

### dwd_patent（专利信息表，2,010 行）

```sql
CREATE TABLE `dwd_patent` (
  `id` varchar(36) NOT NULL,
  `patent_id` varchar(64) NOT NULL,
  `publication_number` varchar(64) NOT NULL COMMENT '公开号',
  `application_kind` varchar(1) DEFAULT NULL COMMENT '申请类型',
  `country_code` varchar(8) NOT NULL COMMENT '国家代码',
  `country` varchar(20) NOT NULL COMMENT '国家',
  `publication_reference` json DEFAULT NULL COMMENT '公开引用信息',
  `application_reference` json DEFAULT NULL COMMENT '申请引用信息',
  `pct_or_regional_filing_data` json DEFAULT NULL,
  `pct_or_regional_publishing_data` json DEFAULT NULL,
  `priority_filings` json DEFAULT NULL COMMENT '优先权',
  `applicants` json DEFAULT NULL COMMENT '申请人',
  `assignees` json DEFAULT NULL COMMENT '受让人',
  `inventors` json DEFAULT NULL COMMENT '发明人',
  `first_applicant_name` varchar(255) DEFAULT NULL COMMENT '第一申请人',
  `first_current_assignee_name` varchar(255) DEFAULT NULL COMMENT '第一当前受让人（DAO 按此列查企业专利）',
  `first_inventor_name` varchar(255) DEFAULT NULL COMMENT '第一发明人',
  `main_classification_ipcr` varchar(32) DEFAULT NULL COMMENT 'IPCR 主分类',
  `further_classification_ipcr` json DEFAULT NULL COMMENT 'IPCR 次分类',
  `main_classification_cpc` varchar(32) DEFAULT NULL COMMENT 'CPC 主分类',
  `further_classification_cpc` json DEFAULT NULL COMMENT 'CPC 次分类',
  `keywords` json DEFAULT NULL COMMENT '关键词',
  `claims` json DEFAULT NULL COMMENT '权利要求',
  `description` json DEFAULT NULL COMMENT '说明书',
  `figures` json DEFAULT NULL COMMENT '附图',
  `language` json DEFAULT NULL,
  `granted_number` varchar(64) DEFAULT NULL COMMENT '授权号',
  `db_source` varchar(64) DEFAULT NULL COMMENT '数据来源',
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `value` int DEFAULT NULL,
  `agents` json DEFAULT NULL COMMENT '代理人',
  `agency` json DEFAULT NULL COMMENT '代理机构',
  `examiners` json DEFAULT NULL COMMENT '审查员',
  `related_documents` json DEFAULT NULL,
  `classification_loc` json DEFAULT NULL,
  `classification_fi` json DEFAULT NULL,
  `classification_upc` json DEFAULT NULL,
  `classification_fterm` json DEFAULT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利信息表';
```

## 动态企业候选池（GkxOrganizationDAO.list_name_id）

运行时 `SHOW TABLES LIKE 'dwd_org_%'` 后逐表 `SHOW COLUMNS`，凡含 `org_id` + `name_cn` 列的表都并入企业候选池（按 org_id 去重，进程级缓存）。dev 共享库实测命中 **19 张表**：

`dwd_org_annual_financial_info`、`dwd_org_bankruptcy_public_cases_list`、`dwd_org_base_info`、`dwd_org_changerecord_info`、`dwd_org_company_abnormal`、`dwd_org_company_illegal`、`dwd_org_company_punish`、`dwd_org_executive_info`、`dwd_org_financing_info`、`dwd_org_heis_info`、`dwd_org_important_news_info`、`dwd_org_invest_info`、`dwd_org_org_product_info`、`dwd_org_recruit_info`、`dwd_org_risk_shixin`、`dwd_org_risk_zhixing`、`dwd_org_shareholder_info`、`dwd_org_stock_base`、`dwd_org_stock_finance_info`

（代码注释按生产全量库口径写的是 31 张表并集约 2.7 万家企业；dev 子集为上述 19 张。）
