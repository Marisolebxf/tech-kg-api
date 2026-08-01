-- 全球专利要素库建表 SQL
-- 来源文件：全球专利要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- 同一表内重复字段名：首次保留原名，后续依次追加 _2、_3、_4……

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 专利信息表：dwd_patent
-- 重复字段 `publication_reference` 调整为：`publication_reference`、`publication_reference_2`、`publication_reference_3`、`publication_reference_4`
-- 重复字段 `application_reference` 调整为：`application_reference`、`application_reference_2`、`application_reference_3`、`application_reference_4`、`application_reference_5`
-- 重复字段 `pct_or_regional_filing_data` 调整为：`pct_or_regional_filing_data`、`pct_or_regional_filing_data_2`、`pct_or_regional_filing_data_3`
-- 重复字段 `pct_or_regional_publishing_data` 调整为：`pct_or_regional_publishing_data`、`pct_or_regional_publishing_data_2`
-- 重复字段 `priority_filings` 调整为：`priority_filings`、`priority_filings_2`、`priority_filings_3`、`priority_filings_4`、`priority_filings_5`、`priority_filings_6`、`priority_filings_7`、`priority_filings_8`、`priority_filings_9`
-- 重复字段 `applicants` 调整为：`applicants`、`applicants_2`
-- 重复字段 `assignees` 调整为：`assignees`、`assignees_2`
-- 重复字段 `inventors` 调整为：`inventors`、`inventors_2`
-- 重复字段 `classification_ipcr` 调整为：`classification_ipcr`、`classification_ipcr_2`
-- 重复字段 `classification_cpc` 调整为：`classification_cpc`、`classification_cpc_2`
CREATE TABLE IF NOT EXISTS `dwd_patent` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `publication_number` VARCHAR(64) NOT NULL COMMENT '专利公布号/varchar(64) ',
  `application_kind` VARCHAR(1) NULL COMMENT '专利申请类型/varchar(1) ',
  `country_code` VARCHAR(8) NOT NULL COMMENT '国家代码/varchar(8) ',
  `country` VARCHAR(20) NOT NULL COMMENT '国家/varchar(20) ',
  `publication_reference` VARCHAR(16) NULL COMMENT '发布文献种类代码/varchar(16) ',
  `publication_reference_2` VARCHAR(10) NULL COMMENT '发布日期/varchar(10) ',
  `publication_reference_3` VARCHAR(4) NULL COMMENT '发布年份/varchar(4) ',
  `publication_reference_4` VARCHAR(7) NULL COMMENT '发布年月/varchar(7) ',
  `application_reference` VARCHAR(64) NULL COMMENT '专利申请号/varchar(64) ',
  `application_reference_2` VARCHAR(8) NOT NULL COMMENT '申请受理局代码/varchar(8) ',
  `application_reference_3` VARCHAR(10) NULL COMMENT '申请日期/varchar(10) ',
  `application_reference_4` VARCHAR(4) NULL COMMENT '申请年份/varchar(4) ',
  `application_reference_5` VARCHAR(7) NULL COMMENT '申请年月/varchar(7) ',
  `pct_or_regional_filing_data` VARCHAR(64) NULL COMMENT 'PCT申请号/varchar(64) ',
  `pct_or_regional_filing_data_2` VARCHAR(10) NULL COMMENT 'PCT国际申请日期/varchar(10) ',
  `pct_or_regional_filing_data_3` VARCHAR(10) NULL COMMENT 'PCT进入国家阶段日期/varchar(10) ',
  `pct_or_regional_publishing_data` VARCHAR(64) NULL COMMENT 'PCT国际公布号/varchar(64) ',
  `pct_or_regional_publishing_data_2` VARCHAR(10) NULL COMMENT 'PCT国际公布日期/varchar(10) ',
  `priority_filings` INT NULL COMMENT '优先权序号/int ',
  `priority_filings_2` INT NULL COMMENT '优先权语言/int ',
  `priority_filings_3` VARCHAR(64) NULL COMMENT '优先权申请号/varchar(64) ',
  `priority_filings_4` VARCHAR(64) NULL COMMENT '优先权公布号/varchar(64) ',
  `priority_filings_5` VARCHAR(8) NULL COMMENT '优先权所属国家/地区/组织代码/varchar(8) ',
  `priority_filings_6` VARCHAR(10) NULL COMMENT '优先权日期/varchar(10) ',
  `priority_filings_7` VARCHAR(4) NULL COMMENT '优先权年份/varchar(4) ',
  `priority_filings_8` VARCHAR(16) NULL COMMENT '优先权申请类型代码/varchar(16) ',
  `priority_filings_9` VARCHAR(255) NULL COMMENT '优先权标题/varchar(255) ',
  `applicants` INT NULL COMMENT '原始申请人序号/int ',
  `applicants_2` VARCHAR(255) NULL COMMENT '原始申请人名称/varchar(255) ',
  `assignees` INT NULL COMMENT '当前申请人/专利权人序号/int ',
  `assignees_2` VARCHAR(255) NULL COMMENT '当前申请人/专利权人名称/varchar(255) ',
  `inventors` INT NULL COMMENT '发明人序号/int ',
  `inventors_2` VARCHAR(255) NULL COMMENT '发明人/varchar(255) ',
  `first_applicant_name` VARCHAR(255) NULL COMMENT '第一原始申请人/varchar(255) ',
  `first_current_assignee_name` VARCHAR(255) NULL COMMENT '第一当前申请人/专利权人/varchar(255) ',
  `first_inventor_name` VARCHAR(255) NULL COMMENT '第一发明人/varchar(255) ',
  `classification_ipcr` VARCHAR(32) NULL COMMENT 'IPCR/IPC主分类号/varchar(32) ',
  `classification_ipcr_2` VARCHAR(32) NULL COMMENT 'IPCR/IPC附加分类号/varchar(32) ',
  `classification_cpc` VARCHAR(32) NULL COMMENT 'CPC主分类号/varchar(32) ',
  `classification_cpc_2` VARCHAR(32) NULL COMMENT 'CPC附加分类号/varchar(32) ',
  `keywords` JSON NULL COMMENT '关键词/json ',
  `claims_localized` JSON NULL COMMENT '权利要求/json ',
  `description_localized` JSON NULL COMMENT '说明书/json ',
  `figures` JSON NULL COMMENT '专利图/json ',
  `language` VARCHAR(16) NULL COMMENT '原文语言/varchar(16) ',
  `granted_number` VARCHAR(64) NULL COMMENT '授权号/varchar(64) ',
  `db_source` VARCHAR(64) NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NULL COMMENT '更新时间/datetime ',
  `value` INT NULL COMMENT '专利价值/int ',
  `agents` JSON NULL COMMENT '代理人/json ',
  `agency` JSON NULL COMMENT '代理机构/json ',
  `examiners` JSON NULL COMMENT '审核员/json ',
  `related_documents` JSON NULL COMMENT '分案继续申请信息/json ',
  `classification_loc` JSON NULL COMMENT 'LOC分类/json ',
  `classification_fi` JSON NULL COMMENT 'FI分类号/json ',
  `classification_upc` JSON NULL COMMENT 'UPC分类号/json ',
  `classification_fterm` JSON NULL COMMENT 'F_term分类号/json ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利信息表';

