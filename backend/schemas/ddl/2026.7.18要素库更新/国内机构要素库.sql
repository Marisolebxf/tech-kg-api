-- 国内机构要素库建表 SQL
-- 来源文件：国内机构要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 机构基本信息：dwd_org_base_info
CREATE TABLE IF NOT EXISTS `dwd_org_base_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `province` VARCHAR(255) NULL COMMENT '所在省份/varchar(255) ',
  `city` VARCHAR(255) NULL COMMENT '所在城市/varchar(255) ',
  `area` VARCHAR(255) NULL COMMENT '所在区县/varchar(255) ',
  `address` TEXT NULL COMMENT '公司地址/text ',
  `addr_lng` VARCHAR(255) NULL COMMENT '地址对应经度/varchar(255) ',
  `addr_lat` VARCHAR(255) NULL COMMENT '地址对应维度/varchar(255) ',
  `postal_code` VARCHAR(255) NULL COMMENT '邮政编码/varchar(255) ',
  `email` TEXT NULL COMMENT '电子邮箱/text ',
  `lerep` VARCHAR(255) NULL COMMENT '法定代表人/varchar(255) ',
  `reg_status` VARCHAR(255) NULL COMMENT '登记状态/varchar(255) ',
  `registration_org` VARCHAR(255) NULL COMMENT '登记机关/varchar(255) ',
  `incorporation_year` DECIMAL(20,0) NULL COMMENT '成立年份/decimal(20,0) ',
  `incorporation_date` DATETIME NULL COMMENT '成立日期/datetime ',
  `start_date` VARCHAR(255) NULL COMMENT '经营期限自/varchar(255) ',
  `end_date` VARCHAR(255) NULL COMMENT '经营期限至/varchar(255) ',
  `org_type` VARCHAR(255) NULL COMMENT '机构类型/varchar(255) ',
  `listing_status` VARCHAR(255) NULL COMMENT '上市状态/varchar(255) ',
  `listing_date` DATETIME NULL COMMENT '上市日期/datetime ',
  `registered_capital_value` DECIMAL(20,2) NULL COMMENT '注册资本(本币元)/decimal(20,2) ',
  `capital_currency` VARCHAR(255) NULL COMMENT '币种/varchar(255) ',
  `industry` VARCHAR(255) NULL COMMENT '最深一级的行业名称/varchar(255) ',
  `industry_l1_name` VARCHAR(255) NULL COMMENT '一级行业名称/varchar(255) ',
  `industry_l1_code` VARCHAR(255) NULL COMMENT '一级行业编码/varchar(255) ',
  `industry_l2_name` VARCHAR(255) NULL COMMENT '二级行业名称/varchar(255) ',
  `industry_l2_code` VARCHAR(255) NULL COMMENT '二级行业编码/varchar(255) ',
  `industry_l3_name` VARCHAR(255) NULL COMMENT '三级行业名称/varchar(255) ',
  `industry_l3_code` VARCHAR(255) NULL COMMENT '三级行业编码/varchar(255) ',
  `industry_l4_name` VARCHAR(255) NULL COMMENT '四级行业名称/varchar(255) ',
  `industry_l4_code` VARCHAR(255) NULL COMMENT '四级行业编码/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='机构基本信息';

-- 股东信息：dwd_org_shareholder_info
CREATE TABLE IF NOT EXISTS `dwd_org_shareholder_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `inv_org_id` VARCHAR(255) NULL COMMENT '股东id/varchar(255) ',
  `owners_name` VARCHAR(255) NOT NULL COMMENT '股东名称/varchar(255) ',
  `owners_type` VARCHAR(255) NULL COMMENT '股东类型/varchar(255) ',
  `ownership_percentage` DECIMAL(20,2) NULL COMMENT '所有权占比(%)/decimal(20,2) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_inv_org_id` (`inv_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='股东信息';

-- 高管信息：dwd_org_executive_info
CREATE TABLE IF NOT EXISTS `dwd_org_executive_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `executives_name` VARCHAR(255) NOT NULL COMMENT '高管姓名/varchar(255) ',
  `executives_position` VARCHAR(255) NULL COMMENT '职位名称/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='高管信息';

-- 经营信息：dwd_org_org_product_info
CREATE TABLE IF NOT EXISTS `dwd_org_org_product_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `main_activities` TEXT NULL COMMENT '公司经营范围/text ',
  `description` TEXT NULL COMMENT '业务描述/text ',
  `main_prod` VARCHAR(255) NULL COMMENT '主要产品/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营信息';

-- 年报财务信息：dwd_org_annual_financial_info
CREATE TABLE IF NOT EXISTS `dwd_org_annual_financial_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `year` DECIMAL(20,0) NOT NULL COMMENT '年报年度/decimal(20,0) ',
  `total_assets` DECIMAL(20,2) NULL COMMENT '资产总额/decimal(20,2) ',
  `total_liabilities` DECIMAL(20,2) NULL COMMENT '负债总额/decimal(20,2) ',
  `operating_revenue` DECIMAL(20,2) NULL COMMENT '营业收入/decimal(20,2) ',
  `main_business_revenue` DECIMAL(20,2) NULL COMMENT '主营业务收入/decimal(20,2) ',
  `total_profit` DECIMAL(20,2) NULL COMMENT '利润总额/decimal(20,2) ',
  `pure_profit` DECIMAL(20,2) NULL COMMENT '净利润/decimal(20,2) ',
  `total_tax_paid` DECIMAL(20,2) NULL COMMENT '纳税总额/decimal(20,2) ',
  `owners_equity` DECIMAL(20,2) NULL COMMENT '所有者权益合计/decimal(20,2) ',
  `employees_number` DECIMAL(20,0) NULL COMMENT '从业人数/decimal(20,0) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='年报财务信息';

-- 重点资讯：dwd_org_important_news_info
CREATE TABLE IF NOT EXISTS `dwd_org_important_news_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `news_title` TEXT NOT NULL COMMENT '资讯标题/text ',
  `news_date` DATETIME NOT NULL COMMENT '资讯日期/datetime ',
  `news_content` TEXT NULL COMMENT '资讯内容/text ',
  `original_textlink` TEXT NULL COMMENT '咨询原文链接/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_news_date` (`news_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='重点资讯';

