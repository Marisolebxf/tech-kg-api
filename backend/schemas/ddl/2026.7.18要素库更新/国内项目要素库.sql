-- 国内项目要素库建表 SQL
-- 来源文件：国内项目要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- JSON 解析子字段按 Excel 说明合并保存在对应的顶层 JSON 字段中

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 国内项目信息表：dwd_zh_project
CREATE TABLE IF NOT EXISTS `dwd_zh_project` (
  `id` VARCHAR(255) NOT NULL COMMENT '项目索引/varchar(255) ',
  `project_number` VARCHAR(255) NULL COMMENT '项目编号/varchar(255) ',
  `title` VARCHAR(255) NULL COMMENT '项目名称/varchar(255) ',
  `project_source` VARCHAR(255) NULL COMMENT '项目来源/varchar(255) ',
  `funded_institution` VARCHAR(255) NULL COMMENT '项目受资助机构/varchar(255) ',
  `project_level` VARCHAR(255) NULL COMMENT '项目级别/varchar(255) ',
  `funded_amount` DECIMAL(18,2) NULL COMMENT '受资助金额/decimal(18,2) ',
  `discipline` VARCHAR(255) NULL COMMENT '学科/varchar(255) ',
  `discipline_code` VARCHAR(255) NULL COMMENT '学科代码/varchar(255) ',
  `fund_category` VARCHAR(255) NULL COMMENT '基金类别/varchar(255) ',
  `funded_province` VARCHAR(255) NULL COMMENT '项目受资助省/varchar(255) ',
  `participating_institution` JSON NULL COMMENT '参与机构/json ',
  `approval_year` INT NULL COMMENT '立项年度/int ',
  `approval_time` DATETIME NULL COMMENT '立项时间/datetime ',
  `research_period` VARCHAR(255) NULL COMMENT '研究期限/varchar(255) ',
  `project_host` VARCHAR(255) NULL COMMENT '项目主持人/varchar(255) ',
  `participants` JSON NULL COMMENT '参与者/json ',
  `keywords` JSON NULL COMMENT '关键词/json ',
  `abstract` TEXT NULL COMMENT '项目标书摘要/text ',
  `final_report_abstract` TEXT NULL COMMENT '项目结题摘要/text ',
  `project_page_url` TEXT NULL COMMENT '项目页面 URL/text ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_discipline_code` (`discipline_code`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内项目信息表';

-- 国内项目-产出信息：dwd_zh_project_output
-- JSON字段 `output_journal_articles` 子字段：`title`、`authors`、`journal`、`year`、`issue`、`keywords`、`abstract`、`source_url`、`doi`、`indexed_by`、`volume`、`pages`、`publish_date`、`oa_flag`
-- JSON字段 `output_patents` 子字段：`patent_title`、`patent_inventor`、`patent_number`、`abstract`、`keywords`、`patent_authority`、`grant_date`、`grant_region`
-- JSON字段 `output_conference_papers` 子字段：`title`、`authors`、`year`、`name`、`doi`、`publish_date`、`abstract`、`keywords`、`oa_flag`
-- JSON字段 `output_degree_papers` 子字段：`title`、`authors`、`keywords`
-- JSON字段 `output_books` 子字段：`title`、`authors`、`keywords`、`publisher`、`publish_date`、`language`、`country`、`page_range`
-- JSON字段 `output_awards` 子字段：`title`、`authors`、`keywords`、`awarding_body`、`award_date`、`award_type`、`award_level`
-- JSON字段 `output_reports` 子字段：`title`、`authors`、`keywords`、`abstract`
-- JSON字段 `output_other` 子字段：`title`、`authors`、`keywords`
CREATE TABLE IF NOT EXISTS `dwd_zh_project_output` (
  `id` VARCHAR(255) NOT NULL COMMENT '项目索引/varchar(255) ',
  `total_outputs` INT NULL COMMENT '项目总产出数量/int ',
  `journal_articles_count` INT NULL COMMENT '期刊文章数量/int ',
  `conference_papers_count` INT NULL COMMENT '会议论文数量/int ',
  `degree_papers_count` INT NULL COMMENT '学位论文数量/int ',
  `patents_count` INT NULL COMMENT '专利数量/int ',
  `books_count` INT NULL COMMENT '图书专著数量/int ',
  `awards_count` INT NULL COMMENT '奖项数量/int ',
  `reports_count` INT NULL COMMENT '报告数量/int ',
  `other_outputs_count` INT NULL COMMENT '其他产出数量/int ',
  `output_journal_articles` JSON NULL COMMENT '产出的期刊文章标题/json ',
  `output_patents` JSON NULL COMMENT '产出的专利标题/json ',
  `output_conference_papers` JSON NULL COMMENT '产出的会议论文标题/json ',
  `output_degree_papers` JSON NULL COMMENT '产出的学位论文标题/json ',
  `output_books` JSON NULL COMMENT '产出的图书专著标题/json ',
  `output_awards` JSON NULL COMMENT '产出的奖项标题/json ',
  `output_reports` JSON NULL COMMENT '产出的报告标题/json ',
  `output_other` JSON NULL COMMENT '其他产出标题/json ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内项目-产出信息';

SET FOREIGN_KEY_CHECKS = 1;
