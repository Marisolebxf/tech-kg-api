# 国外项目数据表规范

本规范依据第三方最新《要素库设计方案》整理。
附件包含 2 张表、74 条字段定义，折叠 JSON 子字段并排除明确删除项后，生成 43 个物理字段。

## 重要说明

附件没有提供英文表名、英文字段名和 JSON 子字段英文名。
`dwd_en_project` 可由附件关联字段确认；`dwd_en_project_output` 及字段英文名称沿用国内项目对应规则，属于项目建议命名。

## 建模约定

1. 中文字段、类型、长度、可空性、索引和主键采用附件提供值。
2. “是否为主键”为“是”的字段建立主键；“是否索引”为“是”的非主键字段建立普通索引。
3. “是否为索引主键”作为数据索引侧元数据保留，不直接转换为 SQL 唯一约束。
4. 产出详情按 JSON 列保存；连续的无类型行作为对应 JSON 主字段的内部属性，不单独创建 SQL 列。
5. 备注明确写有“深化方案中删除”的字段不进入 DDL，但继续保留在原始定义中。
6. 附件未明确外键约束，因此本阶段不添加外键。
7. 本阶段不生成示范数据。

## 表结构汇总

| 中文表名 | 建议英文表名 | 来源 | 附件定义数 | 物理字段数 |
|---|---|---|---:|---:|
| 国外项目信息表 | `dwd_en_project` | 附件关联字段可确认 | 22 | 22 |
| 国外项目-产出信息 | `dwd_en_project_output` | 项目建议命名 | 52 | 21 |

## 排除字段

| 建议英文字段 | 中文字段 | 原因 |
|---|---|---|
| `products_count` | 产品数量 | 附件备注：因完整性过低，深化方案中删除 |
| `output_products` | 产出的产品信息 | JSON 主字段备注：因完整性过低，深化方案中删除 |

## 1. 国外项目信息表 `dwd_en_project`

### 物理字段

