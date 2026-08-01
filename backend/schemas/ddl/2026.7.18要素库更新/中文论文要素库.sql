-- 中文论文要素库建表 SQL
-- 来源文件：中文论文要素库(2).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型
-- 同一表内重复字段名：首次保留原名，后续依次追加 _2、_3……
-- 长字符或文本索引使用前缀索引；JSON 字段不直接创建普通 B-Tree 索引。

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 中文论文详情信息：dwd_zh_paper
CREATE TABLE IF NOT EXISTS `dwd_zh_paper` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `doi` VARCHAR(512) NULL COMMENT '论文唯一识别号/varchar(512) ',
  `en_name` VARCHAR(1024) NULL COMMENT '文献英文题名/varchar(1024) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '文献中文题名/varchar(1024) ',
  `publication_id` BIGINT NOT NULL COMMENT '关联出版物信息/bigint ',
  `paper_type` VARCHAR(255) NULL COMMENT '文献类型/varchar(255) ',
  `publication_type` VARCHAR(255) NULL COMMENT '出版刊物类型/varchar(255) ',
  `publication_zh_name` VARCHAR(1024) NULL COMMENT '出版物中文名/varchar(1024) ',
  `issn` VARCHAR(16) NULL COMMENT 'ISSN/varchar(16) ',
  `volume` VARCHAR(128) NULL COMMENT '文献所在期刊的卷号/varchar(128) ',
  `issue` VARCHAR(128) NULL COMMENT '文献所在期刊的期号/varchar(128) ',
  `first_page` VARCHAR(255) NULL COMMENT '论文在期刊的首页-页码/varchar(255) ',
  `last_page` VARCHAR(255) NULL COMMENT '论文在期刊的末尾页-页码/varchar(255) ',
  `cover_year_start` VARCHAR(4) NULL COMMENT '文献发表年份/varchar(4) ',
  `cover_date_start` VARCHAR(255) NULL COMMENT '文献发表日期/varchar(255) ',
  `language_classify` TINYINT NULL COMMENT '语言/tinyint ',
  `abstract_available` VARCHAR(1) NULL COMMENT '摘要是否可用/varchar(1) ',
  `open_access` TINYINT NULL COMMENT '是否OA/tinyint ',
  `paper_url` TEXT NULL COMMENT '数据来源链接/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_en_name` (`en_name`(191)),
  KEY `idx_zh_name` (`zh_name`(191)),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文详情信息';

-- 中文论文标题信息：ods_zh_paper_title
CREATE TABLE IF NOT EXISTS `ods_zh_paper_title` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文标题信息';

-- 中文论文标题信息：dwd_zh_paper_title
CREATE TABLE IF NOT EXISTS `dwd_zh_paper_title` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `title_sequence` INT NOT NULL COMMENT '标题序号/int ',
  `en_name` VARCHAR(1024) NULL COMMENT '文献英文名/varchar(1024) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '文献中文名/varchar(1024) ',
  `language_code` VARCHAR(12) NULL COMMENT '语言代码/varchar(12) ',
  `language` VARCHAR(255) NULL COMMENT '语种/varchar(255) ',
  `original_title` VARCHAR(1) NULL COMMENT '是否原始标题/varchar(1) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_title_sequence` (`title_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文标题信息';

-- 中文论文摘要信息：ods_zh_paper_abstract
CREATE TABLE IF NOT EXISTS `ods_zh_paper_abstract` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文摘要信息';

-- 中文论文摘要信息：dwd_zh_paper_abstract
CREATE TABLE IF NOT EXISTS `dwd_zh_paper_abstract` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `abstract_sequence` INT NOT NULL COMMENT '摘要序号/int ',
  `language` VARCHAR(255) NULL COMMENT '语种/varchar(255) ',
  `original_abstract` VARCHAR(1) NOT NULL COMMENT '是否原始摘要/varchar(1) ',
  `en_abstract` LONGTEXT NULL COMMENT '摘要 英文/longtext ',
  `zh_abstract` LONGTEXT NULL COMMENT '摘要 中文/longtext ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_abstract_sequence` (`abstract_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文摘要信息';

-- 中文文献作者详情信息：ods_zh_paper_author
CREATE TABLE IF NOT EXISTS `ods_zh_paper_author` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文文献作者详情信息';

