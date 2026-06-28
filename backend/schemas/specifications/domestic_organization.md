# 国内机构字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_org_annual_financial_info` | 前海数据机构年报财务信息 | 5220 | 15 |
| `dwd_org_bankruptcy_public_cases` | 破产案件表 | 1865 | 15 |
| `dwd_org_bankruptcy_public_cases_list` | 破产案件当事人表 | 1920 | 13 |
| `dwd_org_bid_info` | 前海数据机构招投标事件 | 1917 | 11 |
| `dwd_org_change_record_info` | 前海数据机构工商变更信息 | 1586 | 10 |
| `dwd_org_company_abnormal` | 前海数据机构经营异常事件 | 1947 | 15 |
| `dwd_org_company_chattel` | 动产抵押表 | 1945 | 20 |
| `dwd_org_company_illegal` | 前海数据机构严重违法 | 1941 | 16 |
| `dwd_org_company_justice` | 股权冻结表 | 1968 | 16 |
| `dwd_org_company_pledge` | 股权出质表 | 1950 | 31 |
| `dwd_org_company_punish` | 前海数据机构行政处罚记录 | 235 | 24 |
| `dwd_org_executive_info` | 前海数据机构高管信息 | 5507 | 8 |
| `dwd_org_financing_info` | 前海数据机构融资事件 | 973 | 12 |
| `dwd_org_hels_info` | 前海数据高校与科研机构信息 | 3217 | 19 |
| `dwd_org_important_news_info` | 前海数据机构重点资讯 | 879 | 10 |
| `dwd_org_innovation_carrier` | 前海数据机构创新载体信息 | 1374 | 13 |
| `dwd_org_invest_info` | 前海数据机构投资事件 | 4138 | 11 |
| `dwd_org_merger_acquisition_info` | 前海数据机构并购事件 | 922 | 10 |
| `dwd_org_opt_judicial_case` | 前海数据机构司法案件事件 | 1868 | 16 |
| `dwd_org_org_product_info` | 前海数据机构经营信息 | 943 | 10 |
| `dwd_org_recruit_info` | 前海数据招聘信息 | 1817 | 11 |
| `dwd_org_reg_info` | 前海数据机构基本信息 | 1524 | 22 |
| `dwd_org_risk_court_announcement` | 法院公告表 | 1839 | 29 |
| `dwd_org_risk_court_announcement_list` | 法院公告当事人表 | 1957 | 14 |
| `dwd_org_risk_court_filed_case` | 法院立案表 | 1953 | 20 |
| `dwd_org_risk_court_filed_case_litigant` | 法院立案当事人表 | 1972 | 12 |
| `dwd_org_risk_court_notice` | 开庭公告表 | 1947 | 24 |
| `dwd_org_risk_court_notice_list` | 开庭公告当事人表 | 1908 | 16 |
| `dwd_org_risk_lawsuit` | 裁判文书 | 1364 | 27 |
| `dwd_org_risk_lawsuit_list` | 裁判文书当事人表 | 1953 | 15 |
| `dwd_org_risk_shixin` | 前海数据机构失信被执行人记录 | 1775 | 31 |
| `dwd_org_risk_tax_punish` | 前海数据机构税收违法 | 1876 | 25 |
| `dwd_org_risk_xianxiao` | 前海机构限制高消费记录 | 1916 | 16 |
| `dwd_org_risk_zhixing` | 前海数据机构被执行人记录 | 1900 | 20 |
| `dwd_org_risk_zhongben` | 终本案件表 | 1962 | 22 |
| `dwd_org_shareholder_info` | 前海数据机构股东信息 | 2283 | 10 |
| `dwd_org_stock_base` | 前海数据上市企业基本信息 | 5837 | 11 |
| `dwd_org_stock_finance_info` | 前海数据上市企业主要财务指标 | 5269 | 21 |
| `dwd_org_tag_info` | 前海数据机构标签表 | 2730 | 8 |
| `dwd_org_tb_judicial_sale` | 司法拍卖表 | 1987 | 13 |
| `dwd_org_tb_judicial_sale_info_company` | 司法拍卖当事人表 | 1940 | 9 |

## `dwd_org_annual_financial_info`

表注释：前海数据机构年报财务信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `year` | `int` | YES |  |  |  | 年报年度 |
| 5 | `total_assets` | `double` | YES |  |  |  | 资产总额 |
| 6 | `total_fixed_assets` | `double` | YES |  |  |  | 固定资产总额 |
| 7 | `total_liabilities` | `double` | YES |  |  |  | 负债总额 |
| 8 | `operating_revenue` | `double` | YES |  |  |  | 营业收入 |
| 9 | `main_business_revenue` | `double` | YES |  |  |  | 主营业务收入 |
| 10 | `total_profit` | `double` | YES |  |  |  | 利润总额 |
| 11 | `pure_profit` | `double` | YES |  |  |  | 净利润 |
| 12 | `total_tax_paid` | `double` | YES |  |  |  | 纳税总额 |
| 13 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 14 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 15 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_bankruptcy_public_cases`

表注释：破产案件表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 2 | `case_type` | `varchar(255)` | YES |  |  |  | 案件类型 |
| 3 | `handling_court` | `varchar(255)` | YES |  |  |  | 经办法院 |
| 4 | `applicant_info` | `text` | YES |  |  |  | 申请人信息 |
| 5 | `respondent_info` | `text` | YES |  |  |  | 被申请人信息 |
| 6 | `admin_org` | `varchar(255)` | YES |  |  |  | 管理人机构 |
| 7 | `admin_org_id` | `varchar(255)` | YES |  |  |  | 管理人机构id |
| 8 | `admin_principal` | `varchar(255)` | YES |  |  |  | 管理人主要负责人 |
| 9 | `public_date` | `varchar(255)` | YES |  |  |  | 公开时间 |
| 10 | `link` | `text` | YES |  |  |  | 链接 |
| 11 | `is_deleted` | `varchar(255)` | YES |  |  |  | 是否删除 |
| 12 | `history_status` | `varchar(255)` | YES |  |  |  | 历史状态 |
| 13 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 14 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 15 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_bankruptcy_public_cases_list`