-- 专利引用关系表：dwd_patent_cited
-- 重复字段 `reference_cited` 调整为：`reference_cited`、`reference_cited_2`、`reference_cited_3`、`reference_cited_4`、`reference_cited_5`、`reference_cited_6`、`reference_cited_7`、`reference_cited_8`
CREATE TABLE IF NOT EXISTS `dwd_patent_cited` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `reference_cited` INT NOT NULL COMMENT '引用专利数量/int ',
  `cited_by_nums` INT NOT NULL COMMENT '专利被引数量/int ',
  `reference_cited_2` VARCHAR(10) NULL COMMENT '被引专利日期/varchar(10) ',
  `reference_cited_3` VARCHAR(10) NULL COMMENT '引用专利日期/varchar(10) ',
  `reference_cited_4` INT NOT NULL COMMENT '非专利文献引用数量/int ',
  `reference_cited_5` VARCHAR(10) NULL COMMENT '非专利文献引用日期/varchar(10) ',
  `reference_cited_6` VARCHAR(8) NULL COMMENT '引用专利国家/地区/组织代码/varchar(8) ',
  `reference_cited_7` VARCHAR(20) NULL COMMENT '引用专利所属国家/地区/varchar(20) ',
  `reference_cited_8` VARCHAR(16) NULL COMMENT '引用专利文献种类代码/varchar(16) ',
  `cited_by` JSON NULL COMMENT '被引用/json ',
  `patent_citations` JSON NULL COMMENT '专利引用/json ',
  `non_patent_citations` JSON NULL COMMENT '非专利引用/json ',
  `db_source` VARCHAR(64) NOT NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利引用关系表';

-- 专利标题信息表：dwd_patent_title
-- 重复字段 `title_localized` 调整为：`title_localized`、`title_localized_2`
CREATE TABLE IF NOT EXISTS `dwd_patent_title` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `title_localized` VARCHAR(1024) NOT NULL COMMENT '原文标题/varchar(1024) ',
  `title_localized_2` VARCHAR(1024) NULL COMMENT '英文标题/varchar(1024) ',
  `title_zh` VARCHAR(1024) NULL COMMENT '中文翻译标题/varchar(1024) ',
  `db_source` VARCHAR(64) NOT NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利标题信息表';