| 中文字段 | 建议英文字段 | SQL 类型 | 可空 | 索引 | 主键 | 索引主键 | 描述 | 样例 | 关联字段 |
|---|---|---|---|---|---|---|---|---|---|
| 项目索引 | `id` | `VARCHAR(64)` | 否 | 是 | 是 | 否 | 项目记录的唯一主键标识。 | 6f608705-675f-46ce-801f-ce6dfe0a61d2 | - |
| 项目编号 | `project_number` | `VARCHAR(32)` | 是 | 是 | 否 | 是 | 项目在管理系统中的编号。 | 2420605 | - |
| 项目名称 | `title` | `VARCHAR(512)` | 是 | 否 | 否 | 否 | 项目的名称或标题。 | Oceanographic Technical Support CY 2024 Year 1 of 5 | - |
| 项目来源 | `project_source` | `VARCHAR(64)` | 是 | 否 | 否 | 否 | 项目所属的资助来源或立项来源。 | 美国国家科学基金(NSF) | - |
| 项目受资助机构 | `funded_institution` | `VARCHAR(128)` | 是 | 否 | 否 | 否 | 获得项目资助的机构名称。 | UNIVERSITY OF DELAWARE | - |
| 项目级别 | `project_level` | `ENUM('国家级', '州级', '市级', '县级', '其他')` | 是 | 否 | 否 | 否 | 项目所属的级别或层次。 | 国家级 | - |
| 受资助金额 | `funded_amount` | `DECIMAL(18,2)` | 是 | 否 | 否 | 否 | 项目获得的资助经费金额，单位为美元。 | 110673 | - |
| 学科 | `discipline` | `VARCHAR(256)` | 是 | 否 | 否 | 否 | 项目所属的学科领域。 | 工程与材料科学-机械设计与制造-机械动力学 | - |
| 学科代码 | `discipline_code` | `VARCHAR(256)` | 是 | 是 | 否 | 否 | 项目所属学科的分类代码。 | E-E05-E0503 | - |
| 基金类别 | `fund_category` | `VARCHAR(64)` | 是 | 否 | 否 | 否 | 项目对应的基金或资助类别。 | Cooperative Agreement | - |
| 项目受资助地区 | `funded_region` | `VARCHAR(32)` | 是 | 否 | 否 | 否 | 项目受资助机构所在的地区信息。 | 未公开 | - |
| 参与机构 | `participating_institution` | `JSON` | 是 | 否 | 否 | 否 | 参与项目研究或实施的机构信息。 | ["UNIVERSITY OF DELAWARE"] | - |
| 立项年度 | `approval_year` | `INT` | 是 | 是 | 否 | 否 | 项目获批立项的年份。 | 2025 | - |
| 立项时间 | `approval_time` | `DATE` | 是 | 否 | 否 | 否 | 项目正式获批立项的时间。 | 2025/3/15 | - |
| 研究期限 | `research_period` | `VARCHAR(64)` | 是 | 否 | 否 | 否 | 项目计划开展研究的时间期限。 | 2025-3-15 ~ 2030-02-28 (预估) | - |
| 项目主持人 | `project_host` | `VARCHAR(64)` | 是 | 否 | 否 | 否 | 项目的主要负责人或主持人。 | Timothy W Deering | - |
| 参与者 | `participants` | `JSON` | 是 | 否 | 否 | 否 | 参与项目研究或实施的人员信息。 | ["Li, Xiaomin", "Chen, Yu", "Davis, Michael"] | - |
| 关键词 | `keywords` | `JSON` | 是 | 否 | 否 | 否 | 描述项目研究主题的关键词。 | ["OCEANOGRAPHIC TECHNICAL SERVCE", "EXP PROG TO STIM COMP RES"] | - |
| 项目标书摘要 | `abstract` | `LONGTEXT` | 是 | 否 | 否 | 否 | 项目申请书或标书中的摘要内容。 | The University of Delaware(UD)proposes to support oceanographic technical services on R/V Hugh R.Sharp operated as part of the U.S.Academic Research Fleet(ARF),which is scheduled by the University-National Oceanographic Laboratory System(UNOLS).As part of their basic operations,UD will provide shipboard technicians on each seagoing research project to support basic services.Technicians will maintain,calibrate and provide for qualified users,items from their pool of shared-use research instrumentation.Research vessels in the ARF provide support for researchers from a variety of federal and state agencies,as well as some private sponsors.All users(or the appropriate funding agencies)share support costs for basic technical services on the vessel equally,via a day-rate,with each paying a share of the costs based on fractional usage of the vessel.The principal impact of the present proposal is under Merit Review Criterion 2 of the Proposal Guidelines(NSF 23-525).It provides infrastructure support for scientists to use the vessel and its shared-use instrumentation in support of their NSF-funded oceanographic research projects(which individually undergo separate review by the relevant research program of NSF).The acquisition,maintenance and operation of shared-use instrumentation allows NSF-funded researchers from any US university or lab access to working,calibrated instruments for their research,reducing the cost of that research,and expanding the base of potential researchers.This award reflects NSF's statutory mission and has been deemed worthy of support through evaluation using the Foundation's intellectual merit and broader impacts review criteria. | - |
| 项目结题摘要 | `final_report_abstract` | `LONGTEXT` | 是 | 否 | 否 | 否 | 项目结题报告中的摘要内容。 | The University of Delaware(UD)proposes to support oceanographic technical services on R/V Hugh R.Sharp operated as part of the U.S.Academic Research Fleet(ARF),which is scheduled by the University-National Oceanographic Laboratory System(UNOLS).As part of their basic operations,UD will provide shipboard technicians on each seagoing research project to support basic services.Technicians will maintain,calibrate and provide for qualified users,items from their pool of shared-use research instrumentation.Research vessels in the ARF provide support for researchers from a variety of federal and state agencies,as well as some private sponsors.All users(or the appropriate funding agencies)share support costs for basic technical services on the vessel equally,via a day-rate,with each paying a share of the costs based on fractional usage of the vessel.The principal impact of the present proposal is under Merit Review Criterion 2 of the Proposal Guidelines(NSF 23-525).It provides infrastructure support for scientists to use the vessel and its shared-use instrumentation in support of their NSF-funded oceanographic research projects(which individually undergo separate review by the relevant research program of NSF).The acquisition,maintenance and operation of shared-use instrumentation allows NSF-funded researchers from any US university or lab access to working,calibrated instruments for their research,reducing the cost of that research,and expanding the base of potential researchers.This award reflects NSF's statutory mission and has been deemed worthy of support through evaluation using the Foundation's intellectual merit and broader impacts review criteria. | - |
| 项目页面 URL | `project_page_url` | `TEXT` | 是 | 否 | 否 | 否 | 项目详情页面的访问链接。 | https://www.nsf.gov/awardsearch/show-award/?AWD_ID=2420605 | - |
| 更新时间 | `updated_time` | `DATETIME` | 否 | 否 | 否 | 否 | 该条数据最近一次更新的时间。 | 15/4/2026 14:59:34 | - |