表注释：破产案件当事人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `bankruptcy_party_id` | `varchar(255)` | YES |  |  |  | 唯一索引id |
| 2 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 3 | `related_person_name` | `varchar(255)` | YES |  |  |  | 相关人名称 |
| 4 | `party_role_type` | `varchar(255)` | YES |  |  |  | 当事人角色类型 |
| 5 | `party_type` | `varchar(255)` | YES |  |  |  | 当事人类型 |
| 6 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 7 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 8 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 9 | `public_date` | `varchar(255)` | YES |  |  |  | 公开时间 |
| 10 | `is_deleted` | `varchar(255)` | YES |  |  |  | 是否删除 |
| 11 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 12 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 13 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_bid_info`

表注释：前海数据机构招投标事件

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `tender_org_id` | `varchar(50)` | YES |  |  |  | 采购单位id |
| 2 | `tender_name_cn` | `varchar(255)` | YES |  |  |  | 采购单位名称 |
| 3 | `tender_social_credit_code` | `varchar(50)` | YES |  |  |  | 采购单位统一社会信用代码 |
| 4 | `winner_org_id` | `varchar(50)` | YES |  |  |  | 中标单位id |
| 5 | `winner_name_cn` | `varchar(255)` | YES |  |  |  | 中标单位名称 |
| 6 | `winner_social_credit_code` | `varchar(50)` | YES |  |  |  | 中标单位统一社会信用代码 |
| 7 | `announcement_title` | `varchar(255)` | YES |  |  |  | 公告标题 |
| 8 | `announcement_content` | `varchar(50)` | YES |  |  |  | 中标成交信息 |
| 9 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 10 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 11 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_change_record_info`

表注释：前海数据机构工商变更信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `update_content` | `varchar(50)` | YES |  |  |  | 变更类型 |
| 5 | `current_name` | `varchar(1000)` | YES |  |  |  | 变更前内容 |
| 6 | `update_name` | `varchar(1000)` | YES |  |  |  | 变更后内容 |
| 7 | `update_date` | `varchar(50)` | YES |  |  |  | 变更日期 |
| 8 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 10 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_company_abnormal`

表注释：前海数据机构经营异常事件

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `abnormal_id` | `varchar(50)` | YES |  |  |  | 经营异常记录id |
| 5 | `abn_reason` | `varchar(1000)` | YES |  |  |  | 列入原因 |
| 6 | `abn_date` | `varchar(50)` | YES |  |  |  | 列入时间 |
| 7 | `abn_org` | `varchar(50)` | YES |  |  |  | 列入机关 |
| 8 | `remove_reason` | `varchar(1000)` | YES |  |  |  | 移除原因 |
| 9 | `remove_date` | `varchar(50)` | YES |  |  |  | 移除时间 |
| 10 | `remove_org` | `varchar(50)` | YES |  |  |  | 移除机关 |
| 11 | `use_flag` | `int` | YES |  |  |  | 使用标记 |
| 12 | `status_code` | `int` | YES |  |  |  | 状态 |
| 13 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 14 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 15 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_company_chattel`

表注释：动产抵押表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `reg_no` | `varchar(255)` | YES |  |  |  | 登记编号 |
| 5 | `reg_date` | `varchar(255)` | YES |  |  |  | 登记日期 |
| 6 | `reg_org` | `varchar(255)` | YES |  |  |  | 登记机关 |
| 7 | `guarantee_type` | `varchar(255)` | YES |  |  |  | 被担保债权种类 |
| 8 | `guarantee_amount` | `varchar(255)` | YES |  |  |  | 被担保债权数额 |
| 9 | `guarantee_scope` | `text` | YES |  |  |  | 担保范围 |
| 10 | `public_date` | `varchar(255)` | YES |  |  |  | 公示日期 |
| 11 | `debt_term` | `varchar(255)` | YES |  |  |  | 债务人履行债务的期限 |
| 12 | `debt_remark` | `text` | YES |  |  |  | 主债权信息备注 |
| 13 | `status` | `varchar(255)` | YES |  |  |  | 状态 |
| 14 | `cancel_date` | `varchar(255)` | YES |  |  |  | 注销日期 |
| 15 | `cancel_reason` | `text` | YES |  |  |  | 注销原因 |
| 16 | `status_code` | `varchar(255)` | YES |  |  |  | 状态代码 |
| 17 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标记 |
| 18 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 19 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 20 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_company_illegal`

表注释：前海数据机构严重违法

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `sv_id` | `varchar(50)` | YES |  |  |  | 严重违法记录id |
| 5 | `category` | `varchar(50)` | YES |  |  |  | 类别 |
| 6 | `abn_reason` | `varchar(1000)` | YES |  |  |  | 列入原因 |
| 7 | `abn_date` | `varchar(50)` | YES |  |  |  | 列入时间 |
| 8 | `abn_org` | `varchar(50)` | YES |  |  |  | 列入机关 |
| 9 | `remove_reason` | `varchar(1000)` | YES |  |  |  | 移除原因 |
| 10 | `remove_date` | `varchar(50)` | YES |  |  |  | 移除时间 |
| 11 | `remove_org` | `varchar(50)` | YES |  |  |  | 移除机关 |
| 12 | `status` | `int` | YES |  |  |  | 状态 |
| 13 | `use_flag` | `int` | YES |  |  |  | 使用标记 |
| 14 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 15 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 16 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_company_justice`

