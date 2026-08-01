-- 中文报告要素库建表 SQL
-- 来源文件：中文报告要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- 同一表内重复字段名：首次保留原名，后续依次追加 _2、_3……
-- Excel 未填写数据类型的字段使用 TEXT 类型兜底。

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 中文科技报告信息表：dwd_zh_report
CREATE TABLE IF NOT EXISTS `dwd_zh_report` (
  `report_id` VARCHAR(64) NOT NULL COMMENT '中文报告id/varchar(64) ',
  `report_category` VARCHAR(64) NULL COMMENT '报告类别/varchar(64) ',
  `title_cn` VARCHAR(512) NULL COMMENT '中文题名/varchar(512) ',
  `authors` JSON NULL COMMENT '作者/json ',
  `organization` JSON NULL COMMENT '作者单位/完成单位/json ',
  `abstract_cn` LONGTEXT NULL COMMENT '中文摘要/longtext ',
  `keywords_cn` JSON NULL COMMENT '中文关键词/json ',
  `report_type` VARCHAR(32) NULL COMMENT '报告类型/varchar(32) ',
  `page_count` INT NULL COMMENT '全文页数/int ',
  `preparation_time` VARCHAR(8) NULL COMMENT '编制时间/varchar(8) ',
  `approval_year` INT NULL COMMENT '立项批准年/int ',
  `related_literature` JSON NULL COMMENT '相关文献/json ',
  `related_scholars` JSON NULL COMMENT '相关学者/json ',
  `related_institutions` JSON NULL COMMENT '相关机构/json ',
  `related_projects` JSON NULL COMMENT '相关项目/json ',
  `source_org` JSON NULL COMMENT '报告来源/json ',
  `source_url` TEXT NULL COMMENT '报告原文链接/text ',
  `visibility_scope` VARCHAR(16) NULL COMMENT '可见范围/varchar(16) ',
  `project_annual_number` INT NULL COMMENT '项目年度编号/int ',
  `contact_phone` VARCHAR(64) NULL COMMENT '联系电话/varchar(64) ',
  `updated_time` VARCHAR(8) NOT NULL COMMENT '更新时间/varchar(8) ',
  `scholar_id` JSON NULL COMMENT '相关学者ID/json ',
  `org_id` JSON NULL COMMENT '相关机构ID/json ',
  `paper_id` JSON NULL COMMENT '相关论文ID/json ',
  `project_id` JSON NULL COMMENT '相关项目ID/json ',
  `file_path` JSON NULL COMMENT '文件路径/json ',
  KEY `idx_report_id` (`report_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文科技报告信息表';

-- 报告-人才关联表：dwd_zh_report_scholar
CREATE TABLE IF NOT EXISTS `dwd_zh_report_scholar` (
  `scholar_id` VARCHAR(64) NOT NULL COMMENT '学者ID/varchar(64) ',
  `scholar_name` VARCHAR(64) NOT NULL COMMENT '学者名字/varchar(64) ',
  `scholar_unit` JSON NOT NULL COMMENT '学者所属机构/json ',
  `scholar_project` JSON NOT NULL COMMENT '学者参与项目名称/json ',
  `report_id` JSON NOT NULL COMMENT '中文报告ID集合/json ',
  `report_source` VARCHAR(32) NOT NULL COMMENT '报告所属来源/varchar(32) ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_scholar_name` (`scholar_name`),
  KEY `idx_report_source` (`report_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-人才关联表';

-- 报告-论文关联表：dwd_zh_report_paper
CREATE TABLE IF NOT EXISTS `dwd_zh_report_paper` (
  `paper_id` VARCHAR(64) NOT NULL COMMENT '论文ID/varchar(64) ',
  `paper_name` VARCHAR(300) NOT NULL COMMENT '论文名称/varchar(300) ',
  `paper_doi` VARCHAR(100) NOT NULL COMMENT '论文DOI/varchar(100) ',
  `report_source` VARCHAR(32) NOT NULL COMMENT '报告所属来源/varchar(32) ',
  `report_id` JSON NOT NULL COMMENT '中文报告ID集合/json ',
  `paper_source` VARCHAR(32) NOT NULL COMMENT '论文来源/varchar(32) ',
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_paper_name` (`paper_name`),
  KEY `idx_paper_doi` (`paper_doi`),
  KEY `idx_report_source` (`report_source`),
  KEY `idx_paper_source` (`paper_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-论文关联表';

-- 报告-项目关联表：dwd_zh_report_project
CREATE TABLE IF NOT EXISTS `dwd_zh_report_project` (
  `project_id` VARCHAR(64) NOT NULL COMMENT '项目ID/varchar(64) ',
  `project_name` VARCHAR(200) NOT NULL COMMENT '项目名称/varchar(200) ',
  `project_subject` VARCHAR(100) NOT NULL COMMENT '项目领域/varchar(100) ',
  `project_type` VARCHAR(100) NOT NULL COMMENT '项目类别/varchar(100) ',
  `project_number` VARCHAR(100) NOT NULL COMMENT '项目编号/varchar(100) ',
  `report_id` VARCHAR(64) NOT NULL COMMENT '中文报告ID集合/varchar(64) ',
  `project_source` VARCHAR(32) NOT NULL COMMENT '项目来源/varchar(32) ',
  KEY `idx_project_id` (`project_id`),
  KEY `idx_project_name` (`project_name`),
  KEY `idx_project_subject` (`project_subject`),
  KEY `idx_project_type` (`project_type`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_project_source` (`project_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-项目关联表';

-- 报告-机构关联表：dwd_zh_report_org
CREATE TABLE IF NOT EXISTS `dwd_zh_report_org` (
  `org_id` VARCHAR(64) NOT NULL COMMENT '机构ID/varchar(64) ',
  `org_name` VARCHAR(200) NOT NULL COMMENT '机构名称/varchar(200) ',
  `org_xydm` VARCHAR(50) NOT NULL COMMENT '机构的信用代码/varchar(50) ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_org_name` (`org_name`),
  KEY `idx_org_xydm` (`org_xydm`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-机构关联表';

SET FOREIGN_KEY_CHECKS = 1;
