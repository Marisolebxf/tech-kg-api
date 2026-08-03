-- 人才要素库建表 SQL
-- 来源文件：人才要素库(2).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- 长字符索引采用前缀索引，避免 utf8mb4 下超过 MySQL 索引长度限制

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 学者：dwd_scholar
CREATE TABLE IF NOT EXISTS `dwd_scholar` (
  `scholar_id` VARCHAR(32) NOT NULL COMMENT '学者ID/varchar(32) ',
  `name_en` VARCHAR(128) NOT NULL COMMENT '英文姓名/varchar(128) ',
  `name_zh` VARCHAR(128) NOT NULL COMMENT '中文姓名/varchar(128) ',
  `avatar` VARCHAR(256) NOT NULL COMMENT '头像/varchar(256) ',
  `scholar_org_name_en` VARCHAR(4096) NULL COMMENT '英文机构/varchar(4096) ',
  `scholar_org_name_zh` VARCHAR(1024) NULL COMMENT '中文机构/varchar(1024) ',
  `bio` LONGTEXT NULL COMMENT '个人简介/学术简介/longtext ',
  `bio_zh` LONGTEXT NULL COMMENT '个人简介/学术简介（中文）/longtext ',
  `work_experience_date` VARCHAR(100) NULL COMMENT '工作经历起止时间/varchar(100) ',
  `work_experience_institution_en` VARCHAR(255) NULL COMMENT '工作经历单位英文/varchar(255) ',
  `work_experience_department_en` VARCHAR(255) NULL COMMENT '工作经历院系英文/varchar(255) ',
  `work_experience_position_en` VARCHAR(255) NULL COMMENT '工作经历职务英文/varchar(255) ',
  `work_experience_institution_zh` VARCHAR(255) NULL COMMENT '工作经历单位中文/varchar(255) ',
  `work_experience_department_zh` VARCHAR(256) NULL COMMENT '工作经历院系中文/varchar(256) ',
  `work_experience_position_zh` VARCHAR(255) NULL COMMENT '工作经历职务中文/varchar(255) ',
  `education_background_date` VARCHAR(100) NULL COMMENT '教育背景起止时间/varchar(100) ',
  `education_background_institution_en` VARCHAR(500) NULL COMMENT '教育机构英文/varchar(500) ',
  `education_background_degree_en` VARCHAR(255) NULL COMMENT '教育学位英文/varchar(255) ',
  `education_background_institution_zh` VARCHAR(500) NULL COMMENT '教育机构中文/varchar(500) ',
  `education_background_degree_zh` VARCHAR(255) NULL COMMENT '教育学位中文/varchar(255) ',
  `paper_nums` INT NOT NULL COMMENT '论文数量/int ',
  `citation_nums` INT NOT NULL COMMENT '被引数量/int ',
  `h_index` INT NOT NULL COMMENT 'H指数/int ',
  `status` INT NOT NULL COMMENT '状态/int ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_name_en` (`name_en`),
  KEY `idx_name_zh` (`name_zh`),
  KEY `idx_scholar_org_name_en` (`scholar_org_name_en`(191)),
  KEY `idx_scholar_org_name_zh` (`scholar_org_name_zh`(191)),
  KEY `idx_paper_nums` (`paper_nums`),
  KEY `idx_citation_nums` (`citation_nums`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者';

-- 学者人才标识：dwd_scholar_talent_flag
CREATE TABLE IF NOT EXISTS `dwd_scholar_talent_flag` (
  `scholar_id` VARCHAR(32) NOT NULL COMMENT '学者ID/varchar(32) ',
  `academician` VARCHAR(128) NOT NULL COMMENT '是否为院士/varchar(128) ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_academician` (`academician`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者人才标识';

-- 学者研究方向：dwd_scholar_research_direction
CREATE TABLE IF NOT EXISTS `dwd_scholar_research_direction` (
  `scholar_id` VARCHAR(32) NOT NULL COMMENT '学者ID/varchar(32) ',
  `fields` TEXT NULL COMMENT '研究方向/text ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者研究方向';

-- 学者论文关系：dwd_scholar_paper_relation
CREATE TABLE IF NOT EXISTS `dwd_scholar_paper_relation` (
  `paper_id` BIGINT NOT NULL COMMENT '论文ID/bigint ',
  `year` BIGINT NOT NULL COMMENT '论文发表年份/bigint ',
  `scholar_id` VARCHAR(32) NOT NULL COMMENT '学者ID/varchar(32) ',
  `citations` INT NOT NULL COMMENT '被引用次数/int ',
  `publish_time` DATETIME NULL COMMENT '发布时间/datetime ',
  `status` INT NOT NULL COMMENT '状态/int ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  `publication_id` BIGINT NOT NULL COMMENT '期刊ID/bigint ',
  `related_paper_id` BIGINT NOT NULL COMMENT '关联论文库ID/bigint ',
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_citations` (`citations`),
  KEY `idx_publish_time` (`publish_time`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者论文关系';

-- 论文信息：dwd_scholar_papers
CREATE TABLE IF NOT EXISTS `dwd_scholar_papers` (
  `zh_name` VARCHAR(500) NOT NULL COMMENT '中文题目/varchar(500) ',
  `en_name` VARCHAR(500) NOT NULL COMMENT '英文题目/varchar(500) ',
  `authors` TEXT NULL COMMENT '作者列表/text ',
  `paper_url` VARCHAR(1024) NOT NULL COMMENT '论文原始链接/varchar(1024) ',
  `cover_date_start` DATETIME NULL COMMENT '发表时间/datetime ',
  `create_time` DATETIME NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NULL COMMENT '更新时间/datetime ',
  `status` INT NULL COMMENT '状态/int ',
  `zh_abstract` TEXT NULL COMMENT '中文摘要/text ',
  `en_abstract` TEXT NULL COMMENT '英文摘要/text ',
  `doi` VARCHAR(512) NOT NULL COMMENT 'DOI/varchar(512) ',
  `publication_en_name` VARCHAR(1024) NOT NULL COMMENT '期刊/会议英文名/varchar(1024) ',
  KEY `idx_en_name` (`en_name`),
  KEY `idx_cover_date_start` (`cover_date_start`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`),
  KEY `idx_doi` (`doi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='论文信息';

-- 学者合作者关系：dwd_scholar_coauthor
CREATE TABLE IF NOT EXISTS `dwd_scholar_coauthor` (
  `scholar_id` VARCHAR(32) NOT NULL COMMENT '学者ID/varchar(32) ',
  `co_scholar_id` VARCHAR(32) NOT NULL COMMENT '合作学者ID/varchar(32) ',
  `co_scholar_name_en` VARCHAR(256) NULL COMMENT '合作学者英文名/varchar(256) ',
  `co_scholar_name_zh` VARCHAR(128) NULL COMMENT '合作学者中文名/varchar(128) ',
  `co_scholar_avatar` VARCHAR(512) NULL COMMENT '合作学者头像URL/varchar(512) ',
  `co_scholar_org_name_en` VARCHAR(2048) NULL COMMENT '合作学者所属机构英文名/varchar(2048) ',
  `co_scholar_org_name_zh` VARCHAR(1024) NULL COMMENT '合作学者所属机构中文名/varchar(1024) ',
  `co_paper_count` INT NOT NULL COMMENT '合作论文数量/int ',
  `status` INT NOT NULL COMMENT '状态/int ',
  `create_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `update_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_co_scholar_id` (`co_scholar_id`),
  KEY `idx_co_scholar_name_en` (`co_scholar_name_en`),
  KEY `idx_co_scholar_name_zh` (`co_scholar_name_zh`),
  KEY `idx_status` (`status`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者合作者关系';

SET FOREIGN_KEY_CHECKS = 1;