表注释：股权冻结表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 2 | `judicial_assist_id` | `varchar(255)` | YES |  |  |  | 司法协助记录id |
| 3 | `executed_person` | `varchar(255)` | YES |  |  |  | 被执行人 |
| 4 | `equity_amount` | `varchar(255)` | YES |  |  |  | 股权数额 |
| 5 | `exec_court` | `varchar(255)` | YES |  |  |  | 执行法院 |
| 6 | `exec_notice_no` | `varchar(255)` | YES |  |  |  | 执行通知书文号 |
| 7 | `type_status` | `varchar(255)` | YES |  |  |  | 类型\|状态 |
| 8 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标记 |
| 9 | `status` | `varchar(255)` | YES |  |  |  | 状态 |
| 10 | `executed_person_type` | `varchar(255)` | YES |  |  |  | 被执行人类型 |
| 11 | `executed_company_id` | `varchar(255)` | YES |  |  |  | 被执行人的company_id |
| 12 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 13 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 14 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 15 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 16 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_company_pledge`

表注释：股权出质表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `pledge_id` | `varchar(255)` | YES |  |  |  | 股权出质记录id |
| 5 | `reg_no` | `varchar(255)` | YES |  |  |  | 登记编号 |
| 6 | `pledgor` | `varchar(255)` | YES |  |  |  | 出质人 |
| 7 | `pledgor_id_no` | `varchar(255)` | YES |  |  |  | 出质人证件号码 |
| 8 | `pledgee` | `varchar(255)` | YES |  |  |  | 质权人 |
| 9 | `pledgee_id_no` | `varchar(255)` | YES |  |  |  | 质权人证件号码 |
| 10 | `equity_amount` | `varchar(255)` | YES |  |  |  | 出质股权数额 |
| 11 | `pledge_reg_date` | `varchar(255)` | YES |  |  |  | 股权出质设立登记日期 |
| 12 | `status` | `varchar(255)` | YES |  |  |  | 状态 |
| 13 | `public_date` | `varchar(255)` | YES |  |  |  | 公示日期 |
| 14 | `cancel_date` | `varchar(255)` | YES |  |  |  | 注销日期 |
| 15 | `cancel_reason` | `text` | YES |  |  |  | 注销原因 |
| 16 | `invalid_date` | `varchar(255)` | YES |  |  |  | 失效时间 |
| 17 | `invalid_reason` | `text` | YES |  |  |  | 失效原因 |
| 18 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标记 |
| 19 | `status_code` | `varchar(255)` | YES |  |  |  | 状态代码 |
| 20 | `province_abbr` | `varchar(255)` | YES |  |  |  | 省份简称 |
| 21 | `pledgor_company_id` | `varchar(255)` | YES |  |  |  | 机构出质人的company_id |
| 22 | `pledgor_company_name` | `varchar(255)` | YES |  |  |  | 机构出质人名称 |
| 23 | `pledgor_credit_code` | `varchar(255)` | YES |  |  |  | 机构出质人统一社会信用代码 |
| 24 | `pledgor_type` | `varchar(255)` | YES |  |  |  | 出质人类型 |
| 25 | `pledgee_company_id` | `varchar(255)` | YES |  |  |  | 机构质权人的company_id |
| 26 | `pledgee_company_name` | `varchar(255)` | YES |  |  |  | 机构质权人名称 |
| 27 | `pledgee_credit_code` | `varchar(255)` | YES |  |  |  | 机构质权人统一社会信用代码 |
| 28 | `pledgee_type` | `varchar(255)` | YES |  |  |  | 质权人类型 |
| 29 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 30 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 31 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_company_punish`

表注释：前海数据机构行政处罚记录

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `penalty_id` | `varchar(50)` | YES |  |  |  | 行政处罚记录id |
| 5 | `decision_no` | `varchar(50)` | YES |  |  |  | 决定书文号 |
| 6 | `violation_type` | `varchar(256)` | YES |  |  |  | 违法行为类型 |
| 7 | `penalty_content` | `mediumtext` | YES |  |  |  | 行政处罚内容 |
| 8 | `decision_org` | `varchar(50)` | YES |  |  |  | 决定机关 |
| 9 | `penalty_date` | `varchar(50)` | YES |  |  |  | 处罚决定日期 |
| 10 | `public_date` | `varchar(50)` | YES |  |  |  | 公示日期 |
| 11 | `penalty_basis` | `varchar(512)` | YES |  |  |  | 处罚依据 |
| 12 | `violation_fact` | `mediumtext` | YES |  |  |  | 主要违法事实 |
| 13 | `penalty_type` | `varchar(512)` | YES |  |  |  | 处罚种类 |
| 14 | `fine_amount` | `varchar(100)` | YES |  |  |  | 罚款金额 |
| 15 | `confiscate_amount` | `varchar(100)` | YES |  |  |  | 没收金额 |
| 16 | `license_info` | `varchar(50)` | YES |  |  |  | 暂扣或吊销证照名称及编号 |
| 17 | `validity_period` | `varchar(50)` | YES |  |  |  | 处罚有效期 |
| 18 | `public_deadline` | `varchar(50)` | YES |  |  |  | 公示截止日期 |
| 19 | `remark` | `varchar(50)` | YES |  |  |  | 备注 |
| 20 | `use_flag` | `int` | YES |  |  |  | 使用标记 |
| 21 | `status_code` | `int` | YES |  |  |  | 状态代码 |
| 22 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 23 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 24 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_executive_info`

表注释：前海数据机构高管信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `executives_name` | `varchar(50)` | YES |  |  |  | 高管姓名 |
| 5 | `executives_position` | `varchar(50)` | YES |  |  |  | 职位名称 |
| 6 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 7 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 8 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_financing_info`

表注释：前海数据机构融资事件

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `funding_round` | `varchar(50)` | YES |  |  |  | 融资轮次 |
| 5 | `funding_amount` | `bigint` | YES |  |  |  | 获投金额 |
| 6 | `funding_currency_code` | `varchar(50)` | YES |  |  |  | 金额币种 |
| 7 | `post_valuation` | `bigint` | YES |  |  |  | 投后估值 |
| 8 | `completion_date` | `varchar(50)` | YES |  |  |  | 融资完成时间 |
| 9 | `investors_name` | `varchar(500)` | YES |  |  |  | 投资方列表 |
| 10 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 11 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 12 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_hels_info`

表注释：前海数据高校与科研机构信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 高校id |
| 2 | `name_cn` | `varchar(256)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `org_name` | `varchar(256)` | YES |  |  |  | 高校/科研机构名称(中文) |
| 5 | `org_name_en` | `varchar(256)` | YES |  |  |  | 高校/科研机构名称(英文) |
| 6 | `org_desc` | `text` | YES |  |  |  | 高校/科研机构描述 |
| 7 | `address` | `varchar(500)` | YES |  |  |  | 地址(国家、区域、城市) |
| 8 | `addr_lng` | `double` | YES |  |  |  | 地址对应经度 |
| 9 | `addr_lat` | `double` | YES |  |  |  | 地址对应维度 |
| 10 | `province` | `varchar(50)` | YES |  |  |  | 地址所在省 |
| 11 | `city` | `varchar(50)` | YES |  |  |  | 地址所在市 |
| 12 | `univ_type` | `varchar(50)` | YES |  |  |  | 高校类型 |
| 13 | `web_link` | `varchar(100)` | YES |  |  |  | 官方网址 |
| 14 | `postal_code` | `varchar(50)` | YES |  |  |  | 邮政编码 |
| 15 | `contact_number` | `varchar(500)` | YES |  |  |  | 联系电话 |
| 16 | `email` | `text` | YES |  |  |  | 电子邮箱 |
| 17 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 18 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 19 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_important_news_info`

表注释：前海数据机构重点资讯

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `news_title` | `varchar(1000)` | YES |  |  |  | 资讯标题 |
| 5 | `news_date` | `varchar(50)` | YES |  |  |  | 资讯日期 |
| 6 | `news_content` | `varchar(1000)` | YES |  |  |  | 资讯内容 |
| 7 | `original_textlink` | `varchar(255)` | YES |  |  |  | 咨询原文链接 |
| 8 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 10 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_innovation_carrier`

