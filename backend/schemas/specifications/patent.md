# 专利字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `ods_patent` | 深势-专利信息表 | 1044 | 192 |
| `ods_patent_Biblio_` | 全球专利-著录项目 | 0 | 16 |
| `ods_patent_Cited` | 全球专利-专利被引用 | 1000 | 3 |
| `ods_patent_Claims` | 全球专利-权利要求 | 958 | 4 |
| `ods_patent_Description` | 全球专利-说明书 | 982 | 3 |
| `ods_patent_Drawing` | 全球专利-摘要附图 | 957 | 3 |
| `ods_patent_Family` | 全球专利-专利家族 | 978 | 3 |
| `ods_patent_LegalStatus` | 全球专利-法律状态 | 1000 | 4 |
| `ods_patent_weipu` | 维普专利信息 | 100 | 45 |

## `ods_patent`

表注释：深势-专利信息表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(20)` | NO | PRI |  |  | 专利公布号(与DOCDB兼容) |
| 2 | `publication_number` | `varchar(20)` | YES |  |  |  | 专利公布号 |
| 3 | `pct_publication_number` | `varchar(20)` | YES |  |  |  | pct公开号 |
| 4 | `application_number` | `varchar(20)` | YES |  |  |  | 专利申请号 |
| 5 | `country_code` | `varchar(2)` | YES |  |  |  | 国家代码 |
| 6 | `kind_code` | `varchar(2)` | YES |  |  |  | 种类代码 |
| 7 | `application_kind` | `char(1)` | YES |  |  |  | 应用程序类型 |
| 8 | `application_number_formatted` | `varchar(20)` | YES |  |  |  | 格式化的申请号 |
| 9 | `pct_number` | `varchar(17)` | YES |  |  |  | PCT编号 |
| 10 | `family_id` | `varchar(8)` | YES |  |  |  | 家庭ID |
| 11 | `spif_publication_number` | `varchar(20)` | YES |  |  |  | SPIF标准发布编号 |
| 12 | `spif_application_number` | `varchar(20)` | YES |  |  |  | SPIF标准申请号 |
| 13 | `title_localized` | `mediumtext` | YES |  |  |  | 标题 |
| 14 | `abstract_localized` | `mediumtext` | YES |  |  |  | 摘要 |
| 15 | `claims_localized` | `mediumtext` | YES |  |  |  | 权利要求 |
| 16 | `claims_localized_html` | `mediumtext` | YES |  |  |  | 权利要求html |
| 17 | `description_localized` | `mediumtext` | YES |  |  |  | 说明书 |
| 18 | `description_localized_html` | `mediumtext` | YES |  |  |  | 说明书html |
| 19 | `publication_year` | `int` | YES |  |  |  | 发布年份 |
| 20 | `filing_year` | `int` | YES |  |  |  | 申请年份 |
| 21 | `grant_year` | `int` | YES |  |  |  | 授予年份 |
| 22 | `priority_year` | `int` | YES |  |  |  | 优先权年 |
| 23 | `expiration_year` | `int` | YES |  |  |  | 失效年 |
| 24 | `citation_nums` | `int` | YES |  |  |  | 专利引用数量 |
| 25 | `cited_by_nums` | `int` | YES |  |  |  | 专利施引数量 |
| 26 | `publication_date` | `date` | YES |  |  |  | 发布日期 |
| 27 | `filing_date` | `date` | YES |  |  |  | 申请日期 |
| 28 | `grant_date` | `date` | YES |  |  |  | 授予日期 |
| 29 | `priority_date` | `date` | YES |  |  |  | 优先权日 |
| 30 | `priority_claim` | `mediumtext` | YES |  |  |  | 本出版物 |
| 31 | `inventor` | `mediumtext` | YES |  |  |  | 发明人 |
| 32 | `inventor_harmonized` | `mediumtext` | YES |  |  |  | 发明者信息 |
| 33 | `assignee` | `mediumtext` | YES |  |  |  | 受让人/申请人 |
| 34 | `current_assignee` | `mediumtext` | YES |  |  |  | 当前受让人/申请人 |
| 35 | `assignee_harmonized` | `mediumtext` | YES |  |  |  | 受让人/申请人信息 |
| 36 | `examiner` | `mediumtext` | YES |  |  |  | 审查员信息 |
| 37 | `uspc` | `mediumtext` | YES |  |  |  | 美国专利 |
| 38 | `ipc` | `mediumtext` | YES |  |  |  | 国际专利分类 |
| 39 | `cpc` | `mediumtext` | YES |  |  |  | 合作专利分类 |
| 40 | `fi` | `mediumtext` | YES |  |  |  | FI分类 |
| 41 | `fterm` | `mediumtext` | YES |  |  |  | fterm分类 |
| 42 | `locarno` | `mediumtext` | YES |  |  |  | Locarno分类 |
| 43 | `citation` | `mediumtext` | YES |  |  |  | 出版物引用 |
| 44 | `parent` | `mediumtext` | YES |  |  |  | 父申请 |
| 45 | `child` | `mediumtext` | YES |  |  |  | 子申请 |
| 46 | `entity_status` | `varchar(7)` | YES |  |  |  | 美国专利商标局实体状态 |
| 47 | `art_unit` | `varchar(4)` | YES |  |  |  | 美国专利商标局艺术单位 |
| 48 | `status` | `varchar(55)` | YES |  |  |  | 专利状态 |
| 49 | `figures` | `mediumtext` | YES |  |  |  | 专利图 |
| 50 | `pdf_url` | `mediumtext` | YES |  |  |  | 专利文件链接 |
| 51 | `patent_citations` | `mediumtext` | YES |  |  |  | 专利引用 |
| 52 | `family_citations` | `mediumtext` | YES |  |  |  | 家族内引用 |
| 53 | `cited_by` | `mediumtext` | YES |  |  |  | 被引用 |
| 54 | `cited_by_family` | `mediumtext` | YES |  |  |  | 家庭内被引用 |
| 55 | `events` | `mediumtext` | YES |  |  |  | 事件 |
| 56 | `non_patent_citations` | `mediumtext` | YES |  |  |  | 非专利引用 |
| 57 | `legal_events` | `mediumtext` | YES |  |  |  | 法律事件 |
| 58 | `anticipated_expiration` | `date` | YES |  |  |  | 预计到期日 |
| 59 | `language` | `varchar(10)` | YES |  |  |  | 原文语言 |
| 60 | `relevants` | `mediumtext` | YES |  |  |  | 相关专利 |
| 61 | `priority_filings` | `mediumtext` | YES |  |  |  | 优先权信息 |
| 62 | `precis_graph` | `mediumtext` | YES |  |  |  | 摘要图AI生成OSS链接 |
| 63 | `targets` | `mediumtext` | YES |  |  |  | 靶点 |
| 64 | `keywords` | `mediumtext` | YES |  |  |  | 关键词 |
| 65 | `concepts` | `mediumtext` | YES |  |  |  | 概念 |
| 66 | `definitions` | `mediumtext` | YES |  |  |  | 定义 |
| 67 | `worldwides` | `mediumtext` | YES |  |  |  | 全球专利 |
| 68 | `docdb_family` | `mediumtext` | YES |  |  |  | 家族专利 |
| 69 | `prior_art_date` | `date` | YES |  |  |  | Prior art date |
| 70 | `prior_art_year` | `int` | YES |  |  |  | Prior art year |
| 71 | `country` | `varchar(50)` | YES |  |  |  | 国家 |
| 72 | `other_versions` | `mediumtext` | YES |  |  |  | 其他版本 |
| 73 | `external_links` | `mediumtext` | YES |  |  |  | 外部链接 |
| 74 | `landscapes` | `mediumtext` | YES |  |  |  | 技术领域分类 |
| 75 | `dwpi_basic` | `varchar(20)` | YES |  |  |  | DWPI基本专利，指第一个输入到DWPI数据库的同族专利成员 |
| 76 | `dwpi_family` | `mediumtext` | YES |  |  |  | DWPI同族公开号 |
| 77 | `main_family` | `mediumtext` | YES |  |  |  | 同族专利公开号 |
| 78 | `complete_family` | `mediumtext` | YES |  |  |  | 拓展同族公开号 |
| 79 | `legal_status` | `mediumtext` | YES |  |  |  | 法律状态 |
| 80 | `transferor` | `mediumtext` | YES |  |  |  | 转让人 |
| 81 | `transfer_count` | `int` | YES |  |  |  | 转让次数 |
| 82 | `transfer_price` | `mediumtext` | YES |  |  |  | 转让价格 |
| 83 | `transfer_record` | `mediumtext` | YES |  |  |  | 转让时间序列 |
| 84 | `license_type` | `int` | YES |  |  |  | 许可类型，如独占许可、排他许可、普通许可等许可方式 |
| 85 | `license_country` | `mediumtext` | YES |  |  |  | 许可地国家，专利许可在哪些国家或地区有效 |
| 86 | `license_price` | `mediumtext` | YES |  |  |  | 许可费用 |
| 87 | `examination_detail` | `mediumtext` | YES |  |  |  | 审察详细信息 |
| 88 | `technical_abstract` | `mediumtext` | YES |  |  |  | 技术摘要 |
| 89 | `page_count` | `int` | YES |  |  |  | 文献页数 |
| 90 | `subject_classification` | `mediumtext` | YES |  |  |  | 学科分类 |
| 91 | `dwpi_classification` | `mediumtext` | YES |  |  |  | DWPI分类 |
| 92 | `dwpi_title` | `mediumtext` | YES |  |  |  | DWPI标题 |
| 93 | `dwpi_priority_number` | `varchar(20)` | YES |  |  |  | DWPI优先权号 |
| 94 | `dwpi_priority_country` | `varchar(2)` | YES |  |  |  | DWPI优先权国别 |
| 95 | `dwpi_assignee` | `mediumtext` | YES |  |  |  | DWPI专利权人 |
| 96 | `dwpi_inventor` | `mediumtext` | YES |  |  |  | DWPI发明人 |
| 97 | `inpadoc_family_id` | `varchar(8)` | YES |  |  |  | INPADOC同族编号 |
| 98 | `independent_claims_localized` | `mediumtext` | YES |  |  |  | 独立权利要求 |
| 99 | `independent_claims_localized_html` | `mediumtext` | YES |  |  |  | 独立权利要求html |
| 100 | `problem_sum` | `mediumtext` | YES |  |  |  | 技术问题 |
| 101 | `method_sum` | `mediumtext` | YES |  |  |  | 技术手段 |
| 102 | `benefit_sum` | `mediumtext` | YES |  |  |  | 技术功效 |
| 103 | `current_assignee_harmonized` | `mediumtext` | YES |  |  |  | 当前受让人/申请人信息 |
| 104 | `current_inventor` | `mediumtext` | YES |  |  |  | 当前发明人 |
| 105 | `current_inventor_harmonized` | `mediumtext` | YES |  |  |  | 当前发明者信息 |
| 106 | `agent` | `mediumtext` | YES |  |  |  | 代理人 |
| 107 | `current_agent` | `mediumtext` | YES |  |  |  | 当前代理人 |
| 108 | `agency` | `mediumtext` | YES |  |  |  | 代理机构 |
| 109 | `current_agency` | `mediumtext` | YES |  |  |  | 当前代理机构 |
| 110 | `assistant_examiner` | `mediumtext` | YES |  |  |  | 助理审查员信息 |
| 111 | `priority_country` | `varchar(2)` | YES |  |  |  | 优先权国家/地区 |
| 112 | `epds` | `varchar(2)` | YES |  |  |  | EP指定国家/地区 |
| 113 | `business_information` | `mediumtext` | YES |  |  |  | 工商信息 |
| 114 | `first_publication_date` | `date` | YES |  |  |  | 首次公开日 |
| 115 | `examine_date` | `date` | YES |  |  |  | 实质审查生效日 |
| 116 | `pct_entry_date` | `date` | YES |  |  |  | PCT进入国家阶段日 |
| 117 | `legal_status_date` | `date` | YES |  |  |  | 法律状态更新日 |
| 118 | `earliest_priority_date` | `date` | YES |  |  |  | 最早优先权日 |
| 119 | `gbc` | `mediumtext` | YES |  |  |  | 国民经济行业分类号 |
| 120 | `adc` | `mediumtext` | YES |  |  |  | 应用领域分类 |
| 121 | `ttc` | `mediumtext` | YES |  |  |  | 技术主题分类 |
| 122 | `seic` | `mediumtext` | YES |  |  |  | 战略新兴产业分类 |
| 123 | `cite_category` | `varchar(3)` | YES |  |  |  | 引用类别 |
| 124 | `epds_count` | `int` | YES |  |  |  | EP指定国家/地区数量 |
| 125 | `up_status` | `int` | YES |  |  |  | 欧洲统一法院状态 |
| 126 | `epds_legal_status` | `int` | YES |  |  |  | EP指定国家/地区法律状态 |
| 127 | `patent_value` | `int` | YES |  |  |  | 专利价值(美元) |
| 128 | `gov` | `mediumtext` | YES |  |  |  | 政府利益 |
| 129 | `examine_period` | `int` | YES |  |  |  | 审查时长 |
| 130 | `sep` | `mediumtext` | YES |  |  |  | 标准专利 |
| 131 | `award` | `mediumtext` | YES |  |  |  | 奖励 |
| 132 | `sub_case` | `mediumtext` | YES |  |  |  | 分案 |
| 133 | `priority_country_count` | `int` | YES |  |  |  | 优先权国家/地区个数 |
| 134 | `case_number` | `mediumtext` | YES |  |  |  | 案件号 |
| 135 | `court` | `mediumtext` | YES |  |  |  | 审查法院 |
| 136 | `judge` | `mediumtext` | YES |  |  |  | 审判员 |
| 137 | `chief_judge` | `mediumtext` | YES |  |  |  | 审判长 |
| 138 | `plaintiff` | `mediumtext` | YES |  |  |  | 原告 |
| 139 | `defendant` | `mediumtext` | YES |  |  |  | 被告 |
| 140 | `case_filing_date` | `date` | YES |  |  |  | 立案日期 |
| 141 | `verdict_date` | `date` | YES |  |  |  | 裁判日期 |
| 142 | `hearing_date` | `date` | YES |  |  |  | 听证日期 |
| 143 | `trial_grade` | `mediumtext` | YES |  |  |  | 审理程序 |
| 144 | `case` | `mediumtext` | YES |  |  |  | 案件 |
| 145 | `case_close_date` | `date` | YES |  |  |  | 结案日期 |
| 146 | `outcome` | `mediumtext` | YES |  |  |  | 案件结果 |
| 147 | `litigation_count` | `int` | YES |  |  |  | 诉讼次数 |
| 148 | `case_doc_type` | `int` | YES |  |  |  | 文书类型 |
| 149 | `court_grade` | `varchar(4)` | YES |  |  |  | 法院级别 |
| 150 | `verdict` | `mediumtext` | YES |  |  |  | 判决结果 |
| 151 | `party` | `mediumtext` | YES |  |  |  | 当事人 |
| 152 | `amount_plaintiff` | `int` | YES |  |  |  | 申请赔偿总额 |
| 153 | `damages_amount` | `int` | YES |  |  |  | 判赔总额 |
| 154 | `case_filing_year` | `int` | YES |  |  |  | 立案年份 |
| 155 | `litigation_product` | `mediumtext` | YES |  |  |  | 涉及产品 |
| 156 | `licensor` | `mediumtext` | YES |  |  |  | 许可人 |
| 157 | `licensee` | `mediumtext` | YES |  |  |  | 被许可人 |
| 158 | `license_number` | `mediumtext` | YES |  |  |  | 许可合同备案号 |
| 159 | `exclusivity` | `mediumtext` | YES |  |  |  | 许可排他性 |
| 160 | `license_effective_date` | `date` | YES |  |  |  | 许可生效日 |
| 161 | `license_count` | `int` | YES |  |  |  | 许可次数 |
| 162 | `transfer` | `mediumtext` | YES |  |  |  | 权利转移 |
| 163 | `review_invalid_applicant` | `mediumtext` | YES |  |  |  | 复审/无效请求人 |
| 164 | `review_invalid_decision_number` | `mediumtext` | YES |  |  |  | 决定号 |
| 165 | `review_invalid_commission_number` | `mediumtext` | YES |  |  |  | 委内编号 |
| 166 | `review_invalid_decision_date` | `date` | YES |  |  |  | 决定/发文日 |
| 167 | `review_invalid_decision_type` | `mediumtext` | YES |  |  |  | 决定类型 |
| 168 | `review_invalid_decision` | `mediumtext` | YES |  |  |  | 决定 |
| 169 | `review_invalid_decision_point` | `mediumtext` | YES |  |  |  | 决定要点 |
| 170 | `review_invalid_decision_case_mainpoint` | `mediumtext` | YES |  |  |  | 案由 |
| 171 | `review_invalid_legal_basis` | `mediumtext` | YES |  |  |  | 法律依据 |
| 172 | `review_invalid_fulltext` | `mediumtext` | YES |  |  |  | 复审/无效全文 |
| 173 | `invalid_count` | `int` | YES |  |  |  | 无效次数 |
| 174 | `pledgor` | `mediumtext` | YES |  |  |  | 质押人 |
| 175 | `pledgee` | `mediumtext` | YES |  |  |  | 质权人 |
| 176 | `pledgeno` | `mediumtext` | YES |  |  |  | 质押登记号 |
| 177 | `pledge` | `mediumtext` | YES |  |  |  | 质押信息 |
| 178 | `summarize` | `mediumtext` | YES |  |  |  | 总结 |
| 179 | `spare_zero` | `mediumtext` | YES |  |  |  | 备用0 |
| 180 | `spare_one` | `mediumtext` | YES |  |  |  | 备用1 |
| 181 | `spare_two` | `mediumtext` | YES |  |  |  | 备用2 |
| 182 | `spare_three` | `mediumtext` | YES |  |  |  | 备用3 |
| 183 | `spare_four` | `mediumtext` | YES |  |  |  | 备用4 |
| 184 | `spare_five` | `mediumtext` | YES |  |  |  | 备用5 |
| 185 | `spare_six` | `mediumtext` | YES |  |  |  | 备用6 |
| 186 | `spare_seven` | `mediumtext` | YES |  |  |  | 备用7 |
| 187 | `spare_eight` | `varchar(1024)` | YES |  |  |  | 备用8 |
| 188 | `spare_nine` | `varchar(1024)` | YES |  |  |  | 备用9 |
| 189 | `spare_ten` | `varchar(1024)` | YES |  |  |  | 备用10 |
| 190 | `state` | `tinyint` | YES |  | 1 |  | 逻辑删除(1:存在，0:不存在) |
| 191 | `created_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 192 | `updated_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 更新时间 |

## `ods_patent_Biblio_`

表注释：全球专利-著录项目

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `exdt` | `int` | YES |  |  |  | 智慧芽专利预估到期日 |
| 4 | `parties` | `text` | YES |  |  |  | 当事人信息(申请人、发明人等) |
| 5 | `abstracts` | `text` | YES |  |  |  | 摘要信息 |
| 6 | `patent_type` | `varchar(20)` | YES |  |  |  | 专利类型 |
| 7 | `invention_title` | `text` | YES |  |  |  | 标题信息 |
| 8 | `priority_claims` | `text` | YES |  |  |  | 优先权信息 |
| 9 | `reference_cited` | `text` | YES |  |  |  | 应用专利信息 |
| 10 | `related_documents` | `text` | YES |  |  |  | 分案申请、继续申请信息 |
| 11 | `classification_data` | `text` | YES |  |  |  | 分类数据 |
| 12 | `application_reference` | `text` | YES |  |  |  | 申请信息 |
| 13 | `publication_reference` | `text` | YES |  |  |  | 公开信息 |
| 14 | `pct_or_regional_filing_data` | `text` | YES |  |  |  | PCT申请信息 |
| 15 | `dates_of_public_availability` | `text` | YES |  |  |  | 授权信息 |
| 16 | `pct_or_regional_publishing_data` | `text` | YES |  |  |  | PCT公开信息 |

## `ods_patent_Cited`

表注释：全球专利-专利被引用

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `patent_cited` | `text` | YES |  |  |  | 被引用详情 |

## `ods_patent_Claims`

表注释：全球专利-权利要求

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `claims` | `text` | YES |  |  |  | 权利要求信息 |
| 4 | `claim_count` | `int` | YES |  |  |  | 权利要求统计 |

## `ods_patent_Description`

表注释：全球专利-说明书

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `description` | `text` | YES |  |  |  | 说明书信息 |

## `ods_patent_Drawing`

表注释：全球专利-摘要附图

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `abstract_drawing` | `text` | YES |  |  |  | 摘要附图信息 |

## `ods_patent_Family`

表注释：全球专利-专利家族

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `patent_family` | `text` | YES |  |  |  | 专利家族信息 |

## `ods_patent_LegalStatus`

表注释：全球专利-法律状态

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `patent_id` | `varchar(20)` | NO | PRI |  |  | 专利主键ID |
| 2 | `pn` | `varchar(32)` | NO |  |  |  | 专利公开(公告)号 |
| 3 | `legal_date` | `varchar(20)` | YES |  |  |  | 法定日期 |
| 4 | `patent_legal` | `text` | YES |  |  |  | 法律状态详情 |

## `ods_patent_weipu`

表注释：维普专利信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `lngid` | `varchar(50)` | YES |  |  |  |  |
| 2 | `media_c` | `varchar(50)` | YES |  |  |  |  |
| 3 | `years` | `int` | YES |  |  |  |  |
| 4 | `title_c` | `text` | YES |  |  |  |  |
| 5 | `title_e` | `text` | YES |  |  |  |  |
| 6 | `keyword_c` | `text` | YES |  |  |  |  |
| 7 | `keyword_e` | `text` | YES |  |  |  |  |
| 8 | `remark_c` | `text` | YES |  |  |  |  |
| 9 | `remark_e` | `text` | YES |  |  |  |  |
| 10 | `class` | `varchar(50)` | YES |  |  |  |  |
| 11 | `firstclass` | `varchar(50)` | YES |  |  |  |  |
| 12 | `beginpage` | `varchar(50)` | YES |  |  |  |  |
| 13 | `endpage` | `varchar(50)` | YES |  |  |  |  |
| 14 | `jumppage` | `varchar(50)` | YES |  |  |  |  |
| 15 | `pagecount` | `int` | YES |  |  |  |  |
| 16 | `showwriter` | `varchar(512)` | YES |  |  |  |  |
| 17 | `author_e` | `varchar(512)` | YES |  |  |  |  |
| 18 | `showorgan` | `varchar(512)` | YES |  |  |  |  |
| 19 | `intpdf` | `int` | YES |  |  |  |  |
| 20 | `country` | `varchar(50)` | YES |  |  |  |  |
| 21 | `language` | `int` | YES |  |  |  |  |
| 22 | `type` | `int` | YES |  |  |  |  |
| 23 | `classtypes` | `varchar(512)` | YES |  |  |  |  |
| 24 | `showclasstypes` | `varchar(512)` | YES |  |  |  |  |
| 25 | `fulltextaddress` | `text` | YES |  |  |  |  |
| 26 | `zlmaintype` | `varchar(50)` | YES |  |  |  |  |
| 27 | `zlapplicantaddr` | `text` | YES |  |  |  |  |
| 28 | `zlprovincecode` | `varchar(50)` | YES |  |  |  |  |
| 29 | `zlapplicationnum` | `varchar(50)` | YES |  |  |  |  |
| 30 | `zlapplicationdata` | `int` | YES |  |  |  |  |
| 31 | `zlopendata` | `int` | YES |  |  |  |  |
| 32 | `zlpriority` | `text` | YES |  |  |  |  |
| 33 | `zlprioritynumber` | `varchar(50)` | YES |  |  |  |  |
| 34 | `zlmainclassnum` | `varchar(50)` | YES |  |  |  |  |
| 35 | `zlclassnum` | `varchar(128)` | YES |  |  |  |  |
| 36 | `zlinternationalpub` | `varchar(50)` | YES |  |  |  |  |
| 37 | `zlinternationalapp` | `varchar(50)` | YES |  |  |  |  |
| 38 | `zlcomeindata` | `int` | YES |  |  |  |  |
| 39 | `zlsovereignty` | `text` | YES |  |  |  |  |
| 40 | `zlagents` | `varchar(50)` | YES |  |  |  |  |
| 41 | `zlagency` | `varchar(256)` | YES |  |  |  |  |
| 42 | `zllegalstatus` | `varchar(512)` | YES |  |  |  |  |
| 43 | `zlthesissize` | `int` | YES |  |  |  |  |
| 44 | `zlaccdate` | `int` | YES |  |  |  |  |
| 45 | `zlpatentstate` | `varchar(512)` | YES |  |  |  |  |