-- 专利摘要信息表：dwd_patent_abstract
-- 重复字段 `abstract_localized` 调整为：`abstract_localized`、`abstract_localized_2`
CREATE TABLE IF NOT EXISTS `dwd_patent_abstract` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `abstract_localized` TEXT NOT NULL COMMENT '原文摘要/text ',
  `abstract_localized_2` TEXT NULL COMMENT '英文摘要/text ',
  `abstract_zh` TEXT NULL COMMENT '中文翻译摘要/text ',
  `db_source` VARCHAR(64) NOT NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利摘要信息表';

-- 法律状态信息表：dwd_patent_legal
-- 重复字段 `dates_of_public_availability` 调整为：`dates_of_public_availability`、`dates_of_public_availability_2`、`dates_of_public_availability_3`
-- 重复字段 `patent_legal/prs_data` 调整为：`patent_legal/prs_data`、`patent_legal/prs_data_2`、`patent_legal/prs_data_3`、`patent_legal/prs_data_4`
CREATE TABLE IF NOT EXISTS `dwd_patent_legal` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `dates_of_public_availability` VARCHAR(10) NULL COMMENT '授权日期/varchar(10) ',
  `dates_of_public_availability_2` VARCHAR(4) NULL COMMENT '授权年份/varchar(4) ',
  `dates_of_public_availability_3` VARCHAR(7) NULL COMMENT '授权年月/varchar(7) ',
  `status` VARCHAR(64) NULL COMMENT '专利状态/varchar(64) ',
  `legal_events` JSON NULL COMMENT '法律事件/json ',
  `patent_legal/prs_data` VARCHAR(10) NULL COMMENT 'PRS法律状态日期/varchar(10) ',
  `patent_legal/prs_data_2` VARCHAR(16) NULL COMMENT 'PRS法律状态代码/varchar(16) ',
  `patent_legal/prs_data_3` VARCHAR(255) NULL COMMENT 'PRS法律状态说明/varchar(255) ',
  `patent_legal/prs_data_4` VARCHAR(64) NULL COMMENT '法律状态分类说明/varchar(64) ',
  `anticipated_expiration` VARCHAR(10) NULL COMMENT '预计到期日/varchar(10) ',
  `expiration_year` VARCHAR(4) NULL COMMENT '到期年份/varchar(4) ',
  `db_source` VARCHAR(64) NOT NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='法律状态信息表';

-- 专利转移信息表：dwd_patent_transfer
CREATE TABLE IF NOT EXISTS `dwd_patent_transfer` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `country` VARCHAR(8) NOT NULL COMMENT '转移国家/地区/组织代码/varchar(8) ',
  `transfer_effective_date` VARCHAR(10) NULL COMMENT '转移生效日期/varchar(10) ',
  `transferor_sequence` INT NULL COMMENT '转移前权利人序号/int ',
  `transferor_name` VARCHAR(255) NULL COMMENT '转移前权利人名称/varchar(255) ',
  `transferee_sequence` INT NULL COMMENT '转移后权利人序号/int ',
  `transferee_name` VARCHAR(255) NULL COMMENT '转移后权利人名称/varchar(255) ',
  `db_source` VARCHAR(64) NOT NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利转移信息表';

-- 专利家族信息表：dwd_patent_family
-- 重复字段 `simple_family` 调整为：`simple_family`、`simple_family_2`、`simple_family_3`、`simple_family_4`、`simple_family_5`
CREATE TABLE IF NOT EXISTS `dwd_patent_family` (
  `id` BIGINT NOT NULL COMMENT '逻辑id/bigint ',
  `patent_id` VARCHAR(64) NOT NULL COMMENT '专利id/varchar(64) ',
  `simple_family` VARCHAR(20) NOT NULL COMMENT '专利家族ID/varchar(20) ',
  `simple_family_2` JSON NOT NULL COMMENT '专利家族/json ',
  `simple_family_3` INT NOT NULL COMMENT '家族成员序号/int ',
  `simple_family_4` VARCHAR(8) NOT NULL COMMENT '家族成员所属国家/地区/组织代码/varchar(8) ',
  `simple_family_5` VARCHAR(16) NOT NULL COMMENT '家族成员文献种类代码/varchar(16) ',
  `family_citations` JSON NULL COMMENT '家族内引用/json ',
  `cited_by_family` JSON NULL COMMENT '家族内被引用/json ',
  `worldwides` JSON NOT NULL COMMENT '全球同族专利/json ',
  `db_source` VARCHAR(64) NOT NULL COMMENT '数据库来源/varchar(64) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利家族信息表';

SET FOREIGN_KEY_CHECKS = 1;