表注释：前海数据机构创新载体信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `carrier_type` | `varchar(50)` | YES |  |  |  | 载体/平台/中心类型 |
| 2 | `carrier_name` | `varchar(200)` | YES |  |  |  | 载体/平台/中心名称 |
| 3 | `carrier_level` | `varchar(50)` | YES |  |  |  | 载体/平台/中心级别 |
| 4 | `create_year` | `int` | YES |  |  |  | 组建/认定/立项年份 |
| 5 | `area` | `varchar(50)` | YES |  |  |  | 载体/平台/中心所在地区 |
| 6 | `area_code` | `varchar(50)` | YES |  |  |  | 所在地区行政区划代码 |
| 7 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 8 | `org_name` | `varchar(200)` | YES |  |  |  | 关联单位名称 |
| 9 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 10 | `announcement` | `varchar(500)` | YES |  |  |  | 公告名称 |
| 11 | `publish_org` | `varchar(50)` | YES |  |  |  | 发布单位 |
| 12 | `publish_date` | `varchar(50)` | YES |  |  |  | 发布日期 |
| 13 | `source_url` | `varchar(500)` | YES |  |  |  | 来源链接 |

## `dwd_org_invest_info`

表注释：前海数据机构投资事件

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `inv_org_id` | `varchar(50)` | YES |  |  |  | 被投企业id |
| 5 | `inv_name` | `varchar(50)` | YES |  |  |  | 被投资企业名称 |
| 6 | `inv_social_credit_code` | `varchar(50)` | YES |  |  |  | 被投资企业统一社会信用代码 |
| 7 | `investment_amount` | `double` | YES |  |  |  | 投资金额(元) |
| 8 | `investment_ratio` | `double` | YES |  |  |  | 股权占比(%) |
| 9 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 10 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 11 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_merger_acquisition_info`

表注释：前海数据机构并购事件

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `event_time` | `varchar(50)` | YES |  |  |  | 公告日期 |
| 2 | `ma_amount` | `double` | YES |  |  |  | 交易金额 |
| 3 | `currency_code` | `varchar(50)` | YES |  |  |  | 币种 |
| 4 | `acquiring_org_id` | `varchar(50)` | YES |  |  |  | 发起收购企业id |
| 5 | `acquiring_name` | `varchar(50)` | YES |  |  |  | 发起收购企业名称 |
| 6 | `acquired_org_id` | `varchar(50)` | YES |  |  |  | 被收购企业id |
| 7 | `acquired_name` | `varchar(50)` | YES |  |  |  | 被收购企业 |
| 8 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 10 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_opt_judicial_case`

表注释：前海数据机构司法案件事件

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `company_name` | `varchar(50)` | YES |  |  |  | 企业名称 |
| 2 | `reg_no` | `varchar(50)` | YES |  |  |  | 注册号 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 5 | `case_id` | `varchar(50)` | YES |  |  |  | 司法案件唯一标识 |
| 6 | `case_title` | `varchar(1000)` | YES |  |  |  | 案件标题 |
| 7 | `case_type_tag` | `varchar(100)` | YES |  |  |  | 案件类型标签 |
| 8 | `case_no` | `varchar(1000)` | YES |  |  |  | 案号 |
| 9 | `case_cause` | `varchar(500)` | YES |  |  |  | 案由 |
| 10 | `case_role` | `varchar(500)` | YES |  |  |  | 案件身份 |
| 11 | `current_procedure` | `varchar(50)` | YES |  |  |  | 当前审理程序 |
| 12 | `procedure_date` | `varchar(50)` | YES |  |  |  | 当前审理程序日期 |
| 13 | `data_use_flag` | `int` | YES |  |  |  | 数据使用标识 |
| 14 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 15 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 16 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_org_product_info`

表注释：前海数据机构经营信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `industry_class` | `varchar(50)` | YES |  |  |  | 公司行业分类 |
| 5 | `main_activities` | `text` | YES |  |  |  | 公司经营范围 |
| 6 | `description` | `text` | YES |  |  |  | 业务描述 |
| 7 | `main_prod` | `text` | YES |  |  |  | 主要产品 |
| 8 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 10 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_recruit_info`

表注释：前海数据招聘信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `job_title` | `varchar(255)` | YES |  |  |  | 岗位 |
| 5 | `job_description` | `text` | YES |  |  |  | 工作描述 |
| 6 | `work_place` | `varchar(500)` | YES |  |  |  | 工作地点 |
| 7 | `release_date` | `varchar(50)` | YES |  |  |  | 发布日期 |
| 8 | `hiring_number` | `varchar(50)` | YES |  |  |  | 招聘人数 |
| 9 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 10 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 11 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_reg_info`

表注释：前海数据机构基本信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `province` | `varchar(50)` | YES |  |  |  | 所在省份 |
| 5 | `city` | `varchar(50)` | YES |  |  |  | 所在城市 |
| 6 | `address` | `varchar(1000)` | YES |  |  |  | 公司地址 |
| 7 | `addr_lng` | `double` | YES |  |  |  | 地址经度 |
| 8 | `addr_lat` | `double` | YES |  |  |  | 地址纬度 |
| 9 | `postal_code` | `varchar(50)` | YES |  |  |  | 邮编 |
| 10 | `lerep` | `varchar(50)` | YES |  |  |  | 法人代表 |
| 11 | `registration_org` | `varchar(50)` | YES |  |  |  | 登记机关 |
| 12 | `incorporation_year` | `int` | YES |  |  |  | 成立年 |
| 13 | `incorporation_date` | `varchar(50)` | YES |  |  |  | 成立日期 |
| 14 | `start_date` | `varchar(50)` | YES |  |  |  | 经营期限自 |
| 15 | `end_date` | `varchar(50)` | YES |  |  |  | 经营期限至 |
| 16 | `listing_status` | `varchar(50)` | YES |  |  |  | 上市状态 |
| 17 | `listing_date` | `varchar(50)` | YES |  |  |  | 上市日期 |
| 18 | `registered_capital_value` | `double` | YES |  |  |  | 注册资本金 |
| 19 | `capital_currency_code` | `varchar(50)` | YES |  |  |  | 资本货币代码 |
| 20 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 21 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 22 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_court_announcement`

