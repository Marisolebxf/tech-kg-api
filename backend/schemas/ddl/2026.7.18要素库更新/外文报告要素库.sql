-- 外文报告要素库建表 SQL
-- 来源文件：外文报告要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- 同一表内重复字段名：首次保留原名，后续依次追加 _2、_3……
-- MySQL 不支持直接为 JSON 列创建普通 B-Tree 索引，因此相关 JSON 索引要求仅保留字段，不生成无效索引。

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 外文科技报告信息表：dwd_en_report
CREATE TABLE IF NOT EXISTS `dwd_en_report` (
  `report_id` VARCHAR(64) NOT NULL COMMENT '外文报告id/varchar(64) ',
  `report_number` VARCHAR(64) NULL COMMENT '报告编号/varchar(64) ',
  `title_en` VARCHAR(512) NULL COMMENT '英文题名/varchar(512) ',
  `publication_date` VARCHAR(8) NULL COMMENT '发布时间/出版日期/varchar(8) ',
  `authors` JSON NULL COMMENT '作者/json ',
  `corporate_author` JSON NULL COMMENT '团体作者/json ',
  `source_agency` VARCHAR(64) NULL COMMENT '来源机构/出版社/varchar(64) ',
  `source_url` VARCHAR(512) NULL COMMENT '报告原文链接/varchar(512) ',
  `abstract_en` LONGTEXT NULL COMMENT '英文摘要/longtext ',
  `keywords_en` JSON NULL COMMENT '英文关键词/json ',
  `page_count` INT NULL COMMENT '全文页数/int ',
  `document_type` VARCHAR(64) NULL COMMENT '文档类型/varchar(64) ',
  `contract_number` VARCHAR(32) NULL COMMENT '合同编号/varchar(32) ',
  `content` LONGTEXT NULL COMMENT '正文内容/longtext ',
  `related_literature` JSON NULL COMMENT '相关文献/json ',
  `related_scholars` JSON NULL COMMENT '相关学者/json ',
  `updated_time` VARCHAR(8) NOT NULL COMMENT '更新时间/varchar(8) ',
  `literature_id` JSON NULL COMMENT '相关文献ID/json ',
  `org_id` JSON NULL COMMENT '相关机构ID/json ',
  `authors_id` JSON NULL COMMENT '相关作者ID/json ',
  `scholar_id` JSON NULL COMMENT '相关学者ID/json ',
  `file_path` JSON NULL COMMENT '文件路径/json ',
  KEY `idx_report_id` (`report_id`),
  KEY `idx_report_number` (`report_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告信息表';

-- 外文科技报告信息表：ods_en_report
CREATE TABLE IF NOT EXISTS `ods_en_report` (
  `affiliation` VARCHAR(1000) NOT NULL COMMENT '作者机构/varchar(1000) ',
  `country` VARCHAR(100) NOT NULL COMMENT '出版国/varchar(100) ',
  `pub_year` INT NOT NULL COMMENT '出版年/int ',
  `document_type` VARCHAR(100) NULL COMMENT '资源类型/varchar(100) ',
  `category` VARCHAR(300) NULL COMMENT '分类/varchar(300) ',
  KEY `idx_affiliation` (`affiliation`(191)),
  KEY `idx_country` (`country`),
  KEY `idx_document_type` (`document_type`),
  KEY `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告信息表';

-- 外文科技报告与作者关联表：dwd_en_report_author
CREATE TABLE IF NOT EXISTS `dwd_en_report_author` (
  `authors_id` VARCHAR(64) NOT NULL COMMENT '作者唯一标识ID/varchar(64) ',
  `authors_name` VARCHAR(64) NOT NULL COMMENT '作者名称/varchar(64) ',
  `authors_unit` JSON NOT NULL COMMENT '作者所属机构/json ',
  `report_id` JSON NOT NULL COMMENT '外文报告ID集合/json ',
  `report_source` VARCHAR(32) NOT NULL COMMENT '报告所属来源/varchar(32) ',
  KEY `idx_authors_id` (`authors_id`),
  KEY `idx_authors_name` (`authors_name`),
  KEY `idx_report_source` (`report_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告与作者关联表';

-- 外文科技报告与机构关联表：dwd_en_report_org
-- 重复字段 `report_source` 调整为：`report_source`、`report_source_2`
CREATE TABLE IF NOT EXISTS `dwd_en_report_org` (
  `org_id` VARCHAR(64) NOT NULL COMMENT '机构ID/varchar(64) ',
  `org_name` VARCHAR(200) NOT NULL COMMENT '机构名称/varchar(200) ',
  `org_country` VARCHAR(50) NOT NULL COMMENT '机构国别/varchar(50) ',
  `report_id` JSON NOT NULL COMMENT '外文报告ID集合/json ',
  `report_source` VARCHAR(32) NOT NULL COMMENT '报告所属来源/varchar(32) ',
  `report_source_2` VARCHAR(32) NOT NULL COMMENT '报告所属来源/varchar(32) ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_org_name` (`org_name`),
  KEY `idx_org_country` (`org_country`),
  KEY `idx_report_source` (`report_source`),
  KEY `idx_report_source_2` (`report_source_2`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告与机构关联表';

SET FOREIGN_KEY_CHECKS = 1;
