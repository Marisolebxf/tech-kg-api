-- 国外机构要素库建表 SQL
-- 来源文件：国外机构要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 海外机构基本信息：dwd_forg_base_info
CREATE TABLE IF NOT EXISTS `dwd_forg_base_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `name_en` VARCHAR(255) NOT NULL COMMENT '机构名称/varchar(255) ',
  `name_alias` VARCHAR(255) NULL COMMENT '机构本地名称/varchar(255) ',
  `country_code` VARCHAR(255) NULL COMMENT '国家代码/varchar(255) ',
  `country` VARCHAR(255) NULL COMMENT '国家/varchar(255) ',
  `external_id` VARCHAR(255) NULL COMMENT '当地官方唯一注册码/varchar(255) ',
  `city` VARCHAR(255) NULL COMMENT '所在城市/varchar(255) ',
  `address` TEXT NULL COMMENT '公司地址/text ',
  `postal_code` VARCHAR(255) NULL COMMENT '邮政编码（无数据）/varchar(255) ',
  `phone` VARCHAR(255) NULL COMMENT '联系电话/varchar(255) ',
  `email` VARCHAR(255) NULL COMMENT '电子邮箱/varchar(255) ',
  `company_type` TEXT NULL COMMENT '企业类型/text ',
  `registration_org` TEXT NULL COMMENT '注册机构（无数据）/text ',
  `incorporation_year` DECIMAL(20,0) NULL COMMENT '成立年份/decimal(20,0) ',
  `incorporation_date` DATETIME NULL COMMENT '成立日期/注册日期/核准日期/datetime ',
  `listing_status` VARCHAR(255) NULL COMMENT '上市状态/varchar(255) ',
  `registered_capital_value` DECIMAL(20,0) NULL COMMENT '注册资本/decimal(20,0) ',
  `registered_capital_currency_code` VARCHAR(255) NULL COMMENT '注册资本货币代码/varchar(255) ',
  `industry_class` VARCHAR(255) NULL COMMENT '公司行业分类/varchar(255) ',
  `industry_type` VARCHAR(255) NULL COMMENT '行业分类标准（新增字段）/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构基本信息';

-- 海外机构股东股权关联信息：dwd_forg_shareholder_info
CREATE TABLE IF NOT EXISTS `dwd_forg_shareholder_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `owners_name` VARCHAR(255) NULL COMMENT '股东名称/varchar(255) ',
  `ownership_percentage` DECIMAL(20,2) NULL COMMENT '股权占比(%)/decimal(20,2) ',
  `owners_country_code` VARCHAR(255) NULL COMMENT '股东所在国家代码/varchar(255) ',
  `owners_country` VARCHAR(255) NULL COMMENT '股东所在国家/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构股东股权关联信息';

-- 海外机构子公司股权关联信息：dwd_forg_subsidiary_info
CREATE TABLE IF NOT EXISTS `dwd_forg_subsidiary_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `affiliate` VARCHAR(255) NULL COMMENT '子公司id/varchar(255) ',
  `affiliates_name` VARCHAR(255) NULL COMMENT '子公司名称/varchar(255) ',
  `affiliates_country_code` VARCHAR(255) NULL COMMENT '子公司国家代码/varchar(255) ',
  `affiliates_country` VARCHAR(255) NULL COMMENT '子公司国家/varchar(255) ',
  `affiliates_company_id` VARCHAR(255) NULL COMMENT '子公司唯一注册码/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构子公司股权关联信息';

-- 海外机构高管信息：dwd_forg_executive_info
CREATE TABLE IF NOT EXISTS `dwd_forg_executive_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `executives_name` VARCHAR(255) NULL COMMENT '高管姓名/varchar(255) ',
  `executives_position` VARCHAR(255) NULL COMMENT '职位名称/varchar(255) ',
  `dm_birthdate` DATETIME NULL COMMENT '高管出生日期(新增字段)/datetime ',
  `dm_nationalities` VARCHAR(255) NULL COMMENT '高管国籍(新增字段)/varchar(255) ',
  `dm_biography` VARCHAR(255) NULL COMMENT '高管履历(新增字段)/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构高管信息';

