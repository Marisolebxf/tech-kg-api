-- 外文论文要素库建表 SQL
-- 来源文件：外文论文要素库(1).xlsx
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

-- 英文论文详情信息：dwd_en_paper
CREATE TABLE IF NOT EXISTS `dwd_en_paper` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `doi` VARCHAR(512) NOT NULL COMMENT '论文唯一识别号/varchar(512) ',
  `en_name` VARCHAR(1024) NULL COMMENT '文献英文名/varchar(1024) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '文献中文名/varchar(1024) ',
  `publication_id` BIGINT NOT NULL COMMENT '关联出版物信息/bigint ',
  `paper_type` VARCHAR(255) NULL COMMENT '文献类型/varchar(255) ',
  `publication_type` VARCHAR(255) NULL COMMENT '出版刊物类型/varchar(255) ',
  `publication_en_name` VARCHAR(1024) NULL COMMENT '出版物英文名/varchar(1024) ',
  `issn_print` VARCHAR(16) NULL COMMENT 'ISSN/varchar(16) ',
  `issn_online` VARCHAR(16) NULL COMMENT 'EISSN/varchar(16) ',
  `volume` VARCHAR(128) NULL COMMENT '文献所在期刊的卷号/varchar(128) ',
  `issue` VARCHAR(128) NULL COMMENT '文献所在期刊的期号/varchar(128) ',
  `first_page` VARCHAR(255) NULL COMMENT '论文在期刊的首页-页码/varchar(255) ',
  `last_page` VARCHAR(255) NULL COMMENT '论文在期刊的末尾页-页码/varchar(255) ',
  `cover_year_start` VARCHAR(4) NULL COMMENT '文献发表年份/varchar(4) ',
  `cover_date_start` DATETIME NULL COMMENT '文献发表时间/datetime ',
  `language` VARCHAR(255) NULL COMMENT '语种/varchar(255) ',
  `abstract_available` TINYINT NULL COMMENT '摘要是否可用/tinyint ',
  `open_access` TINYINT NULL COMMENT '是否OA/tinyint ',
  `paper_url` TEXT NULL COMMENT '文献官网链接/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_paper_type` (`paper_type`),
  KEY `idx_publication_en_name` (`publication_en_name`(191)),
  KEY `idx_issn_print` (`issn_print`),
  KEY `idx_issn_online` (`issn_online`),
  KEY `idx_cover_year_start` (`cover_year_start`),
  KEY `idx_cover_date_start` (`cover_date_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文详情信息';

-- 英文论文详情信息：ods_en_paper
CREATE TABLE IF NOT EXISTS `ods_en_paper` (
  `pmid` VARCHAR(64) NOT NULL COMMENT 'PubMed标识符。/varchar(64) ',
  KEY `idx_pmid` (`pmid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文详情信息';

-- 英文论文标题信息：dwd_en_paper_title
CREATE TABLE IF NOT EXISTS `dwd_en_paper_title` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `title_sequence` INT NOT NULL COMMENT '标题序号/int ',
  `en_name` VARCHAR(1024) NULL COMMENT '文献英文名/varchar(1024) ',
  `zh_name` VARCHAR(1024) NULL COMMENT '文献中文名/varchar(1024) ',
  `language_code` VARCHAR(12) NULL COMMENT '语言代码/varchar(12) ',
  `language` VARCHAR(255) NULL COMMENT '语种/varchar(255) ',
  `original_title` TINYINT NULL COMMENT '是否原始标题/tinyint ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_title_sequence` (`title_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文标题信息';

-- 英文论文标题信息：ods_en_paper_title
CREATE TABLE IF NOT EXISTS `ods_en_paper_title` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文标题信息';

-- 英文论文摘要信息：dwd_en_paper_abstract
CREATE TABLE IF NOT EXISTS `dwd_en_paper_abstract` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `abstract_sequence` INT NOT NULL COMMENT '摘要序号/int ',
  `language` VARCHAR(255) NULL COMMENT '语种/varchar(255) ',
  `original_abstract` TINYINT NOT NULL COMMENT '是否原始摘要/tinyint ',
  `en_abstract` LONGTEXT NULL COMMENT '摘要 英文/longtext ',
  `zh_abstract` LONGTEXT NULL COMMENT '摘要 中文/longtext ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_abstract_sequence` (`abstract_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文摘要信息';

-- 英文论文摘要信息：ods_en_paper_abstract
CREATE TABLE IF NOT EXISTS `ods_en_paper_abstract` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  `abstract_source` VARCHAR(128) NOT NULL COMMENT '摘要来源/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文摘要信息';

-- 英文文献作者详情信息：dwd_en_author
CREATE TABLE IF NOT EXISTS `dwd_en_author` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文文献作者详情信息';

-- 英文文献作者详情信息：ods_en_author
CREATE TABLE IF NOT EXISTS `ods_en_author` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  `orcid` VARCHAR(64) NOT NULL COMMENT '作者ORCID。/varchar(64) ',
  `author_type` VARCHAR(32) NOT NULL COMMENT '作者类型/varchar(32) ',
  `surname` VARCHAR(255) NOT NULL COMMENT '作者姓/varchar(255) ',
  `given_name` VARCHAR(255) NOT NULL COMMENT '作者名/varchar(255) ',
  `initials` VARCHAR(32) NOT NULL COMMENT '作者姓名首字母/varchar(32) ',
  `preferred_name` VARCHAR(255) NOT NULL COMMENT '作者首选姓名/varchar(255) ',
  `city` VARCHAR(255) NOT NULL COMMENT '文献作者单位所在城市/varchar(255) ',
  `state` VARCHAR(255) NOT NULL COMMENT '文献作者单位所在州或省/varchar(255) ',
  `postal_code` VARCHAR(64) NOT NULL COMMENT '文献作者单位邮政编码/varchar(64) ',
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_orcid` (`orcid`),
  KEY `idx_surname` (`surname`),
  KEY `idx_given_name` (`given_name`),
  KEY `idx_preferred_name` (`preferred_name`),
  KEY `idx_city` (`city`),
  KEY `idx_state` (`state`),
  KEY `idx_postal_code` (`postal_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文文献作者详情信息';

-- 英文期刊详情信息：dwd_en_journal
CREATE TABLE IF NOT EXISTS `dwd_en_journal` (
  `publication_id` BIGINT NOT NULL COMMENT '期刊id/bigint ',
  `publication_type` VARCHAR(255) NULL COMMENT '出版刊物类型/varchar(255) ',
  `country` VARCHAR(255) NULL COMMENT '出版国家/地区/varchar(255) ',
  `en_name` VARCHAR(1024) NULL COMMENT '期刊名/顶会/预印本名（英文）/varchar(1024) ',
  `name_abbr` VARCHAR(255) NULL COMMENT '简称/varchar(255) ',
  `issn_print` VARCHAR(16) NULL COMMENT 'ISSN/varchar(16) ',
  `issn_online` VARCHAR(16) NULL COMMENT 'EISSN/varchar(16) ',
  `jn_official` TEXT NULL COMMENT '期刊官网/text ',
  `en_description` TEXT NULL COMMENT '期刊描述/text ',
  `establish_time` INT NULL COMMENT '创刊时间/int ',
  `annual_publication` INT NULL COMMENT '年文量数/int ',
  `review` TINYINT NULL COMMENT '是否为综述性期刊/tinyint ',
  `impact_factor` DOUBLE NULL COMMENT '影响指数/double ',
  `jcr_zone` VARCHAR(2) NULL COMMENT '分区/varchar(2) ',
  `review_period` VARCHAR(255) NULL COMMENT '平均审稿周期/varchar(255) ',
  `self_rate` DOUBLE NULL COMMENT '自引率/double ',
  `top` TINYINT NULL COMMENT '是否顶刊/tinyint ',
  `warning` TINYINT NULL COMMENT '是否预警/tinyint ',
  `is_sci` TINYINT NULL COMMENT '是否SCI/tinyint ',
  `publish_period` VARCHAR(64) NULL COMMENT '出版周期/varchar(64) ',
  `layout_cost` VARCHAR(15) NULL COMMENT '版面费/varchar(15) ',
  `paper_nums` INT NULL COMMENT '出版论文量/int ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_en_name` (`en_name`(191)),
  KEY `idx_name_abbr` (`name_abbr`),
  KEY `idx_issn_print` (`issn_print`),
  KEY `idx_issn_online` (`issn_online`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文期刊详情信息';

-- 英文期刊详情信息：ods_en_journal
CREATE TABLE IF NOT EXISTS `ods_en_journal` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识/varchar(64) ',
  `publisher_name` VARCHAR(255) NOT NULL COMMENT '期刊出版商名称/varchar(255) ',
  `correspond_method` VARCHAR(255) NOT NULL COMMENT '通讯方式/varchar(255) ',
  `zh_description` TEXT NOT NULL COMMENT '期刊描述，中文描述/text ',
  `quartile` TINYINT NOT NULL COMMENT '中国科学院期刊分区/tinyint ',
  `jci` DOUBLE NOT NULL COMMENT 'JCI期刊引文指标/double ',
  `oa_quote_rate` DOUBLE NOT NULL COMMENT '期刊OA文献被引用占比/double ',
  `article_rate` DOUBLE NOT NULL COMMENT '期刊的研究性文章占比/double ',
  `correct_rate` DOUBLE NOT NULL COMMENT '期刊出版后修正文章占比/double ',
  `revoke_rate` DOUBLE NOT NULL COMMENT '期刊文献撤稿占比/double ',
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_paper_id` (`paper_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文期刊详情信息';

-- 英文论文参考文献信息：dwd_en_paper_reference
CREATE TABLE IF NOT EXISTS `dwd_en_paper_reference` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` BIGINT NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` VARCHAR(512) NOT NULL COMMENT '参考文献唯一识别号/varchar(512) ',
  `en_name` VARCHAR(1024) NULL COMMENT '参考文献英文名/varchar(1024) ',
  `publication_en_name` VARCHAR(1024) NULL COMMENT '参考文献出版物英文名/varchar(1024) ',
  `cover_year_start` VARCHAR(4) NULL COMMENT '文献发表年份/varchar(4) ',
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
  KEY `idx_publication_en_name` (`publication_en_name`(191)),
  KEY `idx_cover_year_start` (`cover_year_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文参考文献信息';

-- 英文论文参考文献信息：ods_en_paper_reference
CREATE TABLE IF NOT EXISTS `ods_en_paper_reference` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文参考文献信息';

-- 英文论文引用文献信息：dwd_en_paper_citation
CREATE TABLE IF NOT EXISTS `dwd_en_paper_citation` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` BIGINT NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` VARCHAR(512) NOT NULL COMMENT '引用文献唯一识别号/varchar(512) ',
  `en_name` VARCHAR(1024) NULL COMMENT '引用文献英文名/varchar(1024) ',
  `publication_en_name` VARCHAR(1024) NULL COMMENT '引用文献出版物英文名/varchar(1024) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_en_name` (`publication_en_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文引用文献信息';

-- 英文论文引用文献信息：ods_en_paper_citation
CREATE TABLE IF NOT EXISTS `ods_en_paper_citation` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文引用文献信息';

-- 英文论文基金信息：dwd_en_paper_funding
CREATE TABLE IF NOT EXISTS `dwd_en_paper_funding` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `funds` LONGTEXT NULL COMMENT '基金/longtext ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文基金信息';

-- 英文论文基金信息：ods_en_paper_funding
CREATE TABLE IF NOT EXISTS `ods_en_paper_funding` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文基金信息';

-- 英文论文分类信息：dwd_en_paper_classification
-- 重复字段 `created_time` 调整为：`created_time`、`created_time_2`
-- 重复字段 `updated_time` 调整为：`updated_time`、`updated_time_2`
CREATE TABLE IF NOT EXISTS `dwd_en_paper_classification` (
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `scope` VARCHAR(20) NULL COMMENT '大类学科领域/varchar(20) ',
  `sub_scope` VARCHAR(20) NULL COMMENT '小类学科主题/varchar(20) ',
  `keywords` JSON NULL COMMENT '论文关键词/json ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  `created_time_2` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time_2` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文分类信息';

-- 英文论文分类信息：ods_en_paper_classification
CREATE TABLE IF NOT EXISTS `ods_en_paper_classification` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文分类信息';

-- 英文论文关联文献信息：dwd_en_paper_related
CREATE TABLE IF NOT EXISTS `dwd_en_paper_related` (
  `logic_id` VARCHAR(128) NOT NULL COMMENT '逻辑主键/varchar(128) ',
  `id` VARCHAR(64) NOT NULL COMMENT '文献id/varchar(64) ',
  `relevant` JSON NULL COMMENT '相关文献/json ',
  `doi` VARCHAR(512) NOT NULL COMMENT '相关文献文献唯一识别号/varchar(512) ',
  `en_name` VARCHAR(1024) NULL COMMENT '相关文献英文名/varchar(1024) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文关联文献信息';

SET FOREIGN_KEY_CHECKS = 1;