## 2. 国外项目-产出信息 `dwd_en_project_output`

### 物理字段

| 中文字段 | 建议英文字段 | SQL 类型 | 可空 | 索引 | 主键 | 索引主键 | 描述 | 样例 | 关联字段 |
|---|---|---|---|---|---|---|---|---|---|
| 项目索引 | `id` | `VARCHAR(64)` | 否 | 是 | 是 | 否 | 项目记录的唯一主键标识。 | 6f608705-675f-46ce-801f-ce6dfe0a61d2 | dwd_en_project.id |
| 项目总产出数量 | `total_outputs` | `INT` | 是 | 否 | 否 | 否 | 项目产生的成果总数量。 | 3 | - |
| 期刊文章数量 | `journal_articles_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的期刊论文数量。 | 3 | - |
| 会议论文数量 | `conference_papers_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的会议论文数量。 | 0 | - |
| 学位论文数量 | `degree_papers_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的学位论文数量。 | 2 | - |
| 专利数量 | `patents_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的专利数量。 | 0 | - |
| 临床试验数量 | `clinical_trials_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的临床试验数量。 | 0 | - |
| 图书专著数量 | `books_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的图书或专著数量。 | 0 | - |
| 奖项数量 | `awards_count` | `INT` | 是 | 否 | 否 | 否 | 项目获得的奖项数量。 | 0 | - |
| 报告数量 | `reports_count` | `INT` | 是 | 否 | 否 | 否 | 项目产出的报告数量。 | 0 | - |
| 其他产出数量 | `other_outputs_count` | `INT` | 是 | 否 | 否 | 否 | 项目产生的其他成果数量。 | 0 | - |
| 产出的期刊文章标题 | `output_journal_articles` | `JSON` | 是 | 否 | 否 | 否 | 项目产出的期刊文章内容 | - | - |
| 产出的专利标题 | `output_patents` | `JSON` | 是 | 否 | 否 | 否 | 项目产出专利标题 | - | - |
| 产出的会议论文标题 | `output_conference_papers` | `JSON` | 是 | 否 | 否 | 否 | 项目产出会议论文标题 | - | - |
| 产出的学位论文标题 | `output_degree_papers` | `JSON` | 是 | 否 | 否 | 否 | 项目产出学位论文标题 | - | - |
| 产出的临床试验信息 | `output_clinical_trials` | `JSON` | 是 | 否 | 否 | 否 | 项目产出临床试验标题 | - | - |
| 产出的图书专著信息 | `output_books` | `JSON` | 是 | 否 | 否 | 否 | 项目产出图书专著标题 | - | - |
| 产出的奖项信息 | `output_awards` | `JSON` | 是 | 否 | 否 | 否 | 项目产出奖项标题 | - | - |
| 产出的报告信息 | `output_reports` | `JSON` | 是 | 否 | 否 | 否 | 项目产出报告标题 | - | - |
| 其他产出信息 | `output_other` | `JSON` | 是 | 否 | 否 | 否 | 项目其他产出标题 | - | - |
| 更新时间 | `updated_time` | `DATETIME` | 否 | 否 | 否 | 否 | 该条数据最近一次更新的时间。 | 15/4/2026 14:59:34 | - |