-- 海外机构公司经营信息：dwd_forg_product_info
CREATE TABLE IF NOT EXISTS `dwd_forg_product_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `description` VARCHAR(255) NULL COMMENT '业务描述/varchar(255) ',
  `main_products` VARCHAR(255) NULL COMMENT '主要产品/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构公司经营信息';

-- 海外机构受益人信息（新增表）：dwd_forg_beneficiary_info
CREATE TABLE IF NOT EXISTS `dwd_forg_beneficiary_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `bo_name` VARCHAR(255) NULL COMMENT '受益人名称/varchar(255) ',
  `bo_gender` VARCHAR(255) NULL COMMENT '受益人性别/varchar(255) ',
  `bo_birthdate` DATETIME NULL COMMENT '受益人出生日期/datetime ',
  `bo_country_code` VARCHAR(255) NULL COMMENT '受益人所在国家代码/varchar(255) ',
  `path` VARCHAR(255) NULL COMMENT '受益人关系路径/varchar(255) ',
  `bo_manager` VARCHAR(255) NULL COMMENT '受益人是否同时是管理层/varchar(255) ',
  `total_percent` DECIMAL(20,2) NULL COMMENT '总持股比例/decimal(20,2) ',
  `direct_percent` DECIMAL(20,2) NULL COMMENT '直接持股比例/decimal(20,2) ',
  `indirect_percent` DECIMAL(20,2) NULL COMMENT '间接持股比例/decimal(20,2) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构受益人信息（新增表）';

-- 海外机构实控人信息（新增表）：dwd_forg_act_contro_info
CREATE TABLE IF NOT EXISTS `dwd_forg_act_contro_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `country_code` VARCHAR(255) NULL COMMENT '企业国家代码/varchar(255) ',
  `entity_eid` VARCHAR(255) NULL COMMENT '实控人ID/varchar(255) ',
  `entity_name` VARCHAR(255) NULL COMMENT '实控人名称/varchar(255) ',
  `entity_type` VARCHAR(255) NULL COMMENT '实控人类型/varchar(255) ',
  `entity_country_code` VARCHAR(255) NULL COMMENT '实控人国家代码/varchar(255) ',
  `direct_pct` VARCHAR(255) NULL COMMENT '直接持股比例/varchar(255) ',
  `total_pct` VARCHAR(255) NULL COMMENT '总持股比例/varchar(255) ',
  `direct_pct_num` DECIMAL(20,2) NULL COMMENT '直接持股比例数值/decimal(20,2) ',
  `total_pct_num` DECIMAL(20,2) NULL COMMENT '总持股比例数值/decimal(20,2) ',
  `path` VARCHAR(255) NULL COMMENT '路径/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构实控人信息（新增表）';

-- 海外上市企业财务信息：dwd_forg_stock_fin_info
CREATE TABLE IF NOT EXISTS `dwd_forg_stock_fin_info` (
  `org_id` VARCHAR(255) NOT NULL COMMENT '机构id/varchar(255) ',
  `occur_period` DATETIME NULL COMMENT '报告期/datetime ',
  `total_assets` DECIMAL(20,2) NULL COMMENT '资产总额/decimal(20,2) ',
  `fixed_assets` DECIMAL(20,2) NULL COMMENT '固定资产总额/decimal(20,2) ',
  `total_liabilities` DECIMAL(20,2) NULL COMMENT '负债总额/decimal(20,2) ',
  `operating_revenue` DECIMAL(20,2) NULL COMMENT '营业收入/decimal(20,2) ',
  `main_business_revenue` DECIMAL(20,2) NULL COMMENT '主营业务收入/decimal(20,2) ',
  `total_profit` DECIMAL(20,2) NULL COMMENT '利润总额/decimal(20,2) ',
  `pure_profit` DECIMAL(20,2) NULL COMMENT '净利润/decimal(20,2) ',
  `total_tax_paid` DECIMAL(20,2) NULL COMMENT '企业所得税/decimal(20,2) ',
  `oper_cash_flow` DECIMAL(20,2) NULL COMMENT '经营活动现金流/decimal(20,2) ',
  `owners_equity` DECIMAL(20,2) NULL COMMENT '所有者权益合计/decimal(20,2) ',
  `employees_number` DECIMAL(20,2) NULL COMMENT '从业人数/decimal(20,2) ',
  `research_development_amount` DECIMAL(20,2) NULL COMMENT '研发投入金额/decimal(20,2) ',
  `research_development_employees_number` DECIMAL(20,2) NULL COMMENT '研发人员数（无数据）/decimal(20,2) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外上市企业财务信息';

SET FOREIGN_KEY_CHECKS = 1;
