# 图谱 ETL 源表 MySQL 建表语句（九大业务模块）

> 覆盖九大业务模块图数据抽取脚本实际消费的 MySQL 源表 DDL，共 66 张，取自 dev 共享 MySQL（`host.docker.internal:30306`，库 `gkx_element`）实测 `SHOW CREATE TABLE`（2026-09-22）。用于在空库重建源表、验证各抽取脚本可行性与完整性。行数为导出时实测。

> 收录口径：模块服务代码中实际读取的边类型/点类型 → 反推装载该边/点的 ETL 脚本 → 该脚本读的源表（硬依赖闭包，含边端点必须预先存在的实体表）。未收录表见文末。

> ⚠️ **核查反馈（2026-09-22，待修订）**：经对本仓库代码逐条核对，本文"硬依赖闭包（66 张）"**不成立**——另有 9 张注入脚本硬依赖的表与 1 个探针列未收录，"未收录的表"一节多条排除理由与代码事实相反。**补齐前请勿以本文为空库重建源表 / 验证抽取脚本可行性的依据**；实际硬依赖应为 75 张表 + 1 列。明细与证据见文末「核查反馈」一节。

## 学者域（load_scholar_entities / load_scholar_relations → Person + AFFILIATED_WITH / COAUTHOR_WITH / STUDIED_AT / AUTHORED_BY）

### `dwd_scholar`（2175 行）

```sql
CREATE TABLE `dwd_scholar` (
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `name_en` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '英文姓名/varchar(128) ',
  `name_zh` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '中文姓名/varchar(128) ',
  `avatar` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '头像/varchar(256) ',
  `scholar_org_name_en` varchar(4096) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '英文机构/varchar(4096) ',
  `scholar_org_name_zh` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '中文机构/varchar(1024) ',
  `bio` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '个人简介/学术简介/longtext ',
  `bio_zh` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '个人简介/学术简介（中文）/longtext ',
  `work_experience_date` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历起止时间/varchar(100) ',
  `work_experience_institution_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历单位英文/varchar(255) ',
  `work_experience_department_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历院系英文/varchar(255) ',
  `work_experience_position_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历职务英文/varchar(255) ',
  `work_experience_institution_zh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历单位中文/varchar(255) ',
  `work_experience_department_zh` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历院系中文/varchar(256) ',
  `work_experience_position_zh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '工作经历职务中文/varchar(255) ',
  `education_background_date` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '教育背景起止时间/varchar(100) ',
  `education_background_institution_en` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '教育机构英文/varchar(500) ',
  `education_background_degree_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '教育学位英文/varchar(255) ',
  `education_background_institution_zh` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '教育机构中文/varchar(500) ',
  `education_background_degree_zh` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '教育学位中文/varchar(255) ',
  `paper_nums` int NOT NULL COMMENT '论文数量/int ',
  `citation_nums` int NOT NULL COMMENT '被引数量/int ',
  `h_index` int NOT NULL COMMENT 'H指数/int ',
  `status` int NOT NULL COMMENT '状态/int ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
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
```

### `dwd_scholar_talent_flag`（2075 行）