-- 工商变更信息：dwd_org_changerecord_info
CREATE TABLE IF NOT EXISTS `dwd_org_changerecord_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `update_content` VARCHAR(255) NULL COMMENT '变更类型/varchar(255) ',
  `current_name` TEXT NULL COMMENT '变更前内容/text ',
  `update_name` TEXT NULL COMMENT '变更后内容/text ',
  `update_date` DATETIME NULL COMMENT '变更日期/datetime ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_update_date` (`update_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='工商变更信息';

-- 并购事件：dwd_org_merger_acquisition_info
CREATE TABLE IF NOT EXISTS `dwd_org_merger_acquisition_info` (
  `acquiring_org_id` VARCHAR(255) NOT NULL COMMENT '发起收购企业id/varchar(255) ',
  `acquiring_name` VARCHAR(255) NOT NULL COMMENT '发起收购企业名称/varchar(255) ',
  `acquiring_external_id` VARCHAR(255) NULL COMMENT '发起收购企业统一社会信用代码/varchar(255) ',
  `acquired_org_id` VARCHAR(255) NOT NULL COMMENT '被收购企业id/varchar(255) ',
  `acquired_name` VARCHAR(255) NOT NULL COMMENT '被收购企业名称/varchar(255) ',
  `acquired_external_id` VARCHAR(255) NULL COMMENT '被收购企业统一社会信用代码/varchar(255) ',
  `ma_amount` DECIMAL(20,2) NULL COMMENT '并购金额(元)/decimal(20,2) ',
  `currency_code` VARCHAR(255) NULL COMMENT '并购金额币种/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_acquiring_org_id` (`acquiring_org_id`),
  KEY `idx_acquiring_external_id` (`acquiring_external_id`),
  KEY `idx_acquired_org_id` (`acquired_org_id`),
  KEY `idx_acquired_external_id` (`acquired_external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='并购事件';

-- 融资事件：dwd_org_financing_info
CREATE TABLE IF NOT EXISTS `dwd_org_financing_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `funding_round` VARCHAR(255) NULL COMMENT '融资轮次/varchar(255) ',
  `funding_amount` DECIMAL(20,2) NULL COMMENT '获投金额(元)/decimal(20,2) ',
  `funding_currency_code` VARCHAR(255) NULL COMMENT '金额币种/varchar(255) ',
  `completion_date` DATETIME NULL COMMENT '融资完成时间/datetime ',
  `investors_name` TEXT NOT NULL COMMENT '投资方列表/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='融资事件';

-- 投资事件：dwd_org_invest_info
CREATE TABLE IF NOT EXISTS `dwd_org_invest_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `inv_org_id` VARCHAR(255) NOT NULL COMMENT '被投企业id/varchar(255) ',
  `inv_name` VARCHAR(255) NOT NULL COMMENT '被投资企业名称/varchar(255) ',
  `inv_external_id` VARCHAR(255) NULL COMMENT '被投资企业统一社会信用代码/varchar(255) ',
  `investment_amount` DECIMAL(20,2) NULL COMMENT '投资金额(元)/decimal(20,2) ',
  `investment_ratio` DECIMAL(20,2) NULL COMMENT '股权占比(%)/decimal(20,2) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_inv_org_id` (`inv_org_id`),
  KEY `idx_inv_external_id` (`inv_external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='投资事件';

-- 招聘信息：dwd_org_recruit_info
CREATE TABLE IF NOT EXISTS `dwd_org_recruit_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `job_title` VARCHAR(255) NULL COMMENT '岗位/varchar(255) ',
  `job_description` TEXT NULL COMMENT '工作描述/text ',
  `work_place` TEXT NULL COMMENT '工作地点/text ',
  `release_date` DATETIME NULL COMMENT '发布日期/datetime ',
  `hiring_number` VARCHAR(255) NULL COMMENT '招聘人数/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招聘信息';

-- 高校基本信息：dwd_org_heis_info
CREATE TABLE IF NOT EXISTS `dwd_org_heis_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '学校名称/varchar(255) ',
  `school_code` VARCHAR(255) NOT NULL COMMENT '学校标识码/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `name_en` VARCHAR(255) NULL COMMENT '学校英文名称/varchar(255) ',
  `est_year` DECIMAL(20,0) NULL COMMENT '建立时间/decimal(20,0) ',
  `address` TEXT NULL COMMENT '学校地址/text ',
  `addr_lng` VARCHAR(255) NULL COMMENT '地址对应经度/varchar(255) ',
  `addr_lat` VARCHAR(255) NULL COMMENT '地址对应维度/varchar(255) ',
  `province` VARCHAR(255) NULL COMMENT '地址所在省/varchar(255) ',
  `city` VARCHAR(255) NULL COMMENT '地址所在市/varchar(255) ',
  `area` VARCHAR(255) NULL COMMENT '地址所在区/varchar(255) ',
  `univ_type` VARCHAR(255) NULL COMMENT '学校类型/varchar(255) ',
  `web_link` TEXT NULL COMMENT '官方网址/text ',
  `comp_dept` VARCHAR(255) NULL COMMENT '主管部门/varchar(255) ',
  `school_nature` VARCHAR(255) NULL COMMENT '办学层次/varchar(255) ',
  `postal_code` VARCHAR(255) NULL COMMENT '邮政编码/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_school_code` (`school_code`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_name_en` (`name_en`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='高校基本信息';

-- 上市企业基本信息：dwd_org_stock_base
CREATE TABLE IF NOT EXISTS `dwd_org_stock_base` (
  `stock_code` VARCHAR(255) NOT NULL COMMENT '股票代码/varchar(255) ',
  `stock_noun` VARCHAR(255) NULL COMMENT '股票简称/varchar(255) ',
  `stock_type` VARCHAR(255) NOT NULL COMMENT '上市板块/varchar(255) ',
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `listed_date` DATETIME NULL COMMENT '上市日期/datetime ',
  `listed_status` VARCHAR(255) NOT NULL COMMENT '上市状态/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业基本信息';

-- 上市企业主要财务指标：dwd_org_stock_finance_info
CREATE TABLE IF NOT EXISTS `dwd_org_stock_finance_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `stock_code` VARCHAR(255) NOT NULL COMMENT '股票代码/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `occur_period` VARCHAR(255) NOT NULL COMMENT '数据期/varchar(255) ',
  `total_assets` DECIMAL(20,2) NULL COMMENT '资产总额(元)/decimal(20,2) ',
  `fixed_assets` DECIMAL(20,2) NULL COMMENT '固定资产总额(元)/decimal(20,2) ',
  `total_liabilities` DECIMAL(20,2) NULL COMMENT '负债总额(元)/decimal(20,2) ',
  `operating_revenue` DECIMAL(20,2) NULL COMMENT '营业收入(元)/decimal(20,2) ',
  `main_business_revenue` DECIMAL(20,2) NULL COMMENT '主营业务收入(元)/decimal(20,2) ',
  `total_profit` DECIMAL(20,2) NULL COMMENT '利润总额(元)/decimal(20,2) ',
  `pure_profit` DECIMAL(20,2) NULL COMMENT '净利润(元)/decimal(20,2) ',
  `total_tax_paid` DECIMAL(20,2) NULL COMMENT '纳税总额(元)/decimal(20,2) ',
  `oper_cash_flow` DECIMAL(20,2) NULL COMMENT '经营活动现金流(元)/decimal(20,2) ',
  `owners_equity` DECIMAL(20,2) NULL COMMENT '所有者权益合计(元)/decimal(20,2) ',
  `employees_number` DECIMAL(20,0) NULL COMMENT '从业人数/decimal(20,0) ',
  `research_development_amount` DECIMAL(20,2) NULL COMMENT '研发投入金额(元)/decimal(20,2) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_occur_period` (`occur_period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业主要财务指标';

-- 经营异常：dwd_org_company_abnormal
CREATE TABLE IF NOT EXISTS `dwd_org_company_abnormal` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `abnormal_id` VARCHAR(255) NOT NULL COMMENT '经营异常记录id/varchar(255) ',
  `abn_reason` TEXT NULL COMMENT '列入原因/text ',
  `abn_date` DATETIME NULL COMMENT '列入时间/datetime ',
  `abn_org` VARCHAR(255) NULL COMMENT '列入机关/varchar(255) ',
  `remove_reason` TEXT NULL COMMENT '移除原因/text ',
  `remove_date` DATETIME NULL COMMENT '移除时间/datetime ',
  `remove_org` VARCHAR(255) NULL COMMENT '移除机关/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_abnormal_id` (`abnormal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营异常';

-- 行政处罚：dwd_org_company_punish
CREATE TABLE IF NOT EXISTS `dwd_org_company_punish` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `penalty_id` VARCHAR(255) NOT NULL COMMENT '行政处罚记录id/varchar(255) ',
  `decision_no` VARCHAR(255) NULL COMMENT '决定书文号/varchar(255) ',
  `violation_type` TEXT NULL COMMENT '违法行为类型/text ',
  `penalty_content` TEXT NULL COMMENT '行政处罚内容/text ',
  `decision_org` VARCHAR(255) NULL COMMENT '决定机关/varchar(255) ',
  `penalty_date` DATETIME NULL COMMENT '处罚决定日期/datetime ',
  `public_date` DATETIME NULL COMMENT '公示日期/datetime ',
  `penalty_basis` TEXT NULL COMMENT '处罚依据/text ',
  `violation_fact` TEXT NULL COMMENT '主要违法事实/text ',
  `penalty_type` VARCHAR(255) NULL COMMENT '处罚种类/varchar(255) ',
  `fine_amount` VARCHAR(255) NULL COMMENT '罚款金额/varchar(255) ',
  `confiscate_amount` VARCHAR(255) NULL COMMENT '没收金额/varchar(255) ',
  `license_info` VARCHAR(255) NULL COMMENT '暂扣或吊销证照名称及编号/varchar(255) ',
  `validity_period` VARCHAR(255) NULL COMMENT '处罚有效期/varchar(255) ',
  `public_deadline` DATETIME NULL COMMENT '公示截止日期/datetime ',
  `mark` VARCHAR(255) NULL COMMENT '备注/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_penalty_id` (`penalty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='行政处罚';

-- 严重违法：dwd_org_company_illegal
CREATE TABLE IF NOT EXISTS `dwd_org_company_illegal` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `sv_id` VARCHAR(255) NOT NULL COMMENT '严重违法记录id/varchar(255) ',
  `category` VARCHAR(255) NULL COMMENT '类别/varchar(255) ',
  `abn_reason` TEXT NULL COMMENT '列入原因/text ',
  `abn_date` DATETIME NULL COMMENT '列入时间/datetime ',
  `abn_org` VARCHAR(255) NULL COMMENT '列入机关/varchar(255) ',
  `remove_reason` TEXT NULL COMMENT '移除原因/text ',
  `remove_date` DATETIME NULL COMMENT '移除时间/datetime ',
  `remove_org` VARCHAR(255) NULL COMMENT '移除机关/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_sv_id` (`sv_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='严重违法';

-- 税收违法：dwd_org_risk_tax_punish
CREATE TABLE IF NOT EXISTS `dwd_org_risk_tax_punish` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `taxpayer_name` VARCHAR(255) NOT NULL COMMENT '纳税人名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `tax_vio_id` VARCHAR(255) NOT NULL COMMENT '唯一索引id/varchar(255) ',
  `report_period` VARCHAR(255) NULL COMMENT '案件上报期/varchar(255) ',
  `taxpayer_id` VARCHAR(255) NULL COMMENT '纳税人识别码/varchar(255) ',
  `org_code` VARCHAR(255) NULL COMMENT '组织机构代码/varchar(255) ',
  `reg_address` TEXT NULL COMMENT '注册地址/text ',
  `publish_date` DATETIME NULL COMMENT '发布日期/datetime ',
  `legal_name` VARCHAR(255) NULL COMMENT '法定代表人或者负责人姓名/varchar(255) ',
  `legal_gender` VARCHAR(255) NULL COMMENT '法定代表人或者负责人性别/varchar(255) ',
  `legal_id_type` VARCHAR(255) NULL COMMENT '法定代表人或者负责人证件类型/varchar(255) ',
  `legal_id_no` VARCHAR(255) NULL COMMENT '法定代表人或者负责人证件号码/varchar(255) ',
  `finance_name` VARCHAR(255) NULL COMMENT '负有直接责任的财务负责人姓名/varchar(255) ',
  `finance_gender` VARCHAR(255) NULL COMMENT '负有直接责任的财务负责人性别/varchar(255) ',
  `finance_id_type` VARCHAR(255) NULL COMMENT '负有直接责任的财务负责人证件类型/varchar(255) ',
  `finance_id_no` VARCHAR(255) NULL COMMENT '负有直接责任的财务负责人证件号码/varchar(255) ',
  `agency_info` VARCHAR(255) NULL COMMENT '负有直接责任的中介机构信息及其从业人员信息/varchar(255) ',
  `case_type` VARCHAR(255) NULL COMMENT '案件性质/varchar(255) ',
  `illegal_fact` TEXT NULL COMMENT '主要违法事实/text ',
  `punish_basis` TEXT NULL COMMENT '相关法律依据及税务处理处罚情况/text ',
  `tax_authority` VARCHAR(255) NULL COMMENT '所属税务机关/varchar(255) ',
  `original_link` TEXT NULL COMMENT '数据原始链接/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_tax_vio_id` (`tax_vio_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='税收违法';

-- 司法案件信息：dwd_org_opt_judicial_case
CREATE TABLE IF NOT EXISTS `dwd_org_opt_judicial_case` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `company_name` VARCHAR(255) NOT NULL COMMENT '企业名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `case_id` VARCHAR(255) NOT NULL COMMENT '司法案件唯一标识/varchar(255) ',
  `reg_no` VARCHAR(255) NULL COMMENT '注册号/varchar(255) ',
  `case_title` TEXT NULL COMMENT '案件标题/text ',
  `case_type_tag` VARCHAR(255) NULL COMMENT '案件类型标签/varchar(255) ',
  `case_no` TEXT NULL COMMENT '案号/text ',
  `case_cause` TEXT NULL COMMENT '案由/text ',
  `case_role` TEXT NULL COMMENT '案件身份/text ',
  `current_procedure` VARCHAR(255) NULL COMMENT '当前审理程序/varchar(255) ',
  `procedure_date` DATETIME NULL COMMENT '当前审理程序日期/datetime ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='司法案件信息';

-- 失信被执行人：dwd_org_risk_shixin
CREATE TABLE IF NOT EXISTS `dwd_org_risk_shixin` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` TEXT NOT NULL COMMENT '失信人名称/text ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `dishonest_id` VARCHAR(255) NOT NULL COMMENT '失信被执行人id/varchar(255) ',
  `official_id` VARCHAR(255) NULL COMMENT '官网id/varchar(255) ',
  `case_no` VARCHAR(255) NULL COMMENT '案号/varchar(255) ',
  `gender` VARCHAR(255) NULL COMMENT '性别/varchar(255) ',
  `age` VARCHAR(255) NULL COMMENT '年龄/varchar(255) ',
  `reg_no` VARCHAR(255) NULL COMMENT '企业注册号/varchar(255) ',
  `display_id_no` VARCHAR(255) NULL COMMENT '展示用证件号码/varchar(255) ',
  `legal_person` VARCHAR(255) NULL COMMENT '法定代表人或负责人/varchar(255) ',
  `exec_court` VARCHAR(255) NULL COMMENT '执行法院/varchar(255) ',
  `province` VARCHAR(255) NULL COMMENT '省份/varchar(255) ',
  `dishonest_type` DECIMAL(20,0) NULL COMMENT '失信人类型/decimal(20,0) ',
  `exec_basis_no` TEXT NULL COMMENT '执行依据文号/text ',
  `exec_basis_org` VARCHAR(255) NULL COMMENT '做出执行依据单位/varchar(255) ',
  `legal_obligation` TEXT NULL COMMENT '生效法律文书确定的义务/text ',
  `fulfillment_status` TEXT NULL COMMENT '被执行人的履行情况/text ',
  `dishonest_behavior` TEXT NULL COMMENT '失信被执行人行为具体情形/text ',
  `publish_date` DATETIME NULL COMMENT '发布时间/datetime ',
  `filing_date` DATETIME NULL COMMENT '立案时间/datetime ',
  `exec_part` TEXT NULL COMMENT '执行部分/text ',
  `unexec_part` TEXT NULL COMMENT '未执行部分/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_dishonest_id` (`dishonest_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='失信被执行人';

-- 被执行人：dwd_org_risk_zhixing
CREATE TABLE IF NOT EXISTS `dwd_org_risk_zhixing` (
  `exec_person_id` VARCHAR(255) NOT NULL COMMENT '唯一索引id/varchar(255) ',
  `exec_person_type` DECIMAL(20,0) NULL COMMENT '被执行人类型/decimal(20,0) ',
  `exec_person_name` VARCHAR(255) NOT NULL COMMENT '被执行人名称/varchar(255) ',
  `gender` VARCHAR(255) NULL COMMENT '性别/varchar(255) ',
  `id_no` VARCHAR(255) NULL COMMENT '证件号码/varchar(255) ',
  `exec_court` VARCHAR(255) NULL COMMENT '执行法院/varchar(255) ',
  `case_no` VARCHAR(255) NULL COMMENT '案号/varchar(255) ',
  `exec_basis_no` VARCHAR(255) NULL COMMENT '执行依据文号/varchar(255) ',
  `exec_status` VARCHAR(255) NULL COMMENT '执行状态/varchar(255) ',
  `exec_target` VARCHAR(255) NULL COMMENT '执行标的/varchar(255) ',
  `web_id` VARCHAR(255) NULL COMMENT '执行信息公开网id/varchar(255) ',
  `filing_date` DATETIME NULL COMMENT '立案时间/datetime ',
  `is_hidden` DECIMAL(20,0) NULL COMMENT '是否不展示/decimal(20,0) ',
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_exec_person_id` (`exec_person_id`),
  KEY `idx_exec_basis_no` (`exec_basis_no`),
  KEY `idx_web_id` (`web_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='被执行人';

-- 破产案件：dwd_org_bankruptcy_public_cases
CREATE TABLE IF NOT EXISTS `dwd_org_bankruptcy_public_cases` (
  `case_no` VARCHAR(255) NOT NULL COMMENT '案号/varchar(255) ',
  `case_type` VARCHAR(255) NULL COMMENT '案件类型/varchar(255) ',
  `handling_court` VARCHAR(255) NULL COMMENT '经办法院/varchar(255) ',
  `applicant_info` TEXT NULL COMMENT '申请人信息/text ',
  `respondent_info` TEXT NULL COMMENT '被申请人信息/text ',
  `admin_org` VARCHAR(255) NULL COMMENT '管理人机构/varchar(255) ',
  `admin_org_id` VARCHAR(255) NOT NULL COMMENT '管理人机构id/varchar(255) ',
  `admin_principal` VARCHAR(255) NULL COMMENT '管理人主要负责人/varchar(255) ',
  `public_date` DATETIME NULL COMMENT '公开时间/datetime ',
  `link` TEXT NULL COMMENT '链接/text ',
  `history_status` VARCHAR(255) NULL COMMENT '历史状态/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_admin_org_id` (`admin_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='破产案件';

-- 破产案件当事人：dwd_org_bankruptcy_public_cases_list
CREATE TABLE IF NOT EXISTS `dwd_org_bankruptcy_public_cases_list` (
  `bankruptcy_party_id` VARCHAR(255) NOT NULL COMMENT '唯一索引id/varchar(255) ',
  `case_no` VARCHAR(255) NULL COMMENT '案号/varchar(255) ',
  `related_person_name` VARCHAR(255) NULL COMMENT '相关人名称/varchar(255) ',
  `party_role_type` DECIMAL(20,0) NULL COMMENT '当事人角色类型/decimal(20,0) ',
  `party_type` DECIMAL(20,0) NULL COMMENT '当事人类型/decimal(20,0) ',
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `public_date` DATETIME NULL COMMENT '公开时间/datetime ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_bankruptcy_party_id` (`bankruptcy_party_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='破产案件当事人';

-- 香港企业：dwd_special_hongkong_company
CREATE TABLE IF NOT EXISTS `dwd_special_hongkong_company` (
  `province_en` VARCHAR(255) NULL COMMENT '省份(英文缩写)/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `name_en` VARCHAR(255) NULL COMMENT '机构英文名称/varchar(255) ',
  `traditional_name` VARCHAR(255) NOT NULL COMMENT '机构繁体名称/varchar(255) ',
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `company_code` VARCHAR(255) NULL COMMENT '机构编号/varchar(255) ',
  `company_type` VARCHAR(255) NULL COMMENT '机构类别/varchar(255) ',
  `incorporation_date` DATETIME NULL COMMENT '成立日期/datetime ',
  `company_status` VARCHAR(255) NULL COMMENT '机构现况/varchar(255) ',
  `remark` VARCHAR(255) NULL COMMENT '备注/varchar(255) ',
  `liquidation_mode` VARCHAR(255) NULL COMMENT '清盘模式/varchar(255) ',
  `cancel_date` DATETIME NULL COMMENT '解散日期/datetime ',
  `mortgage` VARCHAR(255) NULL COMMENT '押记登记册/varchar(255) ',
  `imp_matters` VARCHAR(255) NULL COMMENT '重要事项/varchar(255) ',
  `create_time` DATETIME NOT NULL COMMENT '入库时间/datetime ',
  `br_code` VARCHAR(255) NULL COMMENT '商业登记代码/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_name_en` (`name_en`),
  KEY `idx_traditional_name` (`traditional_name`),
  KEY `idx_org_id` (`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='香港企业';

-- 台湾企业：dwd_special_taiwan_company
CREATE TABLE IF NOT EXISTS `dwd_special_taiwan_company` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `company_name` VARCHAR(255) NULL COMMENT '原始机构名称/varchar(255) ',
  `n_company_name` VARCHAR(255) NULL COMMENT '标准机构名称/varchar(255) ',
  `company_code` VARCHAR(255) NULL COMMENT '统一编号/varchar(255) ',
  `history_company_code` VARCHAR(255) NULL COMMENT '历史统一编号/varchar(255) ',
  `company_status` VARCHAR(255) NULL COMMENT '登记状态/varchar(255) ',
  `company_type` VARCHAR(255) NULL COMMENT '类型/varchar(255) ',
  `name_en` VARCHAR(255) NULL COMMENT '机构英文名称/varchar(255) ',
  `capital` VARCHAR(255) NULL COMMENT '资本总额/varchar(255) ',
  `capital_num` DECIMAL(20,6) NULL COMMENT '资本总额_值(万)/decimal(20,6) ',
  `currency` VARCHAR(255) NULL COMMENT '资本总额_币种/varchar(255) ',
  `real_capital` VARCHAR(255) NULL COMMENT '实缴资本额/varchar(255) ',
  `realcapital_num` DECIMAL(20,6) NULL COMMENT '实缴资本额_值(万)/decimal(20,6) ',
  `realcapital_currency` VARCHAR(255) NULL COMMENT '实收资本额_币种/varchar(255) ',
  `amount_per_share` DECIMAL(20,6) NULL COMMENT '每股金额/decimal(20,6) ',
  `total_shares` VARCHAR(255) NULL COMMENT '已发行股份总数/varchar(255) ',
  `legal_person` VARCHAR(255) NULL COMMENT '代表人姓名/varchar(255) ',
  `company_address` VARCHAR(255) NULL COMMENT '机构所在地/varchar(255) ',
  `registration_org` VARCHAR(255) NULL COMMENT '登记机关/varchar(255) ',
  `incorporation_date` DATETIME NULL COMMENT '成立日期/datetime ',
  `issue_date` DATETIME NULL COMMENT '核准日期/datetime ',
  `plural_voting_shares` VARCHAR(255) NULL COMMENT '是否具有复数表决权特别股/varchar(255) ',
  `matters_veto_shares` VARCHAR(255) NULL COMMENT '是否具有对于特定事项具否决权特别股/varchar(255) ',
  `special_holder_rights` VARCHAR(255) NULL COMMENT '特别股股东被选为董事、监察人的禁止或限制或当选一定名额的权利情况/varchar(255) ',
  `business_scope` TEXT NULL COMMENT '经营范围/text ',
  `history_name` VARCHAR(255) NULL COMMENT '历史名称/varchar(255) ',
  `equity_status` VARCHAR(255) NULL COMMENT '股权状况/varchar(255) ',
  `company_quality` VARCHAR(255) NULL COMMENT '机构属性/varchar(255) ',
  `closure_date_begin` DATETIME NULL COMMENT '停业日期(起)/datetime ',
  `closure_date_end` DATETIME NULL COMMENT '停业日期(迄)/datetime ',
  `closure_authority` VARCHAR(255) NULL COMMENT '停业核准(备)机关/varchar(255) ',
  `is_history` VARCHAR(255) NULL COMMENT '是否历史数据/varchar(255) ',
  `create_time` DATETIME NOT NULL COMMENT '入库时间/datetime ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_company_name` (`company_name`),
  KEY `idx_n_company_name` (`n_company_name`),
  KEY `idx_company_code` (`company_code`),
  KEY `idx_history_company_code` (`history_company_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='台湾企业';

-- 澳门企业：dwd_special_aomen_company
CREATE TABLE IF NOT EXISTS `dwd_special_aomen_company` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `org_loc_name` VARCHAR(255) NOT NULL COMMENT '机构本地名称/varchar(255) ',
  `en_name` VARCHAR(255) NULL COMMENT '机构英文名称/varchar(255) ',
  `incorporation_year` DECIMAL(20,0) NULL COMMENT '成立年份/decimal(20,0) ',
  `incorporation_date` DATETIME NULL COMMENT '成立日期/datetime ',
  `country_code` VARCHAR(255) NULL COMMENT '注册国家代码/varchar(255) ',
  `city` VARCHAR(255) NULL COMMENT '注册城市/varchar(255) ',
  `listing_status` VARCHAR(255) NULL COMMENT '上市状态/varchar(255) ',
  `owners_type` VARCHAR(255) NULL COMMENT '机构经济类型/varchar(255) ',
  `person_num` DECIMAL(20,0) NULL COMMENT '员工人数/decimal(20,0) ',
  `company_code` VARCHAR(255) NULL COMMENT '统一编号/varchar(255) ',
  `company_status` VARCHAR(255) NULL COMMENT '登记状态/varchar(255) ',
  `capital` VARCHAR(255) NULL COMMENT '注册资本/varchar(255) ',
  `currency_code` VARCHAR(255) NULL COMMENT '注册资本币种/varchar(255) ',
  `company_est_status` VARCHAR(255) NULL COMMENT '机构运营状态代码/varchar(255) ',
  `address` VARCHAR(255) NULL COMMENT '地址/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_org_loc_name` (`org_loc_name`),
  KEY `idx_en_name` (`en_name`),
  KEY `idx_company_code` (`company_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='澳门企业';

-- 招投标公告基础表：dwd_bid_base_out
CREATE TABLE IF NOT EXISTS `dwd_bid_base_out` (
  `u_id` VARCHAR(255) NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `publish_time` DATETIME NULL COMMENT '发布时间/datetime ',
  `title` VARCHAR(255) NULL COMMENT '标题/varchar(255) ',
  `project_number` TEXT NULL COMMENT '项目编号/text ',
  `plan_number` TEXT NULL COMMENT '计划编号/text ',
  `project_name` TEXT NULL COMMENT '项目名称/text ',
  `announcement_type` VARCHAR(255) NULL COMMENT '公告类型/varchar(255) ',
  `announcement_type_code` DECIMAL(20,0) NULL COMMENT '公告类型编号/decimal(20,0) ',
  `industry_type` VARCHAR(255) NULL COMMENT '行业分类/varchar(255) ',
  `procurement_method` VARCHAR(255) NULL COMMENT '采购方式/varchar(255) ',
  `procurement_method_code` DECIMAL(20,0) NULL COMMENT '采购方式编号/decimal(20,0) ',
  `bidding_stage` VARCHAR(255) NULL COMMENT '招投标阶段/varchar(255) ',
  `target_item_type` VARCHAR(255) NULL COMMENT '标的物类型/varchar(255) ',
  `bidding_stage_code` DECIMAL(20,0) NULL COMMENT '招投标阶段编码/decimal(20,0) ',
  `project_region_province` VARCHAR(255) NULL COMMENT '项目区域-省/varchar(255) ',
  `project_region_province_code` VARCHAR(255) NULL COMMENT '项目区域-省-编码/varchar(255) ',
  `project_region_city` VARCHAR(255) NULL COMMENT '项目区域-市/varchar(255) ',
  `project_region_city_code` VARCHAR(255) NULL COMMENT '项目区域-市-编码/varchar(255) ',
  `project_region_district` VARCHAR(255) NULL COMMENT '项目区域-区县/varchar(255) ',
  `project_region_district_code` VARCHAR(255) NULL COMMENT '项目区域-区县-编码/varchar(255) ',
  `project_budget_amount` DECIMAL(20,6) NULL COMMENT '项目预算金额/decimal(20,6) ',
  `project_budget_amount_unit` VARCHAR(255) NULL COMMENT '项目预算金额单位/varchar(255) ',
  `total_amount` DECIMAL(20,6) NULL COMMENT '中标总金额/decimal(20,6) ',
  `total_amount_unit` VARCHAR(255) NULL COMMENT '中标总金额单位/varchar(255) ',
  `bid_document_start_time` DATETIME NULL COMMENT '标书获取开始时间/datetime ',
  `bid_document_end_time` DATETIME NULL COMMENT '标书获取截止时间/datetime ',
  `registration_start_time` DATETIME NULL COMMENT '报名开始时间/datetime ',
  `registration_end_time` DATETIME NULL COMMENT '报名截止时间/datetime ',
  `bidding_start_time` DATETIME NULL COMMENT '投标开始时间/datetime ',
  `bidding_end_time` DATETIME NULL COMMENT '投标结束时间/datetime ',
  `opening_bid_time` DATETIME NULL COMMENT '开标时间/datetime ',
  `estimated_purchasing_time` DATETIME NULL COMMENT '预计采购时间/datetime ',
  `contract_num` TEXT NULL COMMENT '合同编号/text ',
  `quotation_validity_start` DATETIME NULL COMMENT '报价有效期-起/datetime ',
  `quotation_validity_end` DATETIME NULL COMMENT '报价有效期-止/datetime ',
  `tender_document_price_amount` DECIMAL(20,6) NULL COMMENT '标书售价(数值)/decimal(20,6) ',
  `tender_document_price_unit` VARCHAR(255) NULL COMMENT '标书售价(单位)/varchar(255) ',
  `registration_fee_amount` DECIMAL(20,6) NULL COMMENT '报名费(数值)/decimal(20,6) ',
  `registration_fee_unit` VARCHAR(255) NULL COMMENT '报名费(单位)/varchar(255) ',
  `bidding_security_amount` DECIMAL(20,6) NULL COMMENT '投标保证金(数值)/decimal(20,6) ',
  `bidding_security_unit` VARCHAR(255) NULL COMMENT '投标保证金(单位)/varchar(255) ',
  `ca_payment_amount` DECIMAL(20,6) NULL COMMENT 'CA缴纳费用(数值字)/decimal(20,6) ',
  `ca_payment_unit` VARCHAR(255) NULL COMMENT 'CA缴纳费用(单位)/varchar(255) ',
  `tender_agent_service_fee_amount` DECIMAL(20,6) NULL COMMENT '招标代理服务费(数值)/decimal(20,6) ',
  `tender_agent_service_fee_unit` VARCHAR(255) NULL COMMENT '招标代理服务费(单位)/varchar(255) ',
  `performance_security_amount` DECIMAL(20,6) NULL COMMENT '履约保证金(数值)/decimal(20,6) ',
  `performance_security_unit` VARCHAR(255) NULL COMMENT '履约保证金(单位)/varchar(255) ',
  `funding_source` TEXT NULL COMMENT '资金来源/text ',
  `construction_service_location` TEXT NULL COMMENT '建设地点/服务地点/text ',
  `construction_service_period` TEXT NULL COMMENT '工期/服务周期/text ',
  `allow_joint_bid` DECIMAL(20,0) NULL COMMENT '是否允许联合体投标/decimal(20,0) ',
  `bidding_document_sub_style` DECIMAL(20,0) NULL COMMENT '投标文件递交方式/decimal(20,0) ',
  `supplier_qualification_criteria` TEXT NULL COMMENT '供应商的准入资质/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标公告基础表';

-- 招投标中标候选人表：dwd_bid_win_candidate_out
CREATE TABLE IF NOT EXISTS `dwd_bid_win_candidate_out` (
  `u_id` VARCHAR(255) NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `org_id` VARCHAR(255) NULL COMMENT '机构id/varchar(255) ',
  `name_cn` VARCHAR(255) NULL COMMENT '机构名称/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `project_number` VARCHAR(255) NULL COMMENT '项目编号/varchar(255) ',
  `project_name` TEXT NULL COMMENT '项目名称/text ',
  `bid_item_name` TEXT NULL COMMENT '招标项目名称/text ',
  `bid_section_number` VARCHAR(255) NULL COMMENT '标段编号/varchar(255) ',
  `amount` DECIMAL(20,6) NULL COMMENT '中标报价(金额)/decimal(20,6) ',
  `amount_unit` VARCHAR(255) NULL COMMENT '中标报价(单位)/varchar(255) ',
  `ranking` DECIMAL(20,0) NULL COMMENT '候选人排名/decimal(20,0) ',
  `relate_type` DECIMAL(20,0) NULL COMMENT '关系类型/decimal(20,0) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标中标候选人表';

-- 招投标采购代理表：dwd_bid_purchase_agency_out
CREATE TABLE IF NOT EXISTS `dwd_bid_purchase_agency_out` (
  `u_id` VARCHAR(255) NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `company_id` VARCHAR(255) NULL COMMENT '机构id/varchar(255) ',
  `company_name` VARCHAR(255) NULL COMMENT '机构名称/varchar(255) ',
  `credit_no` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `project_number` VARCHAR(255) NULL COMMENT '项目编号/varchar(255) ',
  `project_name` TEXT NULL COMMENT '项目名称/text ',
  `relate_type` DECIMAL(20,0) NULL COMMENT '枚举判断/decimal(20,0) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`),
  KEY `idx_company_id` (`company_id`),
  KEY `idx_company_name` (`company_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标采购代理表';

-- 招投标标的物表：dwd_bid_target_item_out
CREATE TABLE IF NOT EXISTS `dwd_bid_target_item_out` (
  `u_id` VARCHAR(255) NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `project_number` TEXT NULL COMMENT '项目编号/text ',
  `project_name` TEXT NULL COMMENT '项目名称/text ',
  `amount_unit` VARCHAR(255) NULL COMMENT '金额单位/varchar(255) ',
  `bid_item_name` TEXT NULL COMMENT '招标项目名称/text ',
  `bid_section_number` VARCHAR(255) NULL COMMENT '标段编号/varchar(255) ',
  `brand` VARCHAR(255) NULL COMMENT '品牌/varchar(255) ',
  `model` VARCHAR(255) NULL COMMENT '型号/varchar(255) ',
  `project_content` VARCHAR(255) NULL COMMENT '项目内容/varchar(255) ',
  `quantity` DECIMAL(20,0) NULL COMMENT '数量/decimal(20,0) ',
  `service_content` TEXT NULL COMMENT '服务内容/text ',
  `standard_product_name` VARCHAR(255) NULL COMMENT '标准产品名称/varchar(255) ',
  `target_item_name` TEXT NULL COMMENT '标的物名称/text ',
  `target_item_type` VARCHAR(255) NULL COMMENT '标的物类型/varchar(255) ',
  `unit_price_amount` DECIMAL(20,2) NULL COMMENT '单价金额/decimal(20,2) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标标的物表';

-- 科研机构基本信息：dwd_research_institute_base_info
CREATE TABLE IF NOT EXISTS `dwd_research_institute_base_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `lerep` VARCHAR(255) NULL COMMENT '法定代表人/varchar(255) ',
  `reg_status` VARCHAR(255) NULL COMMENT '登记状态/varchar(255) ',
  `incorporation_date` DATETIME NULL COMMENT '成立日期/datetime ',
  `org_type` VARCHAR(255) NULL COMMENT '类型/varchar(255) ',
  `registered_capital_value` VARCHAR(255) NULL COMMENT '注册资本(本币元)/varchar(255) ',
  `capital_currency` VARCHAR(255) NULL COMMENT '币种/varchar(255) ',
  `address` TEXT NULL COMMENT '登记地址/text ',
  `name_en` VARCHAR(255) NULL COMMENT '英文名称/varchar(255) ',
  `registration_org` VARCHAR(255) NULL COMMENT '登记机关/varchar(255) ',
  `province` VARCHAR(255) NULL COMMENT '所在省份/varchar(255) ',
  `city` VARCHAR(255) NULL COMMENT '所在城市/varchar(255) ',
  `area` VARCHAR(255) NULL COMMENT '所在区县/varchar(255) ',
  `addr_lng` VARCHAR(255) NULL COMMENT '地址对应经度/varchar(255) ',
  `addr_lat` VARCHAR(255) NULL COMMENT '地址对应维度/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_name_cn` (`name_cn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='科研机构基本信息';

SET FOREIGN_KEY_CHECKS = 1;