表注释：法院公告表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `notice_id` | `varchar(255)` | YES |  |  |  | 公告id |
| 2 | `notice_no` | `varchar(255)` | YES |  |  |  | 公告号 |
| 3 | `notice_name` | `varchar(255)` | YES |  |  |  | 公告名称 |
| 4 | `notice_type` | `varchar(255)` | YES |  |  |  | 公告类型 |
| 5 | `notice_type_name` | `varchar(255)` | YES |  |  |  | 公告类型名称 |
| 6 | `notice_date` | `varchar(255)` | YES |  |  |  | 公告日期 |
| 7 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 8 | `title` | `text` | YES |  |  |  | 标题 |
| 9 | `notice_content` | `text` | YES |  |  |  | 公告内容 |
| 10 | `court_name` | `varchar(255)` | YES |  |  |  | 法院名称 |
| 11 | `handle_level` | `varchar(255)` | YES |  |  |  | 处理等级 |
| 12 | `handle_level_name` | `varchar(255)` | YES |  |  |  | 处理等级名称 |
| 13 | `judge` | `varchar(255)` | YES |  |  |  | 法官 |
| 14 | `judge_phone` | `varchar(255)` | YES |  |  |  | 法官电话 |
| 15 | `mobile_phone` | `varchar(255)` | YES |  |  |  | 手机号 |
| 16 | `plaintiff` | `varchar(255)` | YES |  |  |  | 原告 |
| 17 | `party` | `varchar(255)` | YES |  |  |  | 当事人 |
| 18 | `province` | `varchar(255)` | YES |  |  |  | 省份 |
| 19 | `case_cause` | `varchar(255)` | YES |  |  |  | 案由 |
| 20 | `notice_year` | `varchar(100)` | YES |  |  |  | 公告年份 |
| 21 | `publish_date` | `varchar(255)` | YES |  |  |  | 公告刊登日期 |
| 22 | `publish_page_no` | `varchar(255)` | YES |  |  |  | 公告刊登版面页码 |
| 23 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 24 | `original_url` | `text` | YES |  |  |  | 原始连接URL |
| 25 | `content_md5` | `varchar(255)` | YES |  |  |  | 公告内容的md5值 |
| 26 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 27 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 28 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 29 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_court_announcement_list`

表注释：法院公告当事人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `notice_id` | `varchar(255)` | YES |  |  |  | 公告id |
| 2 | `party_identity` | `varchar(255)` | YES |  |  |  | 当事人身份 |
| 3 | `party_type` | `varchar(255)` | YES |  |  |  | 当事人类型 |
| 4 | `party_role_type` | `varchar(255)` | YES |  |  |  | 当事人角色类型 |
| 5 | `related_person_name` | `varchar(255)` | YES |  |  |  | 相关人名称 |
| 6 | `publish_date` | `varchar(255)` | YES |  |  |  | 公告刊登日期 |
| 7 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 8 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 9 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 10 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 11 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 12 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 13 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 14 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_court_filed_case`

表注释：法院立案表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `case_unique_id` | `varchar(255)` | YES |  |  |  | 案件唯一id |
| 2 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 3 | `norm_case_no` | `varchar(255)` | YES |  |  |  | 归一化案号 |
| 4 | `case_cause` | `varchar(255)` | YES |  |  |  | 案由 |
| 5 | `trial_procedure` | `varchar(255)` | YES |  |  |  | 审理程序 |
| 6 | `case_status` | `varchar(255)` | YES |  |  |  | 案件状态 |
| 7 | `norm_case_status` | `varchar(255)` | YES |  |  |  | 归一化后案件状态 |
| 8 | `filing_date` | `varchar(255)` | YES |  |  |  | 立案日期 |
| 9 | `closing_date` | `varchar(255)` | YES |  |  |  | 结案日期 |
| 10 | `hearing_date` | `varchar(255)` | YES |  |  |  | 开庭日期 |
| 11 | `court_name` | `varchar(255)` | YES |  |  |  | 法院 |
| 12 | `undertaking_dept` | `varchar(255)` | YES |  |  |  | 承办部门 |
| 13 | `judge` | `varchar(255)` | YES |  |  |  | 法官 |
| 14 | `assistant_judge` | `varchar(255)` | YES |  |  |  | 助理法官 |
| 15 | `party_info` | `varchar(5000)` | YES |  |  |  | 当事人信息 |
| 16 | `court_province` | `varchar(255)` | YES |  |  |  | 法院所在省 |
| 17 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 18 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 19 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 20 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_court_filed_case_litigant`

表注释：法院立案当事人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `case_unique_id` | `varchar(255)` | YES |  |  |  | 案件唯一id |
| 2 | `filing_date` | `varchar(255)` | YES |  |  |  | 立案日期 |
| 3 | `party_name` | `varchar(255)` | YES |  |  |  | 当事人名称 |
| 4 | `party_role` | `varchar(255)` | YES |  |  |  | 当事人角色 |
| 5 | `classified_org_type` | `varchar(255)` | YES |  |  |  | 归类后企业类型 |
| 6 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 7 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 8 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 9 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 10 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 11 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 12 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_court_notice`