### JSON 子字段

| JSON 列 | 建议 JSON 属性 | 中文含义 | 描述 | 状态 |
|---|---|---|---|---|
| `output_journal_articles` | `title` | 产出的期刊文章标题 | 项目产出的期刊文章内容 | 保留 |
| `output_journal_articles` | `authors` | 产出的期刊文章作者 | 项目产出期刊的文章作者 | 保留 |
| `output_journal_articles` | `journal` | 产出的期刊文章期刊 | 项目产出期刊 | 保留 |
| `output_journal_articles` | `year` | 产出的期刊文章年份 | 项目产出期刊的年份 | 保留 |
| `output_journal_articles` | `issue` | 产出的期刊文章期数 | 项目产出期刊的期数 | 保留 |
| `output_journal_articles` | `keywords` | 产出的期刊文章关键词 | 项目产出期刊的关键词 | 保留 |
| `output_journal_articles` | `abstract` | 产出的期刊文章摘要 | 项目产出期刊的摘要 | 保留 |
| `output_journal_articles` | `source_url` | 产出的期刊文章来源URL | 项目产出期刊的源地址 | 保留 |
| `output_patents` | `patent_title` | 产出的专利标题 | 项目产出专利标题 | 保留 |
| `output_patents` | `patent_inventor` | 产出的专利发明人 | 项目产出专利发明人 | 保留 |
| `output_patents` | `patent_number` | 产出的专利号 | 项目产出专利号 | 保留 |
| `output_patents` | `abstract` | 产出的专利摘要 | 项目产出专利摘要 | 保留 |
| `output_patents` | `keywords` | 产出的专利关键词 | 项目产出专利关键词 | 保留 |
| `output_conference_papers` | `title` | 产出的会议论文标题 | 项目产出会议论文标题 | 保留 |
| `output_conference_papers` | `authors` | 产出的会议论文作者 | 项目产出会议论文作者 | 保留 |
| `output_conference_papers` | `year` | 产出的会议论文年丰 | 项目产出会议论文年份 | 保留 |
| `output_conference_papers` | `name` | 产出的会议论文名称 | 项目产出会议论文名 | 保留 |
| `output_degree_papers` | `title` | 产出的学位论文标题 | 项目产出学位论文标题 | 保留 |
| `output_degree_papers` | `authors` | 产出的学位论文作者 | 项目产出学位论文作者 | 保留 |
| `output_degree_papers` | `keywords` | 产出的学位论文关键词 | 项目产出学位论文关键词 | 保留 |
| `output_clinical_trials` | `title` | 产出的临床试验信息 | 项目产出临床试验标题 | 保留 |
| `output_clinical_trials` | `authors` | 产出的临床试验信息 | 项目产出临床试验作者 | 保留 |
| `output_clinical_trials` | `keywords` | 产出的临床试验信息 | 项目产出临床试验关键词 | 保留 |
| `output_books` | `title` | 产出的图书专著信息 | 项目产出图书专著标题 | 保留 |
| `output_books` | `authors` | 产出的图书专著信息 | 项目产出图书专著作者 | 保留 |
| `output_books` | `keywords` | 产出的图书专著信息 | 项目产出图书专著关键词 | 保留 |
| `output_products` | `title` | 产出的产品信息 | 项目产出产品标题 | 不建表：深化方案中删除 |
| `output_products` | `authors` | 产出的产品信息 | 项目产出产品作者 | 不建表：深化方案中删除 |
| `output_products` | `keywords` | 产出的产品信息 | 项目产出产品关键词 | 不建表：深化方案中删除 |
| `output_awards` | `title` | 产出的奖项信息 | 项目产出奖项标题 | 保留 |
| `output_awards` | `authors` | 产出的奖项信息 | 项目产出奖项作者 | 保留 |
| `output_awards` | `keywords` | 产出的奖项信息 | 项目产出奖项关键词 | 保留 |
| `output_reports` | `title` | 产出的报告信息 | 项目产出报告标题 | 保留 |
| `output_reports` | `authors` | 产出的报告信息 | 项目产出报告作者 | 保留 |
| `output_reports` | `keywords` | 产出的报告信息 | 项目产出报告关键词 | 保留 |
| `output_reports` | `abstract` | 产出的报告信息 | 项目产出报告摘要 | 保留 |
| `output_other` | `title` | 其他产出信息 | 项目其他产出标题 | 保留 |
| `output_other` | `authors` | 其他产出信息 | 项目其他产出作者 | 保留 |
| `output_other` | `keywords` | 其他产出信息 | 项目其他产出关键词 | 保留 |

