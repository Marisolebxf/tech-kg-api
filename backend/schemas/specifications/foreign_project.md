# 国外项目字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `ods_en_project` | 深势-国外项目信息表 | 1463 | 22 |
| `ods_en_project_output` | 深势-国外项目产出信息表 | 1297 | 24 |

## `ods_en_project`

表注释：深势-国外项目信息表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(64)` | NO | PRI |  |  | 主键 |
| 2 | `project_number` | `varchar(64)` | NO |  |  |  | 项目编号 |
| 3 | `title` | `varchar(1000)` | NO |  |  |  | 项目名称 |
| 4 | `project_source` | `varchar(128)` | YES |  |  |  | 项目来源 |
| 5 | `funded_institution` | `varchar(255)` | YES |  |  |  | 依托单位 |
| 6 | `project_level` | `varchar(64)` | YES |  |  |  | 项目级别 |
| 7 | `funded_amount` | `decimal(12,2)` | YES |  |  |  | 资助金额 |
| 8 | `discipline` | `varchar(500)` | YES |  |  |  | 学科 |
| 9 | `discipline_code` | `varchar(128)` | YES |  |  |  | 学科代码 |
| 10 | `fund_category` | `varchar(128)` | YES |  |  |  | 基金类别 |
| 11 | `funded_province` | `varchar(64)` | YES |  |  |  | 资助省份 |
| 12 | `participating_institution` | `varchar(255)` | YES |  |  |  | 参与单位 |
| 13 | `approval_year` | `date` | YES |  |  |  | 批准年度 |
| 14 | `approval_time` | `date` | YES |  |  |  | 批准日期 |
| 15 | `research_period` | `varchar(128)` | YES |  |  |  | 研究周期 |
| 16 | `project_host` | `varchar(100)` | YES |  |  |  | 项目负责人 |
| 17 | `participants` | `mediumtext` | YES |  |  |  | 参与人员 |
| 18 | `keywords` | `mediumtext` | YES |  |  |  | 关键词 |
| 19 | `abstract` | `mediumtext` | YES |  |  |  | 项目摘要 |
| 20 | `project_page_url` | `varchar(1024)` | YES |  |  |  | 项目详情页 |
| 21 | `create_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |  |
| 22 | `update_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |  |

## `ods_en_project_output`

表注释：深势-国外项目产出信息表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(64)` | NO | PRI |  |  | UUID主键 |
| 2 | `total_outputs` | `int` | YES |  |  |  | 项目总产出数量 |
| 3 | `journal_articles_count` | `int` | YES |  |  |  | 期刊文章数量 |
| 4 | `conference_papers_count` | `int` | YES |  |  |  | 会议论文数量 |
| 5 | `books_count` | `int` | YES |  |  |  | 图书专著数量 |
| 6 | `degree_papers_count` | `int` | YES |  |  |  | 学位论文数量 |
| 7 | `patents_count` | `int` | YES |  |  |  | 专利数量 |
| 8 | `clinical_trials_count` | `int` | YES |  |  |  | 临床试验数量 |
| 9 | `products_count` | `int` | YES |  |  |  | 产品数量 |
| 10 | `awards_count` | `int` | YES |  |  |  | 奖项数量 |
| 11 | `reports_count` | `int` | YES |  |  |  | 报告数量 |
| 12 | `other_outputs_count` | `int` | YES |  |  |  | 其他产出数量 |
| 13 | `output_journal_articles` | `mediumtext` | YES |  |  |  | 期刊文章 |
| 14 | `output_conference_papers` | `mediumtext` | YES |  |  |  | 会议论文 |
| 15 | `output_books` | `mediumtext` | YES |  |  |  | 图书专著 |
| 16 | `output_degree_papers` | `mediumtext` | YES |  |  |  | 学位论文 |
| 17 | `output_patents` | `mediumtext` | YES |  |  |  | 专利 |
| 18 | `output_clinical_trials` | `mediumtext` | YES |  |  |  | 临床试验 |
| 19 | `output_products` | `mediumtext` | YES |  |  |  | 产品 |
| 20 | `output_awards` | `mediumtext` | YES |  |  |  | 奖项 |
| 21 | `output_reports` | `mediumtext` | YES |  |  |  | 报告 |
| 22 | `output_other` | `mediumtext` | YES |  |  |  | 其他成果 |
| 23 | `create_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |  |
| 24 | `update_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED |  |