表注释：开庭公告表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `notice_id` | `varchar(255)` | YES |  |  |  | 公告id |
| 2 | `court_name` | `varchar(255)` | YES |  |  |  | 法院 |
| 3 | `courtroom` | `varchar(255)` | YES |  |  |  | 法庭 |
| 4 | `undertaking_dept` | `varchar(255)` | YES |  |  |  | 承办部门 |
| 5 | `hearing_date` | `varchar(255)` | YES |  |  |  | 开庭日期 |
| 6 | `scheduling_date` | `varchar(255)` | YES |  |  |  | 排期日期 |
| 7 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 8 | `case_cause` | `varchar(255)` | YES |  |  |  | 案由 |
| 9 | `case_type` | `varchar(255)` | YES |  |  |  | 案件类型 |
| 10 | `jurisdiction_area` | `varchar(255)` | YES |  |  |  | 案件管辖区域 |
| 11 | `plaintiff_appellant` | `varchar(255)` | YES |  |  |  | 原告上诉人 |
| 12 | `defendant_appellee` | `varchar(255)` | YES |  |  |  | 被告被上诉人 |
| 13 | `party` | `varchar(255)` | YES |  |  |  | 当事人 |
| 14 | `presiding_judge` | `varchar(255)` | YES |  |  |  | 审判长主审人 |
| 15 | `title` | `text` | YES |  |  |  | 标题 |
| 16 | `notice_content` | `text` | YES |  |  |  | 公告内容 |
| 17 | `province` | `varchar(255)` | YES |  |  |  | 省份 |
| 18 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 19 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 20 | `original_url` | `text` | YES |  |  |  | 原始连接URL |
| 21 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 22 | `data_source_2` | `varchar(255)` | YES |  |  |  | 数据来源（重复字段，已重命名避免冲突） |
| 23 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 24 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_court_notice_list`

表注释：开庭公告当事人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `notice_id` | `varchar(255)` | YES |  |  |  | 公告id |
| 2 | `party_role` | `varchar(255)` | YES |  |  |  | 当事人角色 |
| 3 | `party_role_type` | `varchar(255)` | YES |  |  |  | 当事人角色类型 |
| 4 | `party_type` | `varchar(255)` | YES |  |  |  | 当事人类型 |
| 5 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 6 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 7 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 8 | `related_person_name` | `varchar(255)` | YES |  |  |  | 相关人名称 |
| 9 | `hearing_date` | `varchar(255)` | YES |  |  |  | 开庭日期 |
| 10 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 11 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 12 | `case_cause` | `varchar(255)` | YES |  |  |  | 案由 |
| 13 | `reserve_field` | `varchar(255)` | YES |  |  |  | 预留字段 |
| 14 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 15 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 16 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_lawsuit`

表注释：裁判文书

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `judgment_doc_id` | `varchar(255)` | YES |  |  |  | 裁判文书网文书id |
| 2 | `defendant` | `varchar(255)` | YES |  |  |  | 被告 |
| 3 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 4 | `case_type_code` | `varchar(255)` | YES |  |  |  | 案件类型编码 |
| 5 | `case_type` | `varchar(255)` | YES |  |  |  | 案件类型 |
| 6 | `doc_type_code` | `varchar(255)` | YES |  |  |  | 文书类型编码 |
| 7 | `doc_type` | `varchar(255)` | YES |  |  |  | 文书类型 |
| 8 | `province` | `varchar(255)` | YES |  |  |  | 省份 |
| 9 | `city` | `varchar(255)` | YES |  |  |  | 地市 |
| 10 | `district` | `varchar(255)` | YES |  |  |  | 区县 |
| 11 | `main_doc_id` | `varchar(255)` | YES |  |  |  | 主表docid |
| 12 | `court_name` | `varchar(255)` | YES |  |  |  | 法院名称 |
| 13 | `trial_procedure` | `varchar(255)` | YES |  |  |  | 审理程序名称 |
| 14 | `judgment_year` | `int` | YES |  |  |  | 裁判年份 |
| 15 | `judgment_date` | `varchar(255)` | YES |  |  |  | 裁判日期 |
| 16 | `case_cause` | `varchar(255)` | YES |  |  |  | 案由 |
| 17 | `doc_title` | `text` | YES |  |  |  | 文书标题 |
| 18 | `doc_full_text` | `longtext` | YES |  |  |  | 文书全文 |
| 19 | `publish_date` | `varchar(255)` | YES |  |  |  | 公布日期 |
| 20 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 21 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 22 | `original_url` | `text` | YES |  |  |  | 原始连接URL |
| 23 | `plaintiff` | `varchar(255)` | YES |  |  |  | 原告 |
| 24 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 25 | `source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 26 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 27 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_lawsuit_list`

表注释：裁判文书当事人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `main_doc_id` | `varchar(255)` | YES |  |  |  | 主表docid |
| 2 | `party_identity` | `varchar(255)` | YES |  |  |  | 当事人身份 |
| 3 | `party_role_type` | `varchar(255)` | YES |  |  |  | 当事人角色类型 |
| 4 | `party_type` | `varchar(255)` | YES |  |  |  | 当事人类型 |
| 5 | `related_person_name` | `varchar(255)` | YES |  |  |  | 相关人名称 |
| 6 | `doc_publish_date` | `varchar(255)` | YES |  |  |  | 文书公布日期 |
| 7 | `case_cause` | `varchar(255)` | YES |  |  |  | 案由 |
| 8 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 9 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 10 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 11 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 12 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 13 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 14 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 15 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_shixin`

表注释：前海数据机构失信被执行人记录

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `dishonest_id` | `varchar(50)` | YES |  |  |  | 失信被执行人id |
| 2 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 3 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 4 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 5 | `official_id` | `varchar(50)` | YES |  |  |  | 官网id |
| 6 | `case_no` | `varchar(50)` | YES |  |  |  | 案号 |
| 7 | `dishonest_name` | `varchar(50)` | YES |  |  |  | 失信人名称 |
| 8 | `gender` | `int` | YES |  |  |  | 性别 |
| 9 | `age` | `int` | YES |  |  |  | 年龄 |
| 10 | `reg_no` | `varchar(50)` | YES |  |  |  | 企业注册号 |
| 11 | `display_id_no` | `varchar(50)` | YES |  |  |  | 展示用证件号码 |
| 12 | `legal_person` | `varchar(50)` | YES |  |  |  | 法定代表人或负责人 |
| 13 | `exec_court` | `varchar(50)` | YES |  |  |  | 执行法院 |
| 14 | `province_id` | `varchar(50)` | YES |  |  |  | 省份id |
| 15 | `province` | `varchar(50)` | YES |  |  |  | 省份 |
| 16 | `dishonest_type` | `int` | YES |  |  |  | 失信人类型 |
| 17 | `exec_basis_no` | `varchar(200)` | YES |  |  |  | 执行依据文号 |
| 18 | `exec_basis_org` | `varchar(50)` | YES |  |  |  | 做出执行依据单位 |
| 19 | `legal_obligation` | `text` | YES |  |  |  | 生效法律文书确定的义务 |
| 20 | `fulfillment_status` | `varchar(50)` | YES |  |  |  | 被执行人的履行情况 |
| 21 | `dishonest_behavior` | `varchar(50)` | YES |  |  |  | 失信被执行人行为具体情形 |
| 22 | `publish_date` | `varchar(50)` | YES |  |  |  | 发布时间 |
| 23 | `filing_date` | `varchar(50)` | YES |  |  |  | 立案时间 |
| 24 | `exec_part` | `varchar(50)` | YES |  |  |  | 执行部分 |
| 25 | `unexec_part` | `varchar(50)` | YES |  |  |  | 未执行部分 |
| 26 | `is_history` | `int` | YES |  |  |  | 是否历史数据 |
| 27 | `use_flag` | `int` | YES |  |  |  | 使用标记 |
| 28 | `is_hidden` | `int` | YES |  |  |  | 是否不展示 |
| 29 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 30 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 31 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_tax_punish`