## 原始字段定义

| 序号 | 表名 | 中文字段 | 建议英文字段 | 建议 JSON 属性 | 原始类型 | 长度 | 可空 | 索引 | 主键 | 索引主键 | 完整率 | 备注 |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 国外项目信息表 | 项目索引 | `id` | - | varchar | 64 | 否 | 是 | 是 | 否 | 100 | - |
| 2 | 国外项目信息表 | 项目编号 | `project_number` | - | varchar | 32 | 是 | 是 | 否 | 是 | 100 | - |
| 3 | 国外项目信息表 | 项目名称 | `title` | - | varchar | 512 | 是 | 否 | 否 | 否 | 100 | - |
| 4 | 国外项目信息表 | 项目来源 | `project_source` | - | varchar | 64 | 是 | 否 | 否 | 否 | 100 | - |
| 5 | 国外项目信息表 | 项目受资助机构 | `funded_institution` | - | varchar | 128 | 是 | 否 | 否 | 否 | 100 | - |
| 6 | 国外项目信息表 | 项目级别 | `project_level` | - | enum | - | 是 | 否 | 否 | 否 | 100 | - |
| 7 | 国外项目信息表 | 受资助金额 | `funded_amount` | - | decimal | 18,2 | 是 | 否 | 否 | 否 | 100 | - |
| 8 | 国外项目信息表 | 学科 | `discipline` | - | varchar | 256 | 是 | 否 | 否 | 否 | 99.57 | - |
| 9 | 国外项目信息表 | 学科代码 | `discipline_code` | - | varchar | 256 | 是 | 是 | 否 | 否 | 99.57 | - |
| 10 | 国外项目信息表 | 基金类别 | `fund_category` | - | varchar | 64 | 是 | 否 | 否 | 否 | 100 | - |
| 11 | 国外项目信息表 | 项目受资助地区 | `funded_region` | - | varchar | 32 | 是 | 否 | 否 | 否 | 100 | - |
| 12 | 国外项目信息表 | 参与机构 | `participating_institution` | - | json | - | 是 | 否 | 否 | 否 | 78.61 | - |
| 13 | 国外项目信息表 | 立项年度 | `approval_year` | - | int | - | 是 | 是 | 否 | 否 | 100 | - |
| 14 | 国外项目信息表 | 立项时间 | `approval_time` | - | date | - | 是 | 否 | 否 | 否 | 100 | - |
| 15 | 国外项目信息表 | 研究期限 | `research_period` | - | varchar | 64 | 是 | 否 | 否 | 否 | 100 | - |
| 16 | 国外项目信息表 | 项目主持人 | `project_host` | - | varchar | 64 | 是 | 否 | 否 | 否 | 86.17 | - |
| 17 | 国外项目信息表 | 参与者 | `participants` | - | json | - | 是 | 否 | 否 | 否 | 88.31 | - |
| 18 | 国外项目信息表 | 关键词 | `keywords` | - | json | - | 是 | 否 | 否 | 否 | 99.56 | - |
| 19 | 国外项目信息表 | 项目标书摘要 | `abstract` | - | longtext | - | 是 | 否 | 否 | 否 | 96.47 | - |
| 20 | 国外项目信息表 | 项目结题摘要 | `final_report_abstract` | - | longtext | - | 是 | 否 | 否 | 否 | 76.3 | - |
| 21 | 国外项目信息表 | 项目页面 URL | `project_page_url` | - | text | - | 是 | 否 | 否 | 否 | 100 | - |
| 22 | 国外项目信息表 | 更新时间 | `updated_time` | - | datetime | - | 否 | 否 | 否 | 否 | 100 | - |
| 23 | 国外项目-产出信息 | 项目索引 | `id` | - | varchar | 64 | 否 | 是 | 是 | 否 | 100 | - |
| 24 | 国外项目-产出信息 | 项目总产出数量 | `total_outputs` | - | int | - | 是 | 否 | 否 | 否 | 78.21 | - |
| 25 | 国外项目-产出信息 | 期刊文章数量 | `journal_articles_count` | - | int | - | 是 | 否 | 否 | 否 | 83.26 | - |
| 26 | 国外项目-产出信息 | 会议论文数量 | `conference_papers_count` | - | int | - | 是 | 否 | 否 | 否 | 18.41 | - |
| 27 | 国外项目-产出信息 | 学位论文数量 | `degree_papers_count` | - | int | - | 是 | 否 | 否 | 否 | 8.47 | - |
| 28 | 国外项目-产出信息 | 专利数量 | `patents_count` | - | int | - | 是 | 否 | 否 | 否 | 11.87 | - |
| 29 | 国外项目-产出信息 | 临床试验数量 | `clinical_trials_count` | - | int | - | 是 | 否 | 否 | 否 | 5.24 | - |
| 30 | 国外项目-产出信息 | 图书专著数量 | `books_count` | - | int | - | 是 | 否 | 否 | 否 | 3.62 | - |
| 31 | 国外项目-产出信息 | 产品数量 | `products_count` | - | int | - | 是 | 否 | 否 | 否 | 0 | 因完整性过低，深化方案中删除 |
| 32 | 国外项目-产出信息 | 奖项数量 | `awards_count` | - | int | - | 是 | 否 | 否 | 否 | 3.47 | - |
| 33 | 国外项目-产出信息 | 报告数量 | `reports_count` | - | int | - | 是 | 否 | 否 | 否 | 39.84 | - |
| 34 | 国外项目-产出信息 | 其他产出数量 | `other_outputs_count` | - | int | - | 是 | 否 | 否 | 否 | 9.25 | - |
| 35 | 国外项目-产出信息 | 产出的期刊文章标题 | `output_journal_articles` | `title` | json | - | 是 | 否 | 否 | 否 | 83.26 | - |
| 36 | 国外项目-产出信息 | 产出的期刊文章作者 | `output_journal_articles` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 37 | 国外项目-产出信息 | 产出的期刊文章期刊 | `output_journal_articles` | `journal` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 38 | 国外项目-产出信息 | 产出的期刊文章年份 | `output_journal_articles` | `year` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 39 | 国外项目-产出信息 | 产出的期刊文章期数 | `output_journal_articles` | `issue` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 40 | 国外项目-产出信息 | 产出的期刊文章关键词 | `output_journal_articles` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 41 | 国外项目-产出信息 | 产出的期刊文章摘要 | `output_journal_articles` | `abstract` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 42 | 国外项目-产出信息 | 产出的期刊文章来源URL | `output_journal_articles` | `source_url` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 43 | 国外项目-产出信息 | 产出的专利标题 | `output_patents` | `patent_title` | json | - | 是 | 否 | 否 | 否 | 11.87 | - |
| 44 | 国外项目-产出信息 | 产出的专利发明人 | `output_patents` | `patent_inventor` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 45 | 国外项目-产出信息 | 产出的专利号 | `output_patents` | `patent_number` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 46 | 国外项目-产出信息 | 产出的专利摘要 | `output_patents` | `abstract` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 47 | 国外项目-产出信息 | 产出的专利关键词 | `output_patents` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 48 | 国外项目-产出信息 | 产出的会议论文标题 | `output_conference_papers` | `title` | json | - | 是 | 否 | 否 | 否 | 18.41 | - |
| 49 | 国外项目-产出信息 | 产出的会议论文作者 | `output_conference_papers` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 50 | 国外项目-产出信息 | 产出的会议论文年丰 | `output_conference_papers` | `year` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 51 | 国外项目-产出信息 | 产出的会议论文名称 | `output_conference_papers` | `name` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 52 | 国外项目-产出信息 | 产出的学位论文标题 | `output_degree_papers` | `title` | json | - | 是 | 否 | 否 | 否 | 8.47 | - |
| 53 | 国外项目-产出信息 | 产出的学位论文作者 | `output_degree_papers` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 54 | 国外项目-产出信息 | 产出的学位论文关键词 | `output_degree_papers` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 55 | 国外项目-产出信息 | 产出的临床试验信息 | `output_clinical_trials` | `title` | json | - | 是 | 否 | 否 | 否 | 5.24 | - |
| 56 | 国外项目-产出信息 | 产出的临床试验信息 | `output_clinical_trials` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 57 | 国外项目-产出信息 | 产出的临床试验信息 | `output_clinical_trials` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 58 | 国外项目-产出信息 | 产出的图书专著信息 | `output_books` | `title` | json | - | 是 | 否 | 否 | 否 | 3.62 | - |
| 59 | 国外项目-产出信息 | 产出的图书专著信息 | `output_books` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 60 | 国外项目-产出信息 | 产出的图书专著信息 | `output_books` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 61 | 国外项目-产出信息 | 产出的产品信息 | `output_products` | `title` | json | - | 是 | 否 | 否 | 否 | 0 | 因完整性过低，深化方案中删除 |
| 62 | 国外项目-产出信息 | 产出的产品信息 | `output_products` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 63 | 国外项目-产出信息 | 产出的产品信息 | `output_products` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 64 | 国外项目-产出信息 | 产出的奖项信息 | `output_awards` | `title` | json | - | 是 | 否 | 否 | 否 | 3.47 | - |
| 65 | 国外项目-产出信息 | 产出的奖项信息 | `output_awards` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 66 | 国外项目-产出信息 | 产出的奖项信息 | `output_awards` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 67 | 国外项目-产出信息 | 产出的报告信息 | `output_reports` | `title` | json | - | 是 | 否 | 否 | 否 | 39.84 | - |
| 68 | 国外项目-产出信息 | 产出的报告信息 | `output_reports` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 69 | 国外项目-产出信息 | 产出的报告信息 | `output_reports` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 70 | 国外项目-产出信息 | 产出的报告信息 | `output_reports` | `abstract` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 71 | 国外项目-产出信息 | 其他产出信息 | `output_other` | `title` | json | - | 是 | 否 | 否 | 否 | 9.25 | - |
| 72 | 国外项目-产出信息 | 其他产出信息 | `output_other` | `authors` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 73 | 国外项目-产出信息 | 其他产出信息 | `output_other` | `keywords` | 继承 JSON 主字段 | - | 是 | 否 | 否 | 否 | - | - |
| 74 | 国外项目-产出信息 | 更新时间 | `updated_time` | - | datetime | - | 否 | 否 | 否 | 否 | 100 | - |
