-- 国外项目要素库建表 SQL
-- 来源文件：国外项目要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- JSON 解析子字段按 Excel 说明合并保存在对应的顶层 JSON 字段中

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 国外项目信息表：dwd_en_project
CREATE TABLE IF NOT EXISTS `dwd_en_project` (
  `id` VARCHAR(64) NOT NULL COMMENT '项目索引/varchar(64) ',
  `project_number` VARCHAR(32) NULL COMMENT '项目编号/varchar(32) ',
  `title` VARCHAR(512) NULL COMMENT '项目名称/varchar(512) ',
  `project_source` VARCHAR(64) NULL COMMENT '项目来源/varchar(64) ',
  `funded_institution` VARCHAR(128) NULL COMMENT '项目受资助机构/varchar(128) ',
  `project_level` VARCHAR(255) NULL COMMENT '项目级别/varchar(255) ',
  `funded_amount` DECIMAL(18,2) NULL COMMENT '受资助金额/decimal(18,2) ',
  `discipline` VARCHAR(256) NULL COMMENT '学科/varchar(256) ',
  `discipline_code` VARCHAR(256) NULL COMMENT '学科代码/varchar(256) ',
  `fund_category` VARCHAR(64) NULL COMMENT '基金类别/varchar(64) ',
  `funded_province` VARCHAR(32) NULL COMMENT '项目受资助地区/varchar(32) ',
  `participating_institution` JSON NULL COMMENT '参与机构/json ',
  `approval_year` INT NULL COMMENT '立项年度/int ',
  `approval_time` DATETIME NULL COMMENT '立项时间/datetime ',
  `research_period` VARCHAR(64) NULL COMMENT '研究期限/varchar(64) ',
  `project_host` VARCHAR(64) NULL COMMENT '项目主持人/varchar(64) ',
  `participants` JSON NULL COMMENT '参与者/json ',
  `keywords` JSON NULL COMMENT '关键词/json ',
  `abstract` LONGTEXT NULL COMMENT '项目标书摘要/longtext ',
  `final_report_abstract` LONGTEXT NULL COMMENT '项目结题摘要/longtext ',
  `project_page_url` TEXT NULL COMMENT '项目页面 URL/text ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_discipline_code` (`discipline_code`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国外项目信息表';

-- 国外项目-产出信息：dwd_en_project_output
-- JSON字段 `output_journal_articles` 子字段：`title`、`authors`、`journal`、`year`、`issue`、`keywords`、`abstract`、`source_url`
-- JSON字段 `output_patents` 子字段：`patent_title`、`patent_inventor`、`patent_number`、`abstract`、`keywords`
-- JSON字段 `output_conference_papers` 子字段：`title`、`authors`、`year`、`name`
-- JSON字段 `output_degree_papers` 子字段：`title`、`authors`、`keywords`
-- JSON字段 `output_clinical_trials` 子字段：`title`、`authors`、`keywords`
-- JSON字段 `output_books` 子字段：`title`、`authors`、`keywords`
-- JSON字段 `output_awards` 子字段：`title`、`authors`、`keywords`
-- JSON字段 `output_reports` 子字段：`title`、`authors`、`keywords`、`abstract`
-- JSON字段 `output_other` 子字段：`title`
CREATE TABLE IF NOT EXISTS `dwd_en_project_output` (
  `id` VARCHAR(64) NOT NULL COMMENT '项目索引/varchar(64) ',
  `total_outputs` INT NULL COMMENT '项目总产出数量/int ',
  `journal_articles_count` INT NULL COMMENT '期刊文章数量/int ',
  `conference_papers_count` INT NULL COMMENT '会议论文数量/int ',
  `degree_papers_count` INT NULL COMMENT '学位论文数量/int ',
  `patents_count` INT NULL COMMENT '专利数量/int ',
  `clinical_trials_count` INT NULL COMMENT '临床试验数量/int ',
  `books_count` INT NULL COMMENT '图书专著数量/int ',
  `awards_count` INT NULL COMMENT '奖项数量/int ',
  `reports_count` INT NULL COMMENT '报告数量/int ',
  `other_outputs_count` INT NULL COMMENT '其他产出数量/int ',
  `output_journal_articles` JSON NULL COMMENT '产出的期刊文章标题/json ',
  `output_patents` JSON NULL COMMENT '产出的专利标题/json ',
  `output_conference_papers` JSON NULL COMMENT '产出的会议论文标题/json ',
  `output_degree_papers` JSON NULL COMMENT '产出的学位论文标题/json ',
  `output_clinical_trials` JSON NULL COMMENT '产出的临床试验信息/json ',
  `output_books` JSON NULL COMMENT '产出的图书专著信息/json ',
  `output_awards` JSON NULL COMMENT '产出的奖项信息/json ',
  `output_reports` JSON NULL COMMENT '产出的报告信息/json ',
  `output_other` JSON NULL COMMENT '其他产出信息/json ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国外项目-产出信息';

SET FOREIGN_KEY_CHECKS = 1;