表注释：前海数据机构税收违法

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `taxpayer_name` | `varchar(50)` | YES |  |  |  | 纳税人名称 |
| 2 | `tax_vio_id` | `varchar(50)` | YES |  |  |  | 税收违法id |
| 3 | `report_period` | `varchar(50)` | YES |  |  |  | 案件上报期 |
| 4 | `taxpayer_id` | `varchar(50)` | YES |  |  |  | 纳税人识别码 |
| 5 | `org_code` | `varchar(50)` | YES |  |  |  | 组织机构代码 |
| 6 | `reg_address` | `varchar(512)` | YES |  |  |  | 注册地址 |
| 7 | `publish_date` | `varchar(50)` | YES |  |  |  | 发布日期 |
| 8 | `legal_name` | `varchar(50)` | YES |  |  |  | 法定代表人或者负责人姓名 |
| 9 | `legal_gender` | `varchar(50)` | YES |  |  |  | 法定代表人或者负责人性别 |
| 10 | `legal_id_type` | `varchar(50)` | YES |  |  |  | 法定代表人或者负责人证件类型 |
| 11 | `legal_id_no` | `varchar(50)` | YES |  |  |  | 法定代表人或者负责人证件号码 |
| 12 | `case_type` | `varchar(256)` | YES |  |  |  | 案件性质 |
| 13 | `illegal_fact` | `varchar(1000)` | YES |  |  |  | 主要违法事实 |
| 14 | `punish_basis` | `varchar(1000)` | YES |  |  |  | 相关法律依据及税务处理处罚情况 |
| 15 | `tax_authority` | `varchar(50)` | YES |  |  |  | 所属税务机关 |
| 16 | `original_link` | `varchar(256)` | YES |  |  |  | 数据原始连接 |
| 17 | `use_flag` | `int` | YES |  |  |  | 使用标志 |
| 18 | `original_source` | `varchar(50)` | YES |  |  |  | 原始数据来源 |
| 19 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 20 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 21 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 22 | `is_history` | `int` | YES |  |  |  | 是否历史 |
| 23 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 24 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 25 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_xianxiao`

表注释：前海机构限制高消费记录

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `xhfgk_id` | `varchar(50)` | YES |  |  |  | 限制高消费官网id |
| 2 | `rhc_person_name` | `varchar(50)` | YES |  |  |  | 限制高消费人员名称 |
| 3 | `filing_date` | `varchar(50)` | YES |  |  |  | 立案时间 |
| 4 | `case_no` | `varchar(200)` | YES |  |  |  | 案号 |
| 5 | `gender` | `varchar(50)` | YES |  |  |  | 性别 |
| 6 | `company_info` | `varchar(50)` | YES |  |  |  | 企业信息 |
| 7 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 8 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 9 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 10 | `company_cert_no` | `varchar(50)` | YES |  |  |  | 企业证件号 |
| 11 | `xhfgk_doc_url` | `varchar(500)` | YES |  |  |  | 限制高消费令文件url |
| 12 | `use_flag` | `int` | YES |  |  |  | 使用标记 |
| 13 | `is_history` | `int` | YES |  |  |  | 是否是历史限制高消费 |
| 14 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 15 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 16 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_zhixing`

表注释：前海数据机构被执行人记录

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `exec_person_id` | `varchar(50)` | YES |  |  |  | 唯一索引id |
| 2 | `exec_person_type` | `int` | YES |  |  |  | 被执行人类型 |
| 3 | `exec_person_name` | `varchar(50)` | YES |  |  |  | 被执行人名称 |
| 4 | `gender` | `varchar(50)` | YES |  |  |  | 性别 |
| 5 | `id_no` | `varchar(50)` | YES |  |  |  | 证件号码 |
| 6 | `exec_court` | `varchar(50)` | YES |  |  |  | 执行法院 |
| 7 | `case_no` | `varchar(200)` | YES |  |  |  | 案号 |
| 8 | `exec_basis_no` | `varchar(50)` | YES |  |  |  | 执行依据文号 |
| 9 | `exec_status` | `varchar(50)` | YES |  |  |  | 执行状态 |
| 10 | `exec_target` | `varchar(50)` | YES |  |  |  | 执行标的 |
| 11 | `web_id` | `varchar(50)` | YES |  |  |  | 执行信息公开网id |
| 12 | `filing_date` | `varchar(50)` | YES |  |  |  | 立案时间 |
| 13 | `use_flag` | `int` | YES |  |  |  | 使用标记 |
| 14 | `is_hidden` | `int` | YES |  |  |  | 是否不展示 |
| 15 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 16 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 17 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 18 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 19 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 20 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_risk_zhongben`

表注释：终本案件表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `official_id` | `varchar(255)` | YES |  |  |  | 官网id |
| 2 | `executed_person_name` | `varchar(255)` | YES |  |  |  | 被执行人姓名名称 |
| 3 | `gender` | `varchar(255)` | YES |  |  |  | 性别 |
| 4 | `case_no` | `varchar(255)` | YES |  |  |  | 案号 |
| 5 | `executed_person_type` | `varchar(255)` | YES |  |  |  | 被执行人类型 |
| 6 | `id_no` | `varchar(255)` | YES |  |  |  | 证件号码 |
| 7 | `exec_court` | `varchar(255)` | YES |  |  |  | 执行法院 |
| 8 | `filing_date` | `varchar(255)` | YES |  |  |  | 立案日期 |
| 9 | `termination_date` | `varchar(255)` | YES |  |  |  | 终本日期 |
| 10 | `address` | `text` | YES |  |  |  | 地址 |
| 11 | `exec_target_amount` | `decimal(20,2)` | YES |  |  |  | 执行标的金额 |
| 12 | `unfulfilled_amount` | `decimal(20,2)` | YES |  |  |  | 未履行标的金额 |
| 13 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 14 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 15 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 16 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源zxgk |
| 17 | `data_use_flag` | `varchar(255)` | YES |  |  |  | 数据使用标记 |
| 18 | `is_history` | `varchar(255)` | YES |  |  |  | 是否是历史数据 |
| 19 | `is_hidden` | `varchar(255)` | YES |  |  |  | 是否不展示 |
| 20 | `data_source2` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 21 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 22 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_shareholder_info`