-- 中文文献作者详情信息：dwd_zh_author
CREATE TABLE IF NOT EXISTS `dwd_zh_author` (
  `paper_id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `author_sequence` INT NOT NULL COMMENT '作者顺序/int ',
  `author_id` VARCHAR(32) NOT NULL COMMENT '文献作者 id/varchar(32) ',
  `en_name` VARCHAR(255) NOT NULL COMMENT '文献作者英文名/varchar(255) ',
  `zh_name` VARCHAR(255) NULL COMMENT '文献作者中文名/varchar(255) ',
  `email` JSON NULL COMMENT '文献作者email/json ',
  `correspond` TINYINT NULL COMMENT '是否为通讯作者/tinyint ',
  `institution` TEXT NULL COMMENT '作者单位名称/text ',
  `affiliation` JSON NULL COMMENT '文献作者地址/json ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_author_sequence` (`author_sequence`),
  KEY `idx_author_id` (`author_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文文献作者详情信息';

-- 中文期刊详情信息：ods_zh_journal
CREATE TABLE IF NOT EXISTS `ods_zh_journal` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文期刊详情信息';

-- 中文期刊详情信息：dwd_zh_journal
CREATE TABLE IF NOT EXISTS `dwd_zh_journal` (
  `paper_id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` BIGINT NOT NULL COMMENT '期刊id/bigint ',
  `publication_type` VARCHAR(255) NULL COMMENT '出版刊物类别/varchar(255) ',
  `country` VARCHAR(255) NULL COMMENT '国家/varchar(255) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '期刊名（中文）/varchar(1024) ',
  `name_abbr` VARCHAR(255) NULL COMMENT '简称/varchar(255) ',
  `en_name` VARCHAR(1024) NULL COMMENT '期刊名（英文）/varchar(1024) ',
  `iscn` VARCHAR(16) NULL COMMENT '国内刊号/varchar(16) ',
  `issn` VARCHAR(16) NULL COMMENT 'ISSN/varchar(16) ',
  `eissn` VARCHAR(16) NULL COMMENT 'EISSN/varchar(16) ',
  `founding_time` INT NULL COMMENT '创刊时间/int ',
  `jn_official` TEXT NULL COMMENT '期刊官网/text ',
  `zh_description` TEXT NULL COMMENT '期刊描述/text ',
  `format` TEXT NULL COMMENT '开本/text ',
  `postal_code` VARCHAR(32) NULL COMMENT '邮发代号/varchar(32) ',
  `chief_editor` VARCHAR(128) NULL COMMENT '主编/varchar(128) ',
  `organizer` VARCHAR(1024) NULL COMMENT '主办单位/varchar(1024) ',
  `publisher_place` VARCHAR(64) NULL COMMENT '出版地/varchar(64) ',
  `award` TEXT NULL COMMENT '获奖情况/text ',
  `cite_nums` INT NULL COMMENT '被引用量/int ',
  `annual_publication` INT NULL COMMENT '年文章数/int ',
  `review` TINYINT NULL COMMENT '是否为综述性期刊/tinyint ',
  `impact_factor` DOUBLE NULL COMMENT '分区/double ',
  `sub_quartile` TINYINT NULL COMMENT '分类号/tinyint ',
  `classify_list` TEXT NULL COMMENT 'classify_list/text ',
  `warning` TINYINT NULL COMMENT '是否预警/tinyint ',
  `is_sci` TINYINT NULL COMMENT '是否SCI/tinyint ',
  `publication_cycle` VARCHAR(64) NULL COMMENT '出版周期/varchar(64) ',
  `paper_nums` INT NULL COMMENT '出版论文量/int ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_zh_name` (`zh_name`(191)),
  KEY `idx_name_abbr` (`name_abbr`),
  KEY `idx_en_name` (`en_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文期刊详情信息';

-- 中文论文参考文献信息：ods_zh_paper_reference
CREATE TABLE IF NOT EXISTS `ods_zh_paper_reference` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文参考文献信息';

-- 中文论文参考文献信息：dwd_zh_paper_reference
CREATE TABLE IF NOT EXISTS `dwd_zh_paper_reference` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` BIGINT NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` VARCHAR(512) NOT NULL COMMENT '参考文献唯一识别号/varchar(512) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '参考文献中文名/varchar(1024) ',
  `publication_zh_name` VARCHAR(1024) NULL COMMENT '参考文献出版物中文名/varchar(1024) ',
  `cover_year_start` VARCHAR(4) NULL COMMENT '参考文献发表年份/varchar(4) ',
  `volume` VARCHAR(128) NULL COMMENT '参考文献所在期刊的卷号/varchar(128) ',
  `issue` VARCHAR(128) NULL COMMENT '参考文献所在期刊的期号/varchar(128) ',
  `first_page` VARCHAR(255) NULL COMMENT '参考文献在期刊的首页-页码/varchar(255) ',
  `last_page` VARCHAR(255) NULL COMMENT '参考文献在期刊的末尾页-页码/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191)),
  KEY `idx_cover_year_start` (`cover_year_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文参考文献信息';

-- 中文论文引用文献信息：dwd_zh_paper_citation
CREATE TABLE IF NOT EXISTS `dwd_zh_paper_citation` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` BIGINT NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` VARCHAR(512) NOT NULL COMMENT '引用文献唯一识别号/varchar(512) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '引用文献中文名/varchar(1024) ',
  `publication_zh_name` VARCHAR(1024) NULL COMMENT '引用文献出版物中文名/varchar(1024) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文引用文献信息';

-- 中文论文分类信息：ods_zh_paper_classification
CREATE TABLE IF NOT EXISTS `ods_zh_paper_classification` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文分类信息';

-- 中文论文分类信息：dwd_zh_paper_classification
CREATE TABLE IF NOT EXISTS `dwd_zh_paper_classification` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `scope` VARCHAR(20) NULL COMMENT '大类学科分类/varchar(20) ',
  `scope_zone` VARCHAR(20) NULL COMMENT '小类学科分类/varchar(20) ',
  `keywords` LONGTEXT NULL COMMENT '论文关键字/longtext ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文分类信息';

-- 中文论文关联文献信息：dwd_zh_paper_related
CREATE TABLE IF NOT EXISTS `dwd_zh_paper_related` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `relevant` JSON NULL COMMENT '相关文献/json ',
  `doi` VARCHAR(512) NOT NULL COMMENT '相关文献文献唯一识别号/varchar(512) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '相关文献中文名/varchar(1024) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文关联文献信息';

SET FOREIGN_KEY_CHECKS = 1;