```sql
CREATE TABLE `dwd_scholar_talent_flag` (
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `academician` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '是否为院士/varchar(128) ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_academician` (`academician`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者人才标识';
```

### `dwd_scholar_research_direction`（2155 行）

```sql
CREATE TABLE `dwd_scholar_research_direction` (
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `fields` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '研究方向/text ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者研究方向';
```

### `dwd_scholar_coauthor`（156542 行）

```sql
CREATE TABLE `dwd_scholar_coauthor` (
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `co_scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '合作学者ID/varchar(32) ',
  `co_scholar_name_en` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合作学者英文名/varchar(256) ',
  `co_scholar_name_zh` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合作学者中文名/varchar(128) ',
  `co_scholar_avatar` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合作学者头像URL/varchar(512) ',
  `co_scholar_org_name_en` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合作学者所属机构英文名/varchar(2048) ',
  `co_scholar_org_name_zh` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合作学者所属机构中文名/varchar(1024) ',
  `co_paper_count` int NOT NULL COMMENT '合作论文数量/int ',
  `status` int NOT NULL COMMENT '状态/int ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_co_scholar_id` (`co_scholar_id`),
  KEY `idx_co_scholar_name_en` (`co_scholar_name_en`),
  KEY `idx_co_scholar_name_zh` (`co_scholar_name_zh`),
  KEY `idx_status` (`status`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者合作者关系';
```

### `dwd_scholar_paper_relation`（345324 行）

```sql
CREATE TABLE `dwd_scholar_paper_relation` (
  `paper_id` bigint NOT NULL COMMENT '论文ID/bigint ',
  `year` bigint NOT NULL COMMENT '论文发表年份/bigint ',
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `citations` int NOT NULL COMMENT '被引用次数/int ',
  `publish_time` datetime DEFAULT NULL COMMENT '发布时间/datetime ',
  `status` int NOT NULL COMMENT '状态/int ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `publication_id` bigint NOT NULL COMMENT '期刊ID/bigint ',
  `related_paper_id` bigint NOT NULL COMMENT '关联论文库ID/bigint ',
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_citations` (`citations`),
  KEY `idx_publish_time` (`publish_time`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者论文关系';
```

## 论文期刊域（load_paper_journal_graph / paper_journal_relation → Paper / Journal / 作者Person + AUTHORED_BY / PUBLISHED_IN / CITES / CITED_BY / RELATED_TO / HAS_KEYWORD）

### `dwd_zh_paper`（2000 行）

```sql
CREATE TABLE `dwd_zh_paper` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '论文唯一识别号/varchar(512) ',
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献英文题名/varchar(1024) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献中文题名/varchar(1024) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `paper_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献类型/varchar(255) ',
  `publication_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版刊物类型/varchar(255) ',
  `publication_zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版物中文名/varchar(1024) ',
  `issn` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'ISSN/varchar(16) ',
  `volume` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献所在期刊的卷号/varchar(128) ',
  `issue` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献所在期刊的期号/varchar(128) ',
  `first_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '论文在期刊的首页-页码/varchar(255) ',
  `last_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '论文在期刊的末尾页-页码/varchar(255) ',
  `cover_year_start` varchar(4) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献发表年份/varchar(4) ',
  `cover_date_start` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献发表日期/varchar(255) ',
  `language_classify` tinyint DEFAULT NULL COMMENT '语言/tinyint ',
  `abstract_available` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '摘要是否可用/varchar(1) ',
  `open_access` tinyint DEFAULT NULL COMMENT '是否OA/tinyint ',
  `paper_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '数据来源链接/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_en_name` (`en_name`(191)),
  KEY `idx_zh_name` (`zh_name`(191)),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文详情信息';
```

### `dwd_en_paper`（2000 行）

```sql
CREATE TABLE `dwd_en_paper` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '论文唯一识别号/varchar(512) ',
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献英文名/varchar(1024) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献中文名/varchar(1024) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `paper_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献类型/varchar(255) ',
  `publication_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版刊物类型/varchar(255) ',
  `publication_en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版物英文名/varchar(1024) ',
  `issn_print` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'ISSN/varchar(16) ',
  `issn_online` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'EISSN/varchar(16) ',
  `volume` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献所在期刊的卷号/varchar(128) ',
  `issue` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献所在期刊的期号/varchar(128) ',
  `first_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '论文在期刊的首页-页码/varchar(255) ',
  `last_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '论文在期刊的末尾页-页码/varchar(255) ',
  `cover_year_start` varchar(4) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献发表年份/varchar(4) ',
  `cover_date_start` datetime DEFAULT NULL COMMENT '文献发表时间/datetime ',
  `language` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语种/varchar(255) ',
  `abstract_available` tinyint DEFAULT NULL COMMENT '摘要是否可用/tinyint ',
  `open_access` tinyint DEFAULT NULL COMMENT '是否OA/tinyint ',
  `paper_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '文献官网链接/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
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
```

### `dwd_zh_journal`（2080 行）

```sql
CREATE TABLE `dwd_zh_journal` (
  `paper_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '期刊id/bigint ',
  `publication_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版刊物类别/varchar(255) ',
  `country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '国家/varchar(255) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '期刊名（中文）/varchar(1024) ',
  `name_abbr` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '简称/varchar(255) ',
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '期刊名（英文）/varchar(1024) ',
  `iscn` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '国内刊号/varchar(16) ',
  `issn` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'ISSN/varchar(16) ',
  `eissn` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'EISSN/varchar(16) ',
  `founding_time` int DEFAULT NULL COMMENT '创刊时间/int ',
  `jn_official` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '期刊官网/text ',
  `zh_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '期刊描述/text ',
  `format` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '开本/text ',
  `postal_code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '邮发代号/varchar(32) ',
  `chief_editor` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '主编/varchar(128) ',
  `organizer` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '主办单位/varchar(1024) ',
  `publisher_place` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版地/varchar(64) ',
  `award` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '获奖情况/text ',
  `cite_nums` int DEFAULT NULL COMMENT '被引用量/int ',
  `annual_publication` int DEFAULT NULL COMMENT '年文章数/int ',
  `review` tinyint DEFAULT NULL COMMENT '是否为综述性期刊/tinyint ',
  `impact_factor` double DEFAULT NULL COMMENT '分区/double ',
  `sub_quartile` tinyint DEFAULT NULL COMMENT '分类号/tinyint ',
  `classify_list` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT 'classify_list/text ',
  `warning` tinyint DEFAULT NULL COMMENT '是否预警/tinyint ',
  `is_sci` tinyint DEFAULT NULL COMMENT '是否SCI/tinyint ',
  `publication_cycle` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版周期/varchar(64) ',
  `paper_nums` int DEFAULT NULL COMMENT '出版论文量/int ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_zh_name` (`zh_name`(191)),
  KEY `idx_name_abbr` (`name_abbr`),
  KEY `idx_en_name` (`en_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文期刊详情信息';
```

### `dwd_en_journal`（2126 行）

```sql
CREATE TABLE `dwd_en_journal` (
  `publication_id` bigint NOT NULL COMMENT '期刊id/bigint ',
  `publication_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版刊物类型/varchar(255) ',
  `country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版国家/地区/varchar(255) ',
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '期刊名/顶会/预印本名（英文）/varchar(1024) ',
  `name_abbr` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '简称/varchar(255) ',
  `issn_print` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'ISSN/varchar(16) ',
  `issn_online` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'EISSN/varchar(16) ',
  `jn_official` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '期刊官网/text ',
  `en_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '期刊描述/text ',
  `establish_time` int DEFAULT NULL COMMENT '创刊时间/int ',
  `annual_publication` int DEFAULT NULL COMMENT '年文量数/int ',
  `review` tinyint DEFAULT NULL COMMENT '是否为综述性期刊/tinyint ',
  `impact_factor` double DEFAULT NULL COMMENT '影响指数/double ',
  `jcr_zone` varchar(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '分区/varchar(2) ',
  `scope_zone` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `review_period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '平均审稿周期/varchar(255) ',
  `self_rate` double DEFAULT NULL COMMENT '自引率/double ',
  `top` tinyint DEFAULT NULL COMMENT '是否顶刊/tinyint ',
  `warning` tinyint DEFAULT NULL COMMENT '是否预警/tinyint ',
  `is_sci` tinyint DEFAULT NULL COMMENT '是否SCI/tinyint ',
  `publish_period` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版周期/varchar(64) ',
  `layout_cost` varchar(15) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '版面费/varchar(15) ',
  `paper_nums` int DEFAULT NULL COMMENT '出版论文量/int ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_en_name` (`en_name`(191)),
  KEY `idx_name_abbr` (`name_abbr`),
  KEY `idx_issn_print` (`issn_print`),
  KEY `idx_issn_online` (`issn_online`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文期刊详情信息';
```

### `dwd_zh_paper_related`（39900 行）

```sql
CREATE TABLE `dwd_zh_paper_related` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `relevant` json DEFAULT NULL COMMENT '相关文献/json ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '相关文献文献唯一识别号/varchar(512) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '相关文献中文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文关联文献信息';
```

### `dwd_en_paper_related`（39740 行）

```sql
CREATE TABLE `dwd_en_paper_related` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `relevant` json DEFAULT NULL COMMENT '相关文献/json ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '相关文献英文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文关联文献信息';
```

### `dwd_zh_paper_reference`（23019 行）

```sql
CREATE TABLE `dwd_zh_paper_reference` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献中文名/varchar(1024) ',
  `publication_zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献出版物中文名/varchar(1024) ',
  `cover_year_start` varchar(4) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献发表年份/varchar(4) ',
  `volume` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献所在期刊的卷号/varchar(128) ',
  `issue` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献所在期刊的期号/varchar(128) ',
  `first_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献在期刊的首页-页码/varchar(255) ',
  `last_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献在期刊的末尾页-页码/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191)),
  KEY `idx_cover_year_start` (`cover_year_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文参考文献信息';
```

### `dwd_en_paper_reference`（66989 行）

```sql
CREATE TABLE `dwd_en_paper_reference` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献英文名/varchar(1024) ',
  `publication_en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献出版物英文名/varchar(1024) ',
  `cover_year_start` varchar(4) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献发表年份/varchar(4) ',
  `volume` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献所在期刊的卷号/varchar(128) ',
  `issue` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献所在期刊的期号/varchar(128) ',
  `first_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献在期刊的首页-页码/varchar(255) ',
  `last_page` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '参考文献在期刊的末尾页-页码/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_en_name` (`publication_en_name`(191)),
  KEY `idx_cover_year_start` (`cover_year_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文参考文献信息';
```

### `dwd_zh_paper_citation`（2032 行）

```sql
CREATE TABLE `dwd_zh_paper_citation` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献中文名/varchar(1024) ',
  `publication_zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献出版物中文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文引用文献信息';
```

### `dwd_en_paper_citation`（527 行）

```sql
CREATE TABLE `dwd_en_paper_citation` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献英文名/varchar(1024) ',
  `publication_en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献出版物英文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_en_name` (`publication_en_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文引用文献信息';
```

### `dwd_zh_paper_classification`（2081 行）

```sql
CREATE TABLE `dwd_zh_paper_classification` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `scope` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '大类学科分类/varchar(20) ',
  `scope_zone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '小类学科分类/varchar(20) ',
  `keywords` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '论文关键字/longtext ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文分类信息';
```

### `dwd_en_paper_classification`（2000 行）

```sql
CREATE TABLE `dwd_en_paper_classification` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `scope` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '大类学科领域/varchar(20) ',
  `sub_scope` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '小类学科主题/varchar(20) ',
  `keywords` json DEFAULT NULL COMMENT '论文关键词/json ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `created_time_2` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time_2` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文分类信息';
```

## 项目域（load_project_graph → Project + FUNDED_BY / LEADS / HAS_PARTICIPANT / HAS_KEYWORD / HAS_OUTPUT）

### `dwd_zh_project`（2010 行）

```sql
CREATE TABLE `dwd_zh_project` (
  `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目索引/varchar(255) ',
  `project_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目编号/varchar(255) ',
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目名称/varchar(255) ',
  `project_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目来源/varchar(255) ',
  `funded_institution` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目受资助机构/varchar(255) ',
  `project_level` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目级别/varchar(255) ',
  `funded_amount` decimal(18,2) DEFAULT NULL COMMENT '受资助金额/decimal(18,2) ',
  `discipline` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学科/varchar(255) ',
  `discipline_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学科代码/varchar(255) ',
  `fund_category` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '基金类别/varchar(255) ',
  `funded_province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目受资助省/varchar(255) ',
  `participating_institution` json DEFAULT NULL COMMENT '参与机构/json ',
  `approval_year` int DEFAULT NULL COMMENT '立项年度/int ',
  `approval_time` datetime DEFAULT NULL COMMENT '立项时间/datetime ',
  `research_period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '研究期限/varchar(255) ',
  `project_host` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目主持人/varchar(255) ',
  `participants` json DEFAULT NULL COMMENT '参与者/json ',
  `keywords` json DEFAULT NULL COMMENT '关键词/json ',
  `abstract` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目标书摘要/text ',
  `final_report_abstract` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目结题摘要/text ',
  `project_page_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目页面 URL/text ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  KEY `idx_id` (`id`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_discipline_code` (`discipline_code`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内项目信息表';
```

### `dwd_en_project`（1994 行）

```sql
CREATE TABLE `dwd_en_project` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目索引/varchar(64) ',
  `project_number` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目编号/varchar(32) ',
  `title` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目名称/varchar(512) ',
  `project_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目来源/varchar(64) ',
  `funded_institution` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目受资助机构/varchar(128) ',
  `project_level` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目级别/varchar(255) ',
  `funded_amount` decimal(18,2) DEFAULT NULL COMMENT '受资助金额/decimal(18,2) ',
  `discipline` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学科/varchar(256) ',
  `discipline_code` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学科代码/varchar(256) ',
  `fund_category` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '基金类别/varchar(64) ',
  `funded_province` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目受资助地区/varchar(32) ',
  `participating_institution` json DEFAULT NULL COMMENT '参与机构/json ',
  `approval_year` int DEFAULT NULL COMMENT '立项年度/int ',
  `approval_time` datetime DEFAULT NULL COMMENT '立项时间/datetime ',
  `research_period` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '研究期限/varchar(64) ',
  `project_host` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目主持人/varchar(64) ',
  `participants` json DEFAULT NULL COMMENT '参与者/json ',
  `keywords` json DEFAULT NULL COMMENT '关键词/json ',
  `abstract` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目标书摘要/longtext ',
  `final_report_abstract` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目结题摘要/longtext ',
  `project_page_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目页面 URL/text ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  KEY `idx_id` (`id`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_discipline_code` (`discipline_code`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国外项目信息表';
```

### `dwd_zh_project_output`（2010 行）

```sql
CREATE TABLE `dwd_zh_project_output` (
  `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目索引/varchar(255) ',
  `total_outputs` int DEFAULT NULL COMMENT '项目总产出数量/int ',
  `journal_articles_count` int DEFAULT NULL COMMENT '期刊文章数量/int ',
  `conference_papers_count` int DEFAULT NULL COMMENT '会议论文数量/int ',
  `degree_papers_count` int DEFAULT NULL COMMENT '学位论文数量/int ',
  `patents_count` int DEFAULT NULL COMMENT '专利数量/int ',
  `books_count` int DEFAULT NULL COMMENT '图书专著数量/int ',
  `awards_count` int DEFAULT NULL COMMENT '奖项数量/int ',
  `reports_count` int DEFAULT NULL COMMENT '报告数量/int ',
  `other_outputs_count` int DEFAULT NULL COMMENT '其他产出数量/int ',
  `output_journal_articles` json DEFAULT NULL COMMENT '产出的期刊文章/json ',
  `output_patents` json DEFAULT NULL COMMENT '产出的专利/json ',
  `output_conference_papers` json DEFAULT NULL COMMENT '产出的会议论文/json ',
  `output_degree_papers` json DEFAULT NULL COMMENT '产出的学位论文/json ',
  `output_books` json DEFAULT NULL COMMENT '产出的图书专著/json ',
  `output_awards` json DEFAULT NULL COMMENT '产出的奖项/json ',
  `output_reports` json DEFAULT NULL COMMENT '产出的报告/json ',
  `output_other` json DEFAULT NULL COMMENT '其他产出/json ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内项目-产出信息';
```

### `dwd_en_project_output`（1994 行）

```sql
CREATE TABLE `dwd_en_project_output` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目索引/varchar(64) ',
  `total_outputs` int DEFAULT NULL COMMENT '项目总产出数量/int ',
  `journal_articles_count` int DEFAULT NULL COMMENT '期刊文章数量/int ',
  `conference_papers_count` int DEFAULT NULL COMMENT '会议论文数量/int ',
  `degree_papers_count` int DEFAULT NULL COMMENT '学位论文数量/int ',
  `patents_count` int DEFAULT NULL COMMENT '专利数量/int ',
  `clinical_trials_count` int DEFAULT NULL COMMENT '临床试验数量/int ',
  `books_count` int DEFAULT NULL COMMENT '图书专著数量/int ',
  `awards_count` int DEFAULT NULL COMMENT '奖项数量/int ',
  `reports_count` int DEFAULT NULL COMMENT '报告数量/int ',
  `other_outputs_count` int DEFAULT NULL COMMENT '其他产出数量/int ',
  `output_journal_articles` json DEFAULT NULL COMMENT '产出的期刊文章/json ',
  `output_patents` json DEFAULT NULL COMMENT '产出的专利/json ',
  `output_conference_papers` json DEFAULT NULL COMMENT '产出的会议论文/json ',
  `output_degree_papers` json DEFAULT NULL COMMENT '产出的学位论文/json ',
  `output_clinical_trials` json DEFAULT NULL COMMENT '产出的临床试验信息/json ',
  `output_books` json DEFAULT NULL COMMENT '产出的图书专著信息/json ',
  `output_awards` json DEFAULT NULL COMMENT '产出的奖项信息/json ',
  `output_reports` json DEFAULT NULL COMMENT '产出的报告信息/json ',
  `output_other` json DEFAULT NULL COMMENT '其他产出信息/json ',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国外项目-产出信息';
```

## 专利域（load_patent_graph / load_patent_relations → Patent / Keyword + INVENTED_BY / APPLIED_BY / HAS_KEYWORD）

### `dwd_patent`（2010 行）

```sql
CREATE TABLE `dwd_patent` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `publication_number` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `application_kind` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country_code` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `country` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `publication_reference` json DEFAULT NULL,
  `application_reference` json DEFAULT NULL,
  `pct_or_regional_filing_data` json DEFAULT NULL,
  `pct_or_regional_publishing_data` json DEFAULT NULL,
  `priority_filings` json DEFAULT NULL,
  `applicants` json DEFAULT NULL,
  `assignees` json DEFAULT NULL,
  `inventors` json DEFAULT NULL,
  `first_applicant_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `first_current_assignee_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `first_inventor_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `main_classification_ipcr` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `further_classification_ipcr` json DEFAULT NULL,
  `main_classification_cpc` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `further_classification_cpc` json DEFAULT NULL,
  `keywords` json DEFAULT NULL,
  `claims` json DEFAULT NULL,
  `description` json DEFAULT NULL,
  `figures` json DEFAULT NULL,
  `language` json DEFAULT NULL,
  `granted_number` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `value` int DEFAULT NULL,
  `agents` json DEFAULT NULL,
  `agency` json DEFAULT NULL,
  `examiners` json DEFAULT NULL,
  `related_documents` json DEFAULT NULL,
  `classification_loc` json DEFAULT NULL,
  `classification_fi` json DEFAULT NULL,
  `classification_upc` json DEFAULT NULL,
  `classification_fterm` json DEFAULT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利信息表';
```

### `dwd_patent_abstract`（2000 行）

```sql
CREATE TABLE `dwd_patent_abstract` (
  `id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `abstracts` json NOT NULL,
  `abstract_localized` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `abstract_zh` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_abstract_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利摘要信息表';
```

### `dwd_patent_cited`（2000 行）

```sql
CREATE TABLE `dwd_patent_cited` (
  `id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `reference_cited` int NOT NULL,
  `cited_by_nums` int NOT NULL,
  `cited_by_date` json DEFAULT NULL,
  `patent_citation_date` json DEFAULT NULL,
  `non_patent_count` int NOT NULL,
  `non_patent_date` json DEFAULT NULL,
  `patent_citations_country` json DEFAULT NULL,
  `patent_citations_region` json DEFAULT NULL,
  `patent_citations_kd` json DEFAULT NULL,
  `cited_by` json DEFAULT NULL,
  `patent_citations` json DEFAULT NULL,
  `non_patent_citations` json DEFAULT NULL,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_cited_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利引用关系表';
```

### `dwd_patent_family`（2000 行）

```sql
CREATE TABLE `dwd_patent_family` (
  `id` bigint NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `simple_family_number` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `simple_family_pn` json NOT NULL,
  `simple_family` json NOT NULL,
  `family_citations` json DEFAULT NULL,
  `cited_by_family` json DEFAULT NULL,
  `patent_family` json NOT NULL,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_family_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利家族信息表';
```

### `dwd_patent_legal`（2000 行）

```sql
CREATE TABLE `dwd_patent_legal` (
  `id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dates_of_public_availability` json DEFAULT NULL,
  `status` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `legal_events` json DEFAULT NULL,
  `patent_legal/prs_data` json DEFAULT NULL,
  `anticipated_expiration` int DEFAULT NULL COMMENT '预计到期日，YYYYMMDD',
  `expiration_year` int DEFAULT NULL,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_legal_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='法律状态信息表';
```

### `dwd_patent_title`（2010 行）

```sql
CREATE TABLE `dwd_patent_title` (
  `id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `titles` json NOT NULL,
  `title_localized` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `title_zh` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_title_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利标题信息表';
```

## 机构域（organization_entity_etl / organization_relation_etl → 供间接关系与产业链事件遍历的股权/高管/实控/投资/并购/产品边 + News/Event 点 + HAS_NEWS / INVOLVED_IN）

### `dwd_org_base_info`（1674 行）

```sql
CREATE TABLE `dwd_org_base_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在省份/varchar(255) ',
  `city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在城市/varchar(255) ',
  `area` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在区县/varchar(255) ',
  `address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '公司地址/text ',
  `addr_lng` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址对应经度/varchar(255) ',
  `addr_lat` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址对应维度/varchar(255) ',
  `postal_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '邮政编码/varchar(255) ',
  `email` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '电子邮箱/text ',
  `lerep` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人/varchar(255) ',
  `reg_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记状态/varchar(255) ',
  `registration_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记机关/varchar(255) ',
  `incorporation_year` decimal(20,0) DEFAULT NULL COMMENT '成立年份/decimal(20,0) ',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期/datetime ',
  `start_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '经营期限自/varchar(255) ',
  `end_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '经营期限至/varchar(255) ',
  `org_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构类型/varchar(255) ',
  `listing_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '上市状态/varchar(255) ',
  `listing_date` datetime DEFAULT NULL COMMENT '上市日期/datetime ',
  `registered_capital_value` decimal(20,2) DEFAULT NULL COMMENT '注册资本(本币元)/decimal(20,2) ',
  `capital_currency` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '币种/varchar(255) ',
  `industry` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '最深一级的行业名称/varchar(255) ',
  `industry_l1_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '一级行业名称/varchar(255) ',
  `industry_l1_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '一级行业编码/varchar(255) ',
  `industry_l2_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '二级行业名称/varchar(255) ',
  `industry_l2_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '二级行业编码/varchar(255) ',
  `industry_l3_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '三级行业名称/varchar(255) ',
  `industry_l3_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '三级行业编码/varchar(255) ',
  `industry_l4_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '四级行业名称/varchar(255) ',
  `industry_l4_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '四级行业编码/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='机构基本信息';
```

### `dwd_org_shareholder_info`（2501 行）

```sql
CREATE TABLE `dwd_org_shareholder_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `inv_org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东id/varchar(255) ',
  `owners_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '股东名称/varchar(255) ',
  `owners_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东类型/varchar(255) ',
  `ownership_percentage` decimal(20,2) DEFAULT NULL COMMENT '所有权占比(%)/decimal(20,2) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_inv_org_id` (`inv_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='股东信息';
```

### `dwd_org_executive_info`（5600 行）

```sql
CREATE TABLE `dwd_org_executive_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `executives_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '高管姓名/varchar(255) ',
  `executives_position` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '职位名称/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='高管信息';
```

### `dwd_org_org_product_info`（1184 行）

```sql
CREATE TABLE `dwd_org_org_product_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `main_activities` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '公司经营范围/text ',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '业务描述/text ',
  `main_prod` varchar(1120) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营信息';
```

### `dwd_org_annual_financial_info`（5452 行）

```sql
CREATE TABLE `dwd_org_annual_financial_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `year` decimal(20,0) NOT NULL COMMENT '年报年度/decimal(20,0) ',
  `total_assets` decimal(20,2) DEFAULT NULL COMMENT '资产总额/decimal(20,2) ',
  `total_liabilities` decimal(20,2) DEFAULT NULL COMMENT '负债总额/decimal(20,2) ',
  `operating_revenue` decimal(20,2) DEFAULT NULL COMMENT '营业收入/decimal(20,2) ',
  `main_business_revenue` decimal(20,2) DEFAULT NULL COMMENT '主营业务收入/decimal(20,2) ',
  `total_profit` decimal(20,2) DEFAULT NULL COMMENT '利润总额/decimal(20,2) ',
  `pure_profit` decimal(20,2) DEFAULT NULL COMMENT '净利润/decimal(20,2) ',
  `total_tax_paid` decimal(20,2) DEFAULT NULL COMMENT '纳税总额/decimal(20,2) ',
  `owners_equity` decimal(20,2) DEFAULT NULL COMMENT '所有者权益合计/decimal(20,2) ',
  `employees_number` decimal(20,0) DEFAULT NULL COMMENT '从业人数/decimal(20,0) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='年报财务信息';
```

### `dwd_org_important_news_info`（1013 行）

```sql
CREATE TABLE `dwd_org_important_news_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `news_title` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '资讯标题/text ',
  `news_date` datetime NOT NULL COMMENT '资讯日期/datetime ',
  `news_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '资讯内容/text ',
  `original_textlink` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '咨询原文链接/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_news_date` (`news_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='重点资讯';
```

### `dwd_org_changerecord_info`（100 行）

```sql
CREATE TABLE `dwd_org_changerecord_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `update_content` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '变更类型/varchar(255) ',
  `current_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '变更前内容/text ',
  `update_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '变更后内容/text ',
  `update_date` datetime DEFAULT NULL COMMENT '变更日期/datetime ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_update_date` (`update_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='工商变更信息';
```

### `dwd_org_merger_acquisition_info`（1022 行）

```sql
CREATE TABLE `dwd_org_merger_acquisition_info` (
  `acquiring_org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '发起收购企业id/varchar(255) ',
  `acquiring_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '发起收购企业名称/varchar(255) ',
  `acquiring_external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '发起收购企业统一社会信用代码/varchar(255) ',
  `acquired_org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '被收购企业id/varchar(255) ',
  `acquired_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '被收购企业名称/varchar(255) ',
  `acquired_external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '被收购企业统一社会信用代码/varchar(255) ',
  `ma_amount` decimal(20,2) DEFAULT NULL COMMENT '并购金额(元)/decimal(20,2) ',
  `currency_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '并购金额币种/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_acquiring_org_id` (`acquiring_org_id`),
  KEY `idx_acquiring_external_id` (`acquiring_external_id`),
  KEY `idx_acquired_org_id` (`acquired_org_id`),
  KEY `idx_acquired_external_id` (`acquired_external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='并购事件';
```

### `dwd_org_financing_info`（1073 行）

```sql
CREATE TABLE `dwd_org_financing_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `funding_round` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '融资轮次/varchar(255) ',
  `funding_amount` decimal(20,2) DEFAULT NULL COMMENT '获投金额(元)/decimal(20,2) ',
  `funding_currency_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '金额币种/varchar(255) ',
  `completion_date` datetime DEFAULT NULL COMMENT '融资完成时间/datetime ',
  `investors_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '投资方列表/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='融资事件';
```

### `dwd_org_invest_info`（4298 行）

```sql
CREATE TABLE `dwd_org_invest_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `inv_org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '被投企业id/varchar(255) ',
  `inv_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '被投资企业名称/varchar(255) ',
  `inv_external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '被投资企业统一社会信用代码/varchar(255) ',
  `investment_amount` decimal(20,2) DEFAULT NULL COMMENT '投资金额(元)/decimal(20,2) ',
  `investment_ratio` decimal(20,2) DEFAULT NULL COMMENT '股权占比(%)/decimal(20,2) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_inv_org_id` (`inv_org_id`),
  KEY `idx_inv_external_id` (`inv_external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='投资事件';
```

### `dwd_org_recruit_info`（2100 行）

```sql
CREATE TABLE `dwd_org_recruit_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `job_title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '岗位/varchar(255) ',
  `job_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '工作描述/text ',
  `work_place` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '工作地点/text ',
  `release_date` datetime DEFAULT NULL COMMENT '发布日期/datetime ',
  `hiring_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '招聘人数/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招聘信息';
```

### `dwd_org_stock_finance_info`（5553 行）

```sql
CREATE TABLE `dwd_org_stock_finance_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `stock_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '股票代码/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `occur_period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据期/varchar(255) ',
  `total_assets` decimal(20,2) DEFAULT NULL COMMENT '资产总额(元)/decimal(20,2) ',
  `fixed_assets` decimal(20,2) DEFAULT NULL COMMENT '固定资产总额(元)/decimal(20,2) ',
  `total_liabilities` decimal(20,2) DEFAULT NULL COMMENT '负债总额(元)/decimal(20,2) ',
  `operating_revenue` decimal(20,2) DEFAULT NULL COMMENT '营业收入(元)/decimal(20,2) ',
  `main_business_revenue` decimal(20,2) DEFAULT NULL COMMENT '主营业务收入(元)/decimal(20,2) ',
  `total_profit` decimal(20,2) DEFAULT NULL COMMENT '利润总额(元)/decimal(20,2) ',
  `pure_profit` decimal(20,2) DEFAULT NULL COMMENT '净利润(元)/decimal(20,2) ',
  `total_tax_paid` decimal(20,2) DEFAULT NULL COMMENT '纳税总额(元)/decimal(20,2) ',
  `oper_cash_flow` decimal(20,2) DEFAULT NULL COMMENT '经营活动现金流(元)/decimal(20,2) ',
  `owners_equity` decimal(20,2) DEFAULT NULL COMMENT '所有者权益合计(元)/decimal(20,2) ',
  `employees_number` decimal(20,0) DEFAULT NULL COMMENT '从业人数/decimal(20,0) ',
  `research_development_amount` decimal(20,2) DEFAULT NULL COMMENT '研发投入金额(元)/decimal(20,2) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_occur_period` (`occur_period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业主要财务指标';
```

### `dwd_org_company_abnormal`（2062 行）

```sql
CREATE TABLE `dwd_org_company_abnormal` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `abnormal_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '经营异常记录id/varchar(255) ',
  `abn_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '列入原因/text ',
  `abn_date` datetime DEFAULT NULL COMMENT '列入时间/datetime ',
  `abn_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '列入机关/varchar(255) ',
  `remove_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '移除原因/text ',
  `remove_date` datetime DEFAULT NULL COMMENT '移除时间/datetime ',
  `remove_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '移除机关/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_abnormal_id` (`abnormal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营异常';
```

### `dwd_org_company_punish`（335 行）

```sql
CREATE TABLE `dwd_org_company_punish` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `penalty_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '行政处罚记录id/varchar(255) ',
  `decision_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '决定书文号/varchar(255) ',
  `violation_type` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '违法行为类型/text ',
  `penalty_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '行政处罚内容/text ',
  `decision_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '决定机关/varchar(255) ',
  `penalty_date` datetime DEFAULT NULL COMMENT '处罚决定日期/datetime ',
  `public_date` datetime DEFAULT NULL COMMENT '公示日期/datetime ',
  `penalty_basis` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '处罚依据/text ',
  `violation_fact` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '主要违法事实/text ',
  `penalty_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '处罚种类/varchar(255) ',
  `fine_amount` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '罚款金额/varchar(255) ',
  `confiscate_amount` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '没收金额/varchar(255) ',
  `license_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '暂扣或吊销证照名称及编号/varchar(255) ',
  `validity_period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '处罚有效期/varchar(255) ',
  `public_deadline` datetime DEFAULT NULL COMMENT '公示截止日期/datetime ',
  `mark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_penalty_id` (`penalty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='行政处罚';
```

### `dwd_org_company_illegal`（2100 行）

```sql
CREATE TABLE `dwd_org_company_illegal` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `sv_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '严重违法记录id/varchar(255) ',
  `category` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '类别/varchar(255) ',
  `abn_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '列入原因/text ',
  `abn_date` datetime DEFAULT NULL COMMENT '列入时间/datetime ',
  `abn_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '列入机关/varchar(255) ',
  `remove_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '移除原因/text ',
  `remove_date` datetime DEFAULT NULL COMMENT '移除时间/datetime ',
  `remove_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '移除机关/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_sv_id` (`sv_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='严重违法';
```

### `dwd_org_risk_tax_punish`（2100 行）

```sql
CREATE TABLE `dwd_org_risk_tax_punish` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `taxpayer_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '纳税人名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `tax_vio_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '唯一索引id/varchar(255) ',
  `report_period` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案件上报期/varchar(255) ',
  `taxpayer_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '纳税人识别码/varchar(255) ',
  `org_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '组织机构代码/varchar(255) ',
  `reg_address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '注册地址/text ',
  `publish_date` datetime DEFAULT NULL COMMENT '发布日期/datetime ',
  `legal_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人或者负责人姓名/varchar(255) ',
  `legal_gender` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人或者负责人性别/varchar(255) ',
  `legal_id_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人或者负责人证件类型/varchar(255) ',
  `legal_id_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人或者负责人证件号码/varchar(255) ',
  `finance_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '负有直接责任的财务负责人姓名/varchar(255) ',
  `finance_gender` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '负有直接责任的财务负责人性别/varchar(255) ',
  `finance_id_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '负有直接责任的财务负责人证件类型/varchar(255) ',
  `finance_id_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '负有直接责任的财务负责人证件号码/varchar(255) ',
  `agency_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '负有直接责任的中介机构信息及其从业人员信息/varchar(255) ',
  `case_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案件性质/varchar(255) ',
  `illegal_fact` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '主要违法事实/text ',
  `punish_basis` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '相关法律依据及税务处理处罚情况/text ',
  `tax_authority` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所属税务机关/varchar(255) ',
  `original_link` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '数据原始链接/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_tax_vio_id` (`tax_vio_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='税收违法';
```

### `dwd_org_opt_judicial_case`（2100 行）

```sql
CREATE TABLE `dwd_org_opt_judicial_case` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `company_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '企业名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `case_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '司法案件唯一标识/varchar(255) ',
  `reg_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册号/varchar(255) ',
  `case_title` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '案件标题/text ',
  `case_type_tag` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案件类型标签/varchar(255) ',
  `case_no` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '案号/text ',
  `case_cause` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '案由/text ',
  `case_role` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '案件身份/text ',
  `current_procedure` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前审理程序/varchar(255) ',
  `procedure_date` datetime DEFAULT NULL COMMENT '当前审理程序日期/datetime ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='司法案件信息';
```

### `dwd_org_risk_shixin`（2100 行）

```sql
CREATE TABLE `dwd_org_risk_shixin` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '失信人名称/text ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `dishonest_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '失信被执行人id/varchar(255) ',
  `official_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '官网id/varchar(255) ',
  `case_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案号/varchar(255) ',
  `gender` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '性别/varchar(255) ',
  `age` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '年龄/varchar(255) ',
  `reg_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '企业注册号/varchar(255) ',
  `display_id_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '展示用证件号码/varchar(255) ',
  `legal_person` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人或负责人/varchar(255) ',
  `exec_court` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '执行法院/varchar(255) ',
  `province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '省份/varchar(255) ',
  `dishonest_type` decimal(20,0) DEFAULT NULL COMMENT '失信人类型/decimal(20,0) ',
  `exec_basis_no` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '执行依据文号/text ',
  `exec_basis_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '做出执行依据单位/varchar(255) ',
  `legal_obligation` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '生效法律文书确定的义务/text ',
  `fulfillment_status` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '被执行人的履行情况/text ',
  `dishonest_behavior` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '失信被执行人行为具体情形/text ',
  `publish_date` datetime DEFAULT NULL COMMENT '发布时间/datetime ',
  `filing_date` datetime DEFAULT NULL COMMENT '立案时间/datetime ',
  `exec_part` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '执行部分/text ',
  `unexec_part` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '未执行部分/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_dishonest_id` (`dishonest_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='失信被执行人';
```

### `dwd_org_risk_zhixing`（2100 行）

```sql
CREATE TABLE `dwd_org_risk_zhixing` (
  `exec_person_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '唯一索引id/varchar(255) ',
  `exec_person_type` decimal(20,0) DEFAULT NULL COMMENT '被执行人类型/decimal(20,0) ',
  `exec_person_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '被执行人名称/varchar(255) ',
  `gender` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '性别/varchar(255) ',
  `id_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '证件号码/varchar(255) ',
  `exec_court` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '执行法院/varchar(255) ',
  `case_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案号/varchar(255) ',
  `exec_basis_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '执行依据文号/varchar(255) ',
  `exec_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '执行状态/varchar(255) ',
  `exec_target` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '执行标的/varchar(255) ',
  `web_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '执行信息公开网id/varchar(255) ',
  `filing_date` datetime DEFAULT NULL COMMENT '立案时间/datetime ',
  `is_hidden` decimal(20,0) DEFAULT NULL COMMENT '是否不展示/decimal(20,0) ',
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_exec_person_id` (`exec_person_id`),
  KEY `idx_exec_basis_no` (`exec_basis_no`),
  KEY `idx_web_id` (`web_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='被执行人';
```

### `dwd_org_bankruptcy_public_cases`（2100 行）

```sql
CREATE TABLE `dwd_org_bankruptcy_public_cases` (
  `case_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '案号/varchar(255) ',
  `case_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案件类型/varchar(255) ',
  `handling_court` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '经办法院/varchar(255) ',
  `applicant_info` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '申请人信息/text ',
  `respondent_info` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '被申请人信息/text ',
  `admin_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '管理人机构/varchar(255) ',
  `admin_org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '管理人机构id/varchar(255) ',
  `admin_principal` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '管理人主要负责人/varchar(255) ',
  `public_date` datetime DEFAULT NULL COMMENT '公开时间/datetime ',
  `link` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '链接/text ',
  `history_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '历史状态/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_admin_org_id` (`admin_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='破产案件';
```

### `dwd_org_bankruptcy_public_cases_list`（2100 行）

```sql
CREATE TABLE `dwd_org_bankruptcy_public_cases_list` (
  `bankruptcy_party_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '唯一索引id/varchar(255) ',
  `case_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '案号/varchar(255) ',
  `related_person_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '相关人名称/varchar(255) ',
  `party_role_type` decimal(20,0) DEFAULT NULL COMMENT '当事人角色类型/decimal(20,0) ',
  `party_type` decimal(20,0) DEFAULT NULL COMMENT '当事人类型/decimal(20,0) ',
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `public_date` datetime DEFAULT NULL COMMENT '公开时间/datetime ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_bankruptcy_party_id` (`bankruptcy_party_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='破产案件当事人';
```

### `dwd_special_taiwan_company`（100 行）

```sql
CREATE TABLE `dwd_special_taiwan_company` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `company_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '原始机构名称/varchar(255) ',
  `n_company_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标准机构名称/varchar(255) ',
  `company_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一编号/varchar(255) ',
  `history_company_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '历史统一编号/varchar(255) ',
  `company_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记状态/varchar(255) ',
  `company_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '类型/varchar(255) ',
  `name_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构英文名称/varchar(255) ',
  `capital` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '资本总额/varchar(255) ',
  `capital_num` decimal(20,6) DEFAULT NULL COMMENT '资本总额_值(万)/decimal(20,6) ',
  `currency` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '资本总额_币种/varchar(255) ',
  `real_capital` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '实缴资本额/varchar(255) ',
  `realcapital_num` decimal(20,6) DEFAULT NULL COMMENT '实缴资本额_值(万)/decimal(20,6) ',
  `realcapital_currency` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '实收资本额_币种/varchar(255) ',
  `amount_per_share` decimal(20,6) DEFAULT NULL COMMENT '每股金额/decimal(20,6) ',
  `total_shares` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '已发行股份总数/varchar(255) ',
  `legal_person` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '代表人姓名/varchar(255) ',
  `company_address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构所在地/varchar(255) ',
  `registration_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记机关/varchar(255) ',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期/datetime ',
  `issue_date` datetime DEFAULT NULL COMMENT '核准日期/datetime ',
  `plural_voting_shares` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '是否具有复数表决权特别股/varchar(255) ',
  `matters_veto_shares` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '是否具有对于特定事项具否决权特别股/varchar(255) ',
  `special_holder_rights` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '特别股股东被选为董事、监察人的禁止或限制或当选一定名额的权利情况/varchar(255) ',
  `business_scope` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '经营范围/text ',
  `history_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '历史名称/varchar(255) ',
  `equity_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股权状况/varchar(255) ',
  `company_quality` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构属性/varchar(255) ',
  `closure_date_begin` datetime DEFAULT NULL COMMENT '停业日期(起)/datetime ',
  `closure_date_end` datetime DEFAULT NULL COMMENT '停业日期(迄)/datetime ',
  `closure_authority` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '停业核准(备)机关/varchar(255) ',
  `is_history` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '是否历史数据/varchar(255) ',
  `create_time` datetime NOT NULL COMMENT '入库时间/datetime ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_company_name` (`company_name`),
  KEY `idx_n_company_name` (`n_company_name`),
  KEY `idx_company_code` (`company_code`),
  KEY `idx_history_company_code` (`history_company_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='台湾企业';
```

### `dwd_bid_base_out`（100 行）

```sql
CREATE TABLE `dwd_bid_base_out` (
  `u_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `publish_time` datetime DEFAULT NULL COMMENT '发布时间/datetime ',
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标题/varchar(255) ',
  `project_number` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目编号/text ',
  `plan_number` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '计划编号/text ',
  `project_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目名称/text ',
  `announcement_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '公告类型/varchar(255) ',
  `announcement_type_code` decimal(20,0) DEFAULT NULL COMMENT '公告类型编号/decimal(20,0) ',
  `industry_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '行业分类/varchar(255) ',
  `procurement_method` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '采购方式/varchar(255) ',
  `procurement_method_code` decimal(20,0) DEFAULT NULL COMMENT '采购方式编号/decimal(20,0) ',
  `bidding_stage` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '招投标阶段/varchar(255) ',
  `target_item_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标的物类型/varchar(255) ',
  `bidding_stage_code` decimal(20,0) DEFAULT NULL COMMENT '招投标阶段编码/decimal(20,0) ',
  `project_region_province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目区域-省/varchar(255) ',
  `project_region_province_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目区域-省-编码/varchar(255) ',
  `project_region_city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目区域-市/varchar(255) ',
  `project_region_city_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目区域-市-编码/varchar(255) ',
  `project_region_district` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目区域-区县/varchar(255) ',
  `project_region_district_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目区域-区县-编码/varchar(255) ',
  `project_budget_amount` decimal(20,6) DEFAULT NULL COMMENT '项目预算金额/decimal(20,6) ',
  `project_budget_amount_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目预算金额单位/varchar(255) ',
  `total_amount` decimal(20,6) DEFAULT NULL COMMENT '中标总金额/decimal(20,6) ',
  `total_amount_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '中标总金额单位/varchar(255) ',
  `bid_document_start_time` datetime DEFAULT NULL COMMENT '标书获取开始时间/datetime ',
  `bid_document_end_time` datetime DEFAULT NULL COMMENT '标书获取截止时间/datetime ',
  `registration_start_time` datetime DEFAULT NULL COMMENT '报名开始时间/datetime ',
  `registration_end_time` datetime DEFAULT NULL COMMENT '报名截止时间/datetime ',
  `bidding_start_time` datetime DEFAULT NULL COMMENT '投标开始时间/datetime ',
  `bidding_end_time` datetime DEFAULT NULL COMMENT '投标结束时间/datetime ',
  `opening_bid_time` datetime DEFAULT NULL COMMENT '开标时间/datetime ',
  `estimated_purchasing_time` datetime DEFAULT NULL COMMENT '预计采购时间/datetime ',
  `contract_num` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '合同编号/text ',
  `quotation_validity_start` datetime DEFAULT NULL COMMENT '报价有效期-起/datetime ',
  `quotation_validity_end` datetime DEFAULT NULL COMMENT '报价有效期-止/datetime ',
  `tender_document_price_amount` decimal(20,6) DEFAULT NULL COMMENT '标书售价(数值)/decimal(20,6) ',
  `tender_document_price_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标书售价(单位)/varchar(255) ',
  `registration_fee_amount` decimal(20,6) DEFAULT NULL COMMENT '报名费(数值)/decimal(20,6) ',
  `registration_fee_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报名费(单位)/varchar(255) ',
  `bidding_security_amount` decimal(20,6) DEFAULT NULL COMMENT '投标保证金(数值)/decimal(20,6) ',
  `bidding_security_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '投标保证金(单位)/varchar(255) ',
  `ca_payment_amount` decimal(20,6) DEFAULT NULL COMMENT 'CA缴纳费用(数值字)/decimal(20,6) ',
  `ca_payment_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'CA缴纳费用(单位)/varchar(255) ',
  `tender_agent_service_fee_amount` decimal(20,6) DEFAULT NULL COMMENT '招标代理服务费(数值)/decimal(20,6) ',
  `tender_agent_service_fee_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '招标代理服务费(单位)/varchar(255) ',
  `performance_security_amount` decimal(20,6) DEFAULT NULL COMMENT '履约保证金(数值)/decimal(20,6) ',
  `performance_security_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '履约保证金(单位)/varchar(255) ',
  `funding_source` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '资金来源/text ',
  `construction_service_location` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '建设地点/服务地点/text ',
  `construction_service_period` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '工期/服务周期/text ',
  `allow_joint_bid` decimal(20,0) DEFAULT NULL COMMENT '是否允许联合体投标/decimal(20,0) ',
  `bidding_document_sub_style` decimal(20,0) DEFAULT NULL COMMENT '投标文件递交方式/decimal(20,0) ',
  `supplier_qualification_criteria` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '供应商的准入资质/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标公告基础表';
```

### `dwd_bid_win_candidate_out`（100 行）

```sql
CREATE TABLE `dwd_bid_win_candidate_out` (
  `u_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `project_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目编号/varchar(255) ',
  `project_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目名称/text ',
  `bid_item_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '招标项目名称/text ',
  `bid_section_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标段编号/varchar(255) ',
  `amount` decimal(20,6) DEFAULT NULL COMMENT '中标报价(金额)/decimal(20,6) ',
  `amount_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '中标报价(单位)/varchar(255) ',
  `ranking` decimal(20,0) DEFAULT NULL COMMENT '候选人排名/decimal(20,0) ',
  `relate_type` decimal(20,0) DEFAULT NULL COMMENT '关系类型/decimal(20,0) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标中标候选人表';
```

### `dwd_bid_purchase_agency_out`（100 行）

```sql
CREATE TABLE `dwd_bid_purchase_agency_out` (
  `u_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `company_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构id/varchar(255) ',
  `company_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构名称/varchar(255) ',
  `credit_no` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `project_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目编号/varchar(255) ',
  `project_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目名称/text ',
  `relate_type` decimal(20,0) DEFAULT NULL COMMENT '枚举判断/decimal(20,0) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`),
  KEY `idx_company_id` (`company_id`),
  KEY `idx_company_name` (`company_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标采购代理表';
```

### `dwd_bid_target_item_out`（100 行）

```sql
CREATE TABLE `dwd_bid_target_item_out` (
  `u_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '公告唯一标识id/varchar(255) ',
  `project_number` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目编号/text ',
  `project_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '项目名称/text ',
  `amount_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '金额单位/varchar(255) ',
  `bid_item_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '招标项目名称/text ',
  `bid_section_number` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标段编号/varchar(255) ',
  `brand` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '品牌/varchar(255) ',
  `model` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '型号/varchar(255) ',
  `project_content` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '项目内容/varchar(255) ',
  `quantity` decimal(20,0) DEFAULT NULL COMMENT '数量/decimal(20,0) ',
  `service_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '服务内容/text ',
  `standard_product_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标准产品名称/varchar(255) ',
  `target_item_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '标的物名称/text ',
  `target_item_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标的物类型/varchar(255) ',
  `unit_price_amount` decimal(20,2) DEFAULT NULL COMMENT '单价金额/decimal(20,2) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_u_id` (`u_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标标的物表';
```

### `dwd_research_institute_base_info`（100 行）

```sql
CREATE TABLE `dwd_research_institute_base_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `lerep` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '法定代表人/varchar(255) ',
  `reg_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记状态/varchar(255) ',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期/datetime ',
  `org_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '类型/varchar(255) ',
  `registered_capital_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册资本(本币元)/varchar(255) ',
  `capital_currency` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '币种/varchar(255) ',
  `address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '登记地址/text ',
  `name_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '英文名称/varchar(255) ',
  `registration_org` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记机关/varchar(255) ',
  `province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在省份/varchar(255) ',
  `city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在城市/varchar(255) ',
  `area` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在区县/varchar(255) ',
  `addr_lng` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址对应经度/varchar(255) ',
  `addr_lat` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址对应维度/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_name_cn` (`name_cn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='科研机构基本信息';
```

### `dwd_forg_base_info`（1100 行）

```sql
CREATE TABLE `dwd_forg_base_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `name_alias` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构本地名称/varchar(255) ',
  `country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '国家代码/varchar(255) ',
  `country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '国家/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当地官方唯一注册码/varchar(255) ',
  `city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '所在城市/varchar(255) ',
  `address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '公司地址/text ',
  `postal_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '邮政编码（无数据）/varchar(255) ',
  `phone` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '联系电话/varchar(255) ',
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '电子邮箱/varchar(255) ',
  `company_type` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '企业类型/text ',
  `registration_org` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '注册机构（无数据）/text ',
  `incorporation_year` decimal(20,0) DEFAULT NULL COMMENT '成立年份/decimal(20,0) ',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期/注册日期/核准日期/datetime ',
  `listing_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '上市状态/varchar(255) ',
  `registered_capital_value` decimal(20,0) DEFAULT NULL COMMENT '注册资本/decimal(20,0) ',
  `registered_capital_currency_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册资本货币代码/varchar(255) ',
  `industry_class` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '公司行业分类/varchar(255) ',
  `industry_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '行业分类标准（新增字段）/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构基本信息';
```

### `dwd_forg_shareholder_info`（21197 行）

```sql
CREATE TABLE `dwd_forg_shareholder_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `owners_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东名称/varchar(255) ',
  `ownership_percentage` decimal(20,2) DEFAULT NULL COMMENT '股权占比(%)/decimal(20,2) ',
  `owners_country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东所在国家代码/varchar(255) ',
  `owners_country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东所在国家/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构股东股权关联信息';
```

### `dwd_forg_subsidiary_info`（12299 行）

```sql
CREATE TABLE `dwd_forg_subsidiary_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `affiliate` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司id/varchar(255) ',
  `affiliates_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司名称/varchar(255) ',
  `affiliates_country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司国家代码/varchar(255) ',
  `affiliates_country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司国家/varchar(255) ',
  `affiliates_company_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司唯一注册码/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构子公司股权关联信息';
```

### `dwd_forg_executive_info`（4911 行）

```sql
CREATE TABLE `dwd_forg_executive_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `executives_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '高管姓名/varchar(255) ',
  `executives_position` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '职位名称/varchar(255) ',
  `dm_birthdate` datetime DEFAULT NULL COMMENT '高管出生日期(新增字段)/datetime ',
  `dm_nationalities` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '高管国籍(新增字段)/varchar(255) ',
  `dm_biography` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构高管信息';
```

### `dwd_forg_product_info`（1099 行）

```sql
CREATE TABLE `dwd_forg_product_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `description` varchar(368) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `main_products` varchar(1520) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构公司经营信息';
```

### `dwd_forg_beneficiary_info`（6376 行）

```sql
CREATE TABLE `dwd_forg_beneficiary_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `bo_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '受益人名称/varchar(255) ',
  `bo_gender` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '受益人性别/varchar(255) ',
  `bo_birthdate` datetime DEFAULT NULL COMMENT '受益人出生日期/datetime ',
  `bo_country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '受益人所在国家代码/varchar(255) ',
  `path` varchar(3296) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `bo_manager` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '受益人是否同时是管理层/varchar(255) ',
  `total_percent` decimal(20,2) DEFAULT NULL COMMENT '总持股比例/decimal(20,2) ',
  `direct_percent` decimal(20,2) DEFAULT NULL COMMENT '直接持股比例/decimal(20,2) ',
  `indirect_percent` decimal(20,2) DEFAULT NULL COMMENT '间接持股比例/decimal(20,2) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构受益人信息（新增表）';
```

### `dwd_forg_act_contro_info`（1127 行）

```sql
CREATE TABLE `dwd_forg_act_contro_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '企业国家代码/varchar(255) ',
  `entity_eid` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '实控人ID/varchar(255) ',
  `entity_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '实控人名称/varchar(255) ',
  `entity_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '实控人类型/varchar(255) ',
  `entity_country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '实控人国家代码/varchar(255) ',
  `direct_pct` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '直接持股比例/varchar(255) ',
  `total_pct` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '总持股比例/varchar(255) ',
  `direct_pct_num` decimal(20,2) DEFAULT NULL COMMENT '直接持股比例数值/decimal(20,2) ',
  `total_pct_num` decimal(20,2) DEFAULT NULL COMMENT '总持股比例数值/decimal(20,2) ',
  `path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '路径/varchar(255) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构实控人信息（新增表）';
```

### `dwd_forg_stock_fin_info`（100 行）

```sql
CREATE TABLE `dwd_forg_stock_fin_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `occur_period` datetime DEFAULT NULL COMMENT '报告期/datetime ',
  `total_assets` decimal(20,2) DEFAULT NULL COMMENT '资产总额/decimal(20,2) ',
  `fixed_assets` decimal(20,2) DEFAULT NULL COMMENT '固定资产总额/decimal(20,2) ',
  `total_liabilities` decimal(20,2) DEFAULT NULL COMMENT '负债总额/decimal(20,2) ',
  `operating_revenue` decimal(20,2) DEFAULT NULL COMMENT '营业收入/decimal(20,2) ',
  `main_business_revenue` decimal(20,2) DEFAULT NULL COMMENT '主营业务收入/decimal(20,2) ',
  `total_profit` decimal(20,2) DEFAULT NULL COMMENT '利润总额/decimal(20,2) ',
  `pure_profit` decimal(20,2) DEFAULT NULL COMMENT '净利润/decimal(20,2) ',
  `total_tax_paid` decimal(20,2) DEFAULT NULL COMMENT '企业所得税/decimal(20,2) ',
  `oper_cash_flow` decimal(20,2) DEFAULT NULL COMMENT '经营活动现金流/decimal(20,2) ',
  `owners_equity` decimal(20,2) DEFAULT NULL COMMENT '所有者权益合计/decimal(20,2) ',
  `employees_number` decimal(20,2) DEFAULT NULL COMMENT '从业人数/decimal(20,2) ',
  `research_development_amount` decimal(20,2) DEFAULT NULL COMMENT '研发投入金额/decimal(20,2) ',
  `research_development_employees_number` decimal(20,2) DEFAULT NULL COMMENT '研发人员数（无数据）/decimal(20,2) '
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外上市企业财务信息';
```

## 产业链域（industry_chain_etl / backfill_chain_org_nodes → IndustryChain / IndustryNode / News + HAS_NODE / CHILD_OF / DOWNSTREAM_OF / BELONGS_TO_NODE / COVERS_CHAIN）

### `dwd_industry_chain_info`（180 行）

```sql
CREATE TABLE `dwd_industry_chain_info` (
  `chain_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链名称/varchar(255) ',
  `node_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '节点代码/varchar(255) ',
  `node_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '节点名称/varchar(255) ',
  `node_type` decimal(20,0) NOT NULL COMMENT '节点类型/decimal(20,0) ',
  `level` decimal(20,0) NOT NULL COMMENT '节点层级/decimal(20,0) ',
  `node_seq` decimal(20,0) DEFAULT NULL COMMENT '节点序号/decimal(20,0) ',
  `parent_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '父级节点代码/varchar(255) ',
  `parent_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '父级节点名称/text ',
  `node_imp_level` decimal(20,0) DEFAULT NULL COMMENT '节点重要性等级/decimal(20,0) ',
  `downstream_link_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '下游节点代码/varchar(255) ',
  `node_stage` decimal(20,0) DEFAULT NULL COMMENT '节点环节/decimal(20,0) ',
  `node_path` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '节点路径/text ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_node_imp_level` (`node_imp_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链图谱';
```

### `dwd_org_industry_chain_dtl`（2951 行）

```sql
CREATE TABLE `dwd_org_industry_chain_dtl` (
  `chain_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链名称/varchar(255) ',
  `node_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '节点代码/varchar(255) ',
  `node_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '节点名称/varchar(255) ',
  `antitypic` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '企业id/varchar(255) ',
  `credit_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `chain_score` decimal(20,2) DEFAULT NULL COMMENT '产业链评分/decimal(20,2) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业关联企业信息';
```

### `dwd_org_industry_chain_prod_dtl`（6059 行）

```sql
CREATE TABLE `dwd_org_industry_chain_prod_dtl` (
  `chain_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链名称/varchar(255) ',
  `antitypic` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '企业id/varchar(255) ',
  `company_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '企业名称/varchar(500) ',
  `credit_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `tech_product` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '主营产品名称/varchar(255) ',
  `tech_product_seq` decimal(20,0) DEFAULT NULL COMMENT '主营产品排序/decimal(20,0) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链企业关联产品信息';
```

### `dwd_industry_chain_news_info`（476 行）

```sql
CREATE TABLE `dwd_industry_chain_news_info` (
  `chain_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '产业链名称/varchar(255) ',
  `news_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '资讯id/varchar(255) ',
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '标题/varchar(255) ',
  `relaese_date` datetime DEFAULT NULL COMMENT '发布时间/datetime ',
  `summary` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '摘要/text ',
  `source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业动态资讯';
```

## 未收录的表（全量 spec 中有、但九模块不消费）

| 表 | 原因 |
|---|---|
| `dwd_zh_report` / `dwd_en_report` / `dwd_zh_report_paper` | Report 顶点与 REFERENCED_BY 边；九模块不读 Report 域（AUTHOR_OF_REPORT / REPORT_ORG / REPORT_RELATED_PROJECT 无装载脚本） |
| `dwd_org_heis_info` / `dwd_special_hongkong_company` / `dwd_special_aomen_company` | 纯 Organization 顶点补充，不产生任何九模块读取的边（顶点仅提升学者机构名匹配率，非硬依赖） |
| `dwd_org_stock_base` | 上市公司 Organization 顶点补充；抽取脚本侧不产九模块读的边（模块 7 运行时经 gkx 会话使用，见《九大业务模块MySQL表结构.md》） |
| `dwd_org_tag_info` | 无 ETL 脚本引用；ORM/运行时在用但 dev 库缺表 |
| `scholar` | 仅 legacy `load_graph.py`（techkg 旧空间）使用，dev 库无此表 |

## 核查反馈（2026-09-22，待修订）

对本文"收录口径（硬依赖闭包，66 张）"与"未收录的表"两节做了代码级核查。基准：本仓库 `backend/`（与 kgetl@7778e52 在 `backend/script/` 下仅差 `semantic_research_entity_extract.py`，结论两边通用）。

**总结论：66 张已收录表全部真实被消费、无凑数，抽查 SQL 引用列名与本文 DDL 全部对得上；但闭包不成立——另有 9 张硬依赖表与 1 个探针列未收录，"未收录的表"一节多条排除理由与代码事实相反。补齐前，本文档不能支撑"空库重建源表、验证各抽取脚本可行性"的目标。实际硬依赖应为 75 张表 + 1 列。**

### 1. 缺失的硬依赖表（9 张，按本文口径重建即失败 / 建不出边）

| 表 | 消费证据（backend/ 内 file:line） | 缺失后果 |
|---|---|---|
| `dwd_zh_author` / `dwd_en_author` | `script/load_paper_journal_graph.py:264`（主流程步骤 2，无条件执行）；`script/relation_extractors_one_relation/authored_by_relation.py:18-25`；`script/entity_extractors_one_entity/person_entity.py:124-125`（平台 SOURCES）；`script/paper_journal_relation/attach_provenance.py:61,67` | 步骤 2 直接抛错，期刊/引文/报告后续步骤全部不跑、水位不推进。论文期刊域头部声称的"作者 Person + AUTHORED_BY"唯一来源就是这两张表 |
| `dwd_zh_report` / `dwd_en_report` | `script/load_paper_journal_graph.py:472,497`（步骤 6，无条件执行）；`script/entity_extractors_one_entity/report_entity.py:9-10`（Report 顶点，且已注册平台抽取 `register_platform_extraction.py:52`）；`attach_provenance.py:85,91` | 步骤 6 崩。"九模块不读 Report 域"混淆了运行时读取与注入装载：Report 顶点每轮都在装 |
| `dwd_zh_report_paper` | `script/paper_journal_relation/load_paper_relation.py:393`（默认 RELATION_TYPES 含 paper_report，:447-453，默认必跑）；`script/relation_extractors_one_relation/referenced_by_relation.py:15-19`；`script/workflow/paper_journal_chain_etl.py:409,425` | 与《关联关系脚本整理说明》序号 7"REFERENCED_BY 已实现（referenced_by_relation.py）"直接矛盾——该脚本源表即本表 |
| `dwd_org_heis_info` | `script/relation_extractors_one_relation/resolvers.py:68-84`（`ExactOrganizationResolver._SOURCES` 七表 SELECT，机构域全部边脚本共用，`org_edges.py:505` 每次 transform 加载）；`script/entity_extractors_one_entity/org_catalog.py:70`（39 张 TableSpec 之一）；`organization_ETL/run_etl.py` preflight 对全部 39 张做 information_schema 校验，缺表即硬错误 | "纯顶点补充，非硬依赖"不成立：不产边属实，但缺表则机构域**一条边都建不出来**（resolver 抛错、preflight 拒跑） |
| `dwd_special_hongkong_company` / `dwd_special_aomen_company` | 同上 `resolvers.py:73-76,82`；`org_catalog.py:117,123`；另 `script/load_patent_relations.py:44-54` 与 `relation_extractors_one_relation/patent_matching.py:38-44` 将其（含 heis）列为 APPLIED_BY/OWNED_BY 唯一合法机构目标来源 | 同上；且这三张缺席时专利申请边目标候选池静默缩水（不崩、丢边） |
| `dwd_org_stock_base` | `script/entity_extractors_one_entity/org_catalog.py:72-77`（organization_enrichment 顶点）；`script/organization_etl_common.py:143`；属 39 张 preflight 范围 | "抽取脚本侧不产九模块读的边"前半句属实，但表本身被实体注入读取；只建本文 35 张机构表，org ETL preflight 直接失败 |

### 2. 缺失列 / 列口径问题

- `dwd_scholar.scholar_org_id`：`script/load_scholar_entities.py:144-155`、`load_scholar_relations.py:214-221` 均按 information_schema 探测该列（dev 库实际存在），`person_entity.py:81` 映射 `organization_id`。按本文 DDL 重建不报错，但 AFFILIATED_WITH 会从 confidence 1.0（org_id 直连）**静默降级**为 0.6（机构名匹配），Person.organization_id 溯源丢失。
- 境外机构（forg）系列 DDL 无 `data_source`/`created_time`/`updated_time` 审计列（若为实测输出则属实情，但需注明）：`organization_relation_etl.py:985-993` 的水位增量对无时间列表静默退化为全量重跑，`source_update_time` 溯源为空。
- ORM 与本文 DDL 存在版本差待对齐：`db_model/scholar.py` 映射 `id`/`scholar_org_id`；`db_model/domestic_organization.py:1222-1248` 将 stock 两表信用代码列映射为 `social_credit_code`，而本文 DDL 为 `external_id`；`dwd_org_org_product_info` ORM 的 `industry_class`（背景分析在用）不在本文 DDL。请注明本文 DDL 实测自哪个库哪个版本，避免"修好库指向后又撞 unknown-column"。

### 3. "未收录的表"理由勘误

| 原排除理由 | 核查结论 |
|---|---|
| Report 三表"九模块不读 Report 域（AUTHOR_OF_REPORT / REPORT_ORG / REPORT_RELATED_PROJECT 无装载脚本）" | **错误**。Report 顶点有装载（report_entity.py，已平台注册）；dwd_zh_report_paper 是 REFERENCED_BY 的源表且默认必跑。"无装载脚本"仅对 AUTHOR_OF_REPORT / REPORT_ORG / REPORT_RELATED_PROJECT 三条边成立 |
| heis / hongkong / aomen"纯顶点补充，不产生任何九模块读取的边（非硬依赖）" | **错误**。是机构域边解析器（resolvers.py 七表）与 org ETL preflight（39 表）的硬依赖 |
| `dwd_org_stock_base`"抽取脚本侧不产九模块读的边" | **半对**。无边属实；但被 organization_enrichment 实体装载读取，且在 preflight 39 表内 |
| `dwd_org_tag_info`"无 ETL 脚本引用" | 属实（仅 `dao/organization.py:51-53` + `db_model/domestic_organization.py:1284-1302` 运行时用） |
| `scholar`"仅 legacy load_graph.py 使用" | 属实（且 load_graph.py 实际读的也是 DwdScholar/dwd_scholar，`scholar` ORM 类为死代码） |

软性漏记（建议补入"未收录"并注明理由）：`dwd_rel_project_paper` / `dwd_rel_project_patent`——`load_project_graph.py:400-427`、`has_output_relation.py:162-163` 存在性保护读取，仅产出 cross_domain 报告项、不建边。

### 4. 抽取脚本执行层已知问题（影响"验证各抽取脚本可行性"的目标）

- `load_paper_journal_graph.py`：BATCH=1 逐行 HTTP INSERT；`batch_insert_vertex/edge`（:81-89,107-112）首错后全部吞掉、ok 计数虚高 → **静默丢点/丢边**；增量模式对期刊/引文/报告仍是全量扫；CITES/CITED_BY 写向本脚本不创建的 `paper_ref_`/`paper_cit_` 桩 VID（须先跑 `load_paper_relation.py`，否则悬空边）。
- `industry_chain_etl/load_industry_chain_graph.py:74-80`、`backfill_chain_org_nodes.py:88-94`：`_write` 吞一切异常仍返回 len(rows)，"写入完成 N"虚报实际写入量。
- 陈旧硬编码溯源：`load_paper_relation.py:66-67`（INGEST_BATCH="paper_relation_0725" / INGEST_TIME="2026-07-26"）、`attach_provenance.py:40-41` 与 `backfill_stub_journals.py`（"2026-08-11T00:00:00Z"）、产业链两脚本（2026-08-05/10）——重跑仍打旧时间戳。
- `org_edges.py:502-507`：`ExactOrganizationResolver` 每个 transform 全量扫 7 张表重建索引，批量越多浪费越大。
- `relation_extractors_one_relation/common.py:346-366`：非唯一 `ORDER BY 1` 上 LIMIT/OFFSET 分页，运行中写入会跳行/重行；水位为本地文件（`script/.etl_watermark/`），跨机器/容器不共享。
- 学者/专利关系脚本整表 `.all()` 进内存、无水位全量重跑（靠写侧幂等兜底）：dev 量级可行，生产量级不可。

正面确认：66 张收录表分域逐一核对全部真实消费（学者 5/5、论文期刊 12/12、项目 4/4、专利 6/6、机构 35/35、产业链 4/4，无 padding）；抽查 SQL 引用列名全部存在于本文 DDL；`etl_watermark.py` 原子写、成功才推进；`load_patent_graph.py` keyset 分页 + 批内去重 + 被拒批次二分重试；one-relation 包确定性 rank 的 `INSERT EDGE @rank` 幂等覆盖设计良好。

### 5. 修订清单（待办）

1. 补 §1 的 9 张表 DDL（dev 库 `SHOW CREATE TABLE`），并为 `dwd_scholar` 补 `scholar_org_id` 列 → "共 66 张"改 75 张。
2. 按 §3 重写"未收录的表"，补记 `dwd_rel_project_paper` / `dwd_rel_project_patent`。
3. 若坚持 66 张口径，收录口径须改为"平台 one-relation 通道闭包"并逐条声明排除的旧 monolithic 入口，同时修正《关联关系脚本整理说明》序号 7 与本文的矛盾表述。
4. 按 §2 注明 DDL 实测库/版本，并核齐 ORM ↔ DDL 差异。