表注释：前海数据机构股东信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `inv_org_id` | `varchar(50)` | YES |  |  |  | 股东id |
| 5 | `owners_name` | `varchar(50)` | YES |  |  |  | 股东名称 |
| 6 | `owners_type` | `varchar(50)` | YES |  |  |  | 股东类型 |
| 7 | `ownership_percentage` | `double` | YES |  |  |  | 所有权占比(%) |
| 8 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 10 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_stock_base`

表注释：前海数据上市企业基本信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `stock_code` | `varchar(50)` | YES |  |  |  | 股票代码 |
| 5 | `stock_noun` | `varchar(50)` | YES |  |  |  | 股票简称 |
| 6 | `stock_type` | `varchar(50)` | YES |  |  |  | 上市板块 |
| 7 | `listed_date` | `varchar(50)` | YES |  |  |  | 上市日期 |
| 8 | `listed_status` | `varchar(50)` | YES |  |  |  | 上市状态 |
| 9 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 10 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 11 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_stock_finance_info`

表注释：前海数据上市企业主要财务指标

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `stock_code` | `varchar(50)` | YES |  |  |  | 股票代码 |
| 5 | `occur_period` | `varchar(50)` | YES |  |  |  | 数据期 |
| 6 | `total_assets` | `decimal(20,2)` | YES |  |  |  | 资产总额(元) |
| 7 | `fixed_assets` | `decimal(20,2)` | YES |  |  |  | 固定资产总额(元) |
| 8 | `total_liabilities` | `decimal(20,2)` | YES |  |  |  | 负债总额(元) |
| 9 | `operating_revenue` | `decimal(20,2)` | YES |  |  |  | 营业收入(元) |
| 10 | `gross_revenue` | `decimal(20,2)` | YES |  |  |  | 营业总收入(元) |
| 11 | `main_business_revenue` | `decimal(20,2)` | YES |  |  |  | 主营业务收入(元) |
| 12 | `total_profit` | `decimal(20,2)` | YES |  |  |  | 利润总额(元) |
| 13 | `pure_profit` | `decimal(20,2)` | YES |  |  |  | 净利润(元) |
| 14 | `total_tax_paid` | `decimal(20,2)` | YES |  |  |  | 纳税总额(元) |
| 15 | `oper_cash_flow` | `decimal(20,2)` | YES |  |  |  | 经营活动现金流(元) |
| 16 | `owners_equity` | `decimal(20,2)` | YES |  |  |  | 所有者权益合计(元) |
| 17 | `employees_number` | `int` | YES |  |  |  | 从业人数 |
| 18 | `research_development_amount` | `decimal(20,2)` | YES |  |  |  | 研发投入金额(元) |
| 19 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 20 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 21 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_tag_info`

表注释：前海数据机构标签表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `org_id` | `varchar(50)` | YES |  |  |  | 机构id |
| 2 | `name_cn` | `varchar(50)` | YES |  |  |  | 机构名称 |
| 3 | `social_credit_code` | `varchar(50)` | YES |  |  |  | 统一社会信用代码 |
| 4 | `org_tag` | `varchar(50)` | YES |  |  |  | 企业标签 |
| 5 | `tag_level` | `varchar(50)` | YES |  |  |  | 级别 |
| 6 | `data_source` | `varchar(50)` | YES |  |  |  | 数据来源 |
| 7 | `created_time` | `varchar(50)` | YES |  |  |  | 创建时间 |
| 8 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |

## `dwd_org_tb_judicial_sale`

表注释：司法拍卖表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `notice_name` | `text` | YES |  |  |  | 公告名 |
| 2 | `asset_disposal_unit` | `varchar(255)` | YES |  |  |  | 资产处置单位 |
| 3 | `notice_time` | `varchar(255)` | YES |  |  |  | 公告时间 |
| 4 | `notice_id` | `varchar(255)` | YES |  |  |  | 公告id |
| 5 | `source_website` | `varchar(255)` | YES |  |  |  | 来源网站 |
| 6 | `notice_content_path` | `text` | YES |  |  |  | 公告内容存储路径 |
| 7 | `auction_start_date` | `varchar(255)` | YES |  |  |  | 拍卖开始日期 |
| 8 | `auction_end_date` | `varchar(255)` | YES |  |  |  | 拍卖截止日期 |
| 9 | `original_link` | `text` | YES |  |  |  | 原始链接 |
| 10 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标志 |
| 11 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 12 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 13 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |

## `dwd_org_tb_judicial_sale_info_company`

表注释：司法拍卖当事人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `notice_id` | `varchar(255)` | YES |  |  |  | 公告id |
| 2 | `related_company` | `varchar(255)` | YES |  |  |  | 相关公司 |
| 3 | `org_id` | `varchar(255)` | YES |  |  |  | 机构id |
| 4 | `name_cn` | `varchar(255)` | YES |  |  |  | 机构名称 |
| 5 | `social_credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 6 | `use_flag` | `varchar(255)` | YES |  |  |  | 使用标记 |
| 7 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 8 | `created_time` | `datetime` | YES |  |  |  | 创建时间 |
| 9 | `updated_time` | `datetime` | YES |  |  |  | 更新时间 |
