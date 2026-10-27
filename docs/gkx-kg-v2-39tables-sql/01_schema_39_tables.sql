-- gkx_kg_v2 全 39 张表 DDL（14 实体 + 25 关系）
-- v_organization 含合并新列 confidence double（学者行=0.6，企业行=NULL）
-- 建库：CREATE DATABASE IF NOT EXISTS gkx_kg_v2 DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_general_ci;
-- MySQL dump 10.13  Distrib 8.0.46, for Linux (x86_64)
--
-- Host: localhost    Database: gkx_kg_v2
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `v_person`
--

DROP TABLE IF EXISTS `v_person`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_person` (
  `person_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键=scholar_id / author_id / md5(kind|org|姓名|生日|国籍)',
  `name_en` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_scholar.name_en / dwd_zh_author.en_name',
  `name_zh` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_scholar.name_zh / dwd_zh_author.zh_name',
  `name_cn` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← 任职批 executives_name/bo_name/entity_name/owners_name；法人批 lerep/legal_person',
  `email` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学者批恒空串',
  `source` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '常量 scholar（学者批）',
  `person_kind` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'shareholder/executive/beneficial_owner/actual_controller/legal_representative',
  `country_code` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'æ”¾å®½:å›¾ä¸Š34å­—ç¬¦æ—§æµ‹è¯•æ‰¹è„å€¼',
  `country` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dm_nationalities/country',
  `birth_date` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dm_birthdate/bo_birthdate/birth_date',
  `gender` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'æ”¾å®½:åŒä¸Š',
  `biography` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_scholar.bio / dm_biography',
  `bio_zh` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_scholar.bio_zh',
  `avatar` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_scholar.avatar',
  `scholar_org` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_scholar.scholar_org_name_zh OR scholar_org_name_en（摘要单位行/画布副标题）',
  `paper_nums` int DEFAULT NULL COMMENT '← dwd_scholar.paper_nums（M9 指标徽标）',
  `citation_nums` int DEFAULT NULL COMMENT '← dwd_scholar.citation_nums（M9 指标徽标）',
  `h_index` int DEFAULT NULL COMMENT '← dwd_scholar.h_index（M9 指标徽标）',
  `scholar_status` int DEFAULT NULL COMMENT '← dwd_scholar.status',
  `is_academician` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_scholar_talent_flag.academician（最新一条）',
  `research_fields` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_scholar_research_direction.fields（分号拼接；M6 主题兜底）',
  `work_experience_date` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_scholar.work_experience_date（M4 时段/M7 合作时间）',
  `work_experience_institution_en` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `work_experience_department_en` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `work_experience_position_en` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `work_experience_institution_zh` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `work_experience_department_zh` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M4 部门判定',
  `work_experience_position_zh` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M4 头衔/M7·M8 角色',
  `education_background_date` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M5 同期判定',
  `education_background_institution_en` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M5 同校判定（LOOKUP 兜底键）',
  `education_background_degree_en` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M5 同学历判定',
  `education_background_institution_zh` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M5 同校判定（LOOKUP 兜底键）',
  `education_background_degree_zh` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M5 同学历判定',
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_method` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_evidence` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_base` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci COMMENT '整源行 JSON（作者批含 affiliation）',
  `coauthor_ids` json DEFAULT NULL,
  `affiliation_org_ids` json DEFAULT NULL,
  `scholar_org_name_zh` mediumtext COLLATE utf8mb4_general_ci,
  `scholar_org_name_en` mediumtext COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`person_id`),
  KEY `idx_name_zh` (`name_zh`),
  KEY `idx_name_en` (`name_en`),
  KEY `idx_source` (`source_table`,`source_record_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专家/人物（四来源融合）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_paper`
--

DROP TABLE IF EXISTS `v_paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_paper` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键=源表 id',
  `title_zh` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← zh_name',
  `title_en` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← en_name',
  `doi` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `publication_year` varchar(8) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← cover_year_start（M3 完成时间/M6 时间过滤）',
  `publication_date` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← cover_date_start',
  `language` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← zh.language_classify / en.language',
  `document_type` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← paper_type',
  `publication_type` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `publication_id` bigint DEFAULT NULL COMMENT 'â† dwd_zh/en_paper.publication_idï¼›PUBLISHED_IN å…³ç³»çš„å®žä½“ä¾§å¤–é”®ï¼ˆ=kg_journal ä¸»é”®ï¼‰',
  `volume` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `issue` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `start_page` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← first_page',
  `end_page` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← last_page',
  `is_oa` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← open_access',
  `source_url` text COLLATE utf8mb4_general_ci COMMENT '← paper_url',
  `source` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← data_source（缺省 zh_paper/en_paper）',
  `created_time` datetime DEFAULT NULL,
  `updated_time` datetime DEFAULT NULL,
  `output_awards` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_scholar_papers.operator_remarks（严格 JSON 门禁）',
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_method` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_evidence` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_base` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `related_dois` json DEFAULT NULL COMMENT '相关论文DOI清单←dwd_zh_paper_related.relevant(JSON内doi)+dwd_en_paper_related.doi 按论文聚合(10-26补,RELATED_TO连接键)',
  `author_ids` json DEFAULT NULL,
  `keyword_ids` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_doi` (`doi`(191)),
  KEY `idx_pub_year` (`publication_year`),
  KEY `idx_source` (`source_table`,`source_record_id`),
  KEY `idx_pubid` (`publication_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='论文（中英论文表+学者论文表合并）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_patent`
--

DROP TABLE IF EXISTS `v_patent`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_patent` (
  `patent_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `publication_number` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `application_number` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← application_reference JSON $.apno',
  `application_kind` varchar(8) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country_code` varchar(8) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `publication_date` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← publication_reference JSON $.pbdt',
  `application_date` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← application_reference JSON $.apdt；M7 合作时间',
  `granted_number` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `grant_date` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent_legal.dates_of_public_availability $.date',
  `status` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent_legal.status',
  `anticipated_expiration` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent_legal.anticipated_expiration',
  `title_original` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_patent_title.titles（JSON text/content 换行连接）',
  `title_en` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent_title.title_localized',
  `title_zh` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent_title.title_zh',
  `abstract_zh` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_patent_abstract.abstract_zh',
  `language` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent.language（JSON 数组逗号join）',
  `main_ipcr` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← main_classification_ipcr',
  `further_ipcr` mediumtext COLLATE utf8mb4_general_ci COMMENT '← further_classification_ipcr（JSON 快照）',
  `main_cpc` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← main_classification_cpc',
  `further_cpc` mediumtext COLLATE utf8mb4_general_ci COMMENT '← further_classification_cpc（JSON 快照）',
  `keywords` mediumtext COLLATE utf8mb4_general_ci COMMENT '← dwd_patent.keywords（JSON 快照；M3 所属领域）',
  `citation_nums` int DEFAULT NULL COMMENT '← dwd_patent_cited.reference_cited',
  `cited_by_nums` int DEFAULT NULL COMMENT '← dwd_patent_cited.cited_by_nums',
  `patent_value` int DEFAULT NULL COMMENT '← dwd_patent.value',
  `simple_family_number` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← dwd_patent_family.simple_family_number',
  `db_source` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `title` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '展示回退链列（演示批/回填）',
  `source` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `output_awards` mediumtext COLLATE utf8mb4_general_ci,
  `evaluation` mediumtext COLLATE utf8mb4_general_ci,
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_method` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_evidence` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_base` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `inventors` mediumtext COLLATE utf8mb4_general_ci,
  `applicants` mediumtext COLLATE utf8mb4_general_ci,
  `assignees` mediumtext COLLATE utf8mb4_general_ci,
  `source_patent_row_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_pubnum` (`publication_number`),
  KEY `idx_title_zh` (`title_zh`(191)),
  KEY `idx_family` (`simple_family_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利（五子表聚合）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_patent_family`
--

DROP TABLE IF EXISTS `v_patent_family`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_patent_family` (
  `family_number` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键← dwd_patent_family.simple_family_number',
  `organization_base` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`family_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利同族';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_project`
--

DROP TABLE IF EXISTS `v_project`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_project` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `project_number` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `title` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `project_host` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `project_source` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `project_level` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `funded_amount` double DEFAULT NULL,
  `discipline` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `discipline_code` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fund_category` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `funded_region` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← funded_province（改名）',
  `approval_year` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'date→ISO 文本；M7 合作时间',
  `approval_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `research_period` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `abstract` mediumtext COLLATE utf8mb4_general_ci,
  `final_report_abstract` mediumtext COLLATE utf8mb4_general_ci COMMENT '仅中文项目表有；英文表恒空',
  `project_page_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '常量 zh_project/en_project',
  `total_outputs` int DEFAULT NULL COMMENT '以下 11 计数列 ← dwd_*_project_output 同名列',
  `journal_articles_count` int DEFAULT NULL,
  `conference_papers_count` int DEFAULT NULL,
  `books_count` int DEFAULT NULL,
  `degree_papers_count` int DEFAULT NULL,
  `patents_count` int DEFAULT NULL,
  `clinical_trials_count` int DEFAULT NULL COMMENT '中文表恒 0',
  `products_count` int DEFAULT NULL COMMENT '恒 0（SQL 常量）',
  `awards_count` int DEFAULT NULL,
  `reports_count` int DEFAULT NULL,
  `other_outputs_count` int DEFAULT NULL,
  `output_awards` mediumtext COLLATE utf8mb4_general_ci COMMENT '← output_awards JSON 规范化串；M3 奖项',
  `keywords` mediumtext COLLATE utf8mb4_general_ci COMMENT '← keywords JSON 快照',
  `evaluation` mediumtext COLLATE utf8mb4_general_ci COMMENT '← operator_remarks 严格门禁',
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_method` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `match_evidence` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `leader_person_ids` json DEFAULT NULL,
  `participant_person_ids` json DEFAULT NULL,
  `funded_org_ids` json DEFAULT NULL,
  `participants` mediumtext COLLATE utf8mb4_general_ci,
  `funded_institution` mediumtext COLLATE utf8mb4_general_ci,
  `participating_institution` mediumtext COLLATE utf8mb4_general_ci,
  `output_journal_articles` mediumtext COLLATE utf8mb4_general_ci,
  `output_conference_papers` mediumtext COLLATE utf8mb4_general_ci,
  `output_degree_papers` mediumtext COLLATE utf8mb4_general_ci,
  `output_patents` mediumtext COLLATE utf8mb4_general_ci,
  `output_reports` mediumtext COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`),
  KEY `idx_title` (`title`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='项目（中英项目表+产出计数合并）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_organization`
--

DROP TABLE IF EXISTS `v_organization`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_organization` (
  `org_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键← org_id/company_id/entity_eid 候选链；链上回填=antitypic',
  `name_cn` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '候选链 name_cn/org_loc_name/company_name/n_company_name/traditional_name/name_alias/name_en',
  `name_en` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← name_en/en_name',
  `source` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `external_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← external_id/company_code/school_code/credit_no；链上回填=credit_code',
  `province` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `city` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `area` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country_code` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `address` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← address/company_address/reg_address',
  `postal_code` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `phone` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `email` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `legal_rep` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← lerep/legal_person/legal_name',
  `org_type` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← org_type/univ_type/company_type/industry_type',
  `org_size` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← person_num/employees_number',
  `founded_year` int DEFAULT NULL COMMENT '← incorporation_year/est_year/incorporation_date',
  `listing_status` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← listing_status/listed_status（stock_base）；M7 行业地位/经营状况',
  `listed_date` datetime DEFAULT NULL COMMENT '← stock_base.listed_date',
  `registered_capital` double DEFAULT NULL COMMENT '← registered_capital_value/capital_num/capital；M7 经营状况',
  `capital_currency` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← capital_currency/currency_code/currency',
  `industry_class` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← industry/industry_class/industry_l1_name；M7 合作领域/M9 副标题',
  `stock_code` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← stock_base.stock_code',
  `stock_noun` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← stock_base.stock_noun',
  `stock_type` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← stock_base.stock_type；M7 行业地位',
  `org_kind` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源表常量（domestic_organization/domestic_university/…/industry_chain_enterprise）',
  `description` mediumtext COLLATE utf8mb4_general_ci COMMENT '← description/main_activities/business_scope；M7',
  `main_products` mediumtext COLLATE utf8mb4_general_ci COMMENT '← main_products/main_prod（产品经营表）/tech_product聚合（链上回填）；M7',
  `organization_base` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `manual_disabled` int DEFAULT NULL COMMENT '修正中心运行时列',
  `correction_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '修正中心运行时列',
  `corrected_at` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '修正中心运行时列',
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci COMMENT '多源按 table:record_id 合并；M7 背景摊平',
  `shareholders` json DEFAULT NULL COMMENT '股东清单←dwd_org_shareholder_info(境内:{inv_org_id,owners_name,owners_type,ownership_percentage})+dwd_forg_shareholder_info(境外:{owners_name,ownership_percentage},inv侧需按名解析)(10-26补,SHAREHOLDER_OF连接键)',
  `forg_subsidiaries` json DEFAULT NULL COMMENT '子公司/关联方←gkx_element.dwd_forg_subsidiary_info[{affiliate,affiliates_company_id,affiliates_name}](10-26补,SUBSIDIARY_OF连接键,图上118边唯一来源表)',
  `sub_orgs` json DEFAULT NULL COMMENT '境内母子公司对←gkx_dwd_local.dwd_org_subsidiary_info[{sub_org_id,sub_name_cn}](10-26补,图上SUBSIDIARY_OF未用此表)',
  `industry_node_ids` json DEFAULT NULL,
  `executives` json DEFAULT NULL,
  `invests` json DEFAULT NULL,
  `acquires` json DEFAULT NULL,
  `actual_controllers` json DEFAULT NULL,
  `beneficial_owners` json DEFAULT NULL,
  `confidence` double DEFAULT NULL COMMENT '置信度(scholar_affiliation行=dwd_scholar_work_experience物化props.confidence,企业行NULL)',
  PRIMARY KEY (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_stock_code` (`stock_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='机构/企业（十来源+链上回填合并）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_news`
--

DROP TABLE IF EXISTS `v_news`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_news` (
  `news_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键=链上 news_id / 机构要闻行 md5',
  `title` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← news_title（链上 or title 兜底）',
  `content` mediumtext COLLATE utf8mb4_general_ci COMMENT '← news_content / summary（链上）',
  `release_date` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← news_date / relaese_date（源表列名原样拼写）',
  `original_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← original_textlink；链上来源恒空',
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'dwd_org_important_news_info / dwd_industry_chain_news_info',
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`news_id`),
  KEY `idx_release_date` (`release_date`),
  KEY `idx_orgid` (`organization_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='新闻（机构要闻+产业链新闻）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_event`
--

DROP TABLE IF EXISTS `v_event`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_event` (
  `event_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键=stable_record_id(表级复合键)',
  `event_type` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '表级常量（annual_finance/financing/bid/bankruptcy/shixin/zhixing/judicial_case 等）',
  `raw_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '同 event_id 口径',
  `title` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '候选链 title/project_name/case_title/job_title/funding_round/…；全空→表中文名',
  `content` mediumtext COLLATE utf8mb4_general_ci COMMENT '候选链 content/penalty_content/violation_fact/legal_obligation/exec_target/…；全空→整行 JSON',
  `case_no` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `case_cause` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '候选链 case_cause/case_type/case_type_tag',
  `occur_date` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '候选链 publish_time/public_date/penalty_date/procedure_date/filing_date/occur_period/year；M8 筛选',
  `amount` double DEFAULT NULL COMMENT '候选链 amount/funding_amount/fine_amount/exec_target/project_budget_amount/total_assets；M8 影响力分/M9 徽标',
  `currency` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '候选链 currency/currency_code/funding_currency_code/amount_unit',
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '16 张事件源表名（分表映射见设计文档 3.6）',
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `case_role` mediumtext COLLATE utf8mb4_general_ci,
  `exec_person_type` mediumtext COLLATE utf8mb4_general_ci,
  `party_role_type` mediumtext COLLATE utf8mb4_general_ci,
  `u_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`event_id`),
  KEY `idx_type_date` (`event_type`,`occur_date`),
  KEY `idx_orgid` (`organization_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='事件（16 表统一口径）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_journal`
--

DROP TABLE IF EXISTS `v_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_journal` (
  `publication_id` bigint NOT NULL COMMENT '主键=publication_id',
  `name_zh` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← zh_name',
  `name_en` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← en_name',
  `name_abbr` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← name_abbr（两表同列）',
  `issn` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← zh.issn / en.issn_print',
  `eissn` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← zh.eissn / en.issn_online',
  `country` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `founding_time` int DEFAULT NULL COMMENT '← zh.founding_time / en.establish_time',
  `impact_factor` double DEFAULT NULL,
  `is_sci` tinyint DEFAULT NULL COMMENT 'M6 期刊分级',
  `jcr_zone` varchar(2) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '仅英文刊表；M6 期刊分级',
  `scope_zone` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '仅英文刊表（中科院分区）；M6 期刊分级',
  `sub_quartile` tinyint DEFAULT NULL COMMENT '仅中文刊表；M6 期刊分级',
  `top` tinyint DEFAULT NULL COMMENT '仅英文刊表；M6 期刊分级',
  `zh_core` text COLLATE utf8mb4_general_ci COMMENT '← zh.classify_list（北大核心/CSCD 等）；M6 期刊分级',
  `cite_nums` int DEFAULT NULL COMMENT '仅中文刊表',
  `annual_publication` int DEFAULT NULL,
  `publication_cycle` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← zh.publication_cycle / en.publish_period',
  `source` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '常量 zh_journal/en_journal',
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`publication_id`),
  KEY `idx_name_zh` (`name_zh`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='期刊（中英期刊表合并；分级六列全保留）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_keyword`
--

DROP TABLE IF EXISTS `v_keyword`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_keyword` (
  `keyword_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键=md5(NFKC+空白折叠+casefold(词))',
  `keyword` mediumtext COLLATE utf8mb4_general_ci NOT NULL COMMENT 'æ”¹text:å›¾ä¸Š240ç‚¹ä¸º65kå­—ç¬¦è¯è¡¨ä¸²',
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_base` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `citation_nums` int DEFAULT NULL COMMENT '该关键词下论文被引总量(派生:dwd_zh_paper_citation.citation_num按DOI关联kg_paper再经HAS_KEYWORD边汇总,2026-10-27 MANUAL_BACKFILL_1027C)',
  PRIMARY KEY (`keyword_id`),
  KEY `idx_keyword` (`keyword`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='关键词（四来源归一词）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_report`
--

DROP TABLE IF EXISTS `v_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_report` (
  `report_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键；zh=UUID，en=KJBG 编码',
  `title_cn` varchar(1500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '中文报告题名',
  `abstract_cn` text COLLATE utf8mb4_general_ci COMMENT '中文摘要',
  `keywords_cn` json DEFAULT NULL COMMENT '中文关键词',
  `report_type` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告类型（最终报告等）',
  `report_category` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告分类（医药、卫生等）',
  `approval_year` int DEFAULT NULL COMMENT '立项/批准年份',
  `preparation_time` varchar(10) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '编写时间',
  `project_annual_number` int DEFAULT NULL COMMENT '项目年度编号',
  `contact_phone` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '联系电话',
  `source_org` json DEFAULT NULL COMMENT '来源机构（zh）',
  `related_institutions` json DEFAULT NULL COMMENT '相关机构',
  `related_paper_id` json DEFAULT NULL COMMENT '相关论文 id',
  `related_project_id` json DEFAULT NULL COMMENT '相关项目 id',
  `related_projects` json DEFAULT NULL COMMENT '相关项目（名称）',
  `visibility_scope` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '可见范围',
  `title_en` mediumtext COLLATE utf8mb4_general_ci COMMENT '英文报告题名',
  `abstract_en` longtext COLLATE utf8mb4_general_ci COMMENT '英文摘要',
  `keywords_en` json DEFAULT NULL COMMENT '英文关键词',
  `category` varchar(302) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告分类（en）',
  `document_type` varchar(212) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文档类型',
  `report_number` varchar(174) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告编号',
  `contract_number` varchar(182) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合同号',
  `corporate_author` json DEFAULT NULL COMMENT '机构作者',
  `author_id` json DEFAULT NULL COMMENT '作者 id',
  `country` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '国家',
  `pub_year` int DEFAULT NULL COMMENT '出版年份（en）',
  `publication_date` varchar(8) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '出版日期（en）',
  `source_agency` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源机构（en）',
  `related_literature_id` json DEFAULT NULL COMMENT '相关文献 id',
  `authors` json DEFAULT NULL COMMENT '作者列表',
  `organization` mediumtext COLLATE utf8mb4_general_ci COMMENT '所属机构（zh=json / en=文本，取宽存文本）',
  `content` longtext COLLATE utf8mb4_general_ci COMMENT '报告正文',
  `page_count` int DEFAULT NULL COMMENT '页数',
  `related_author_id` json DEFAULT NULL COMMENT '相关作者 id',
  `related_authors` json DEFAULT NULL COMMENT '相关作者（名称）',
  `related_literature` json DEFAULT NULL COMMENT '相关文献',
  `related_org_id` json DEFAULT NULL COMMENT '相关机构 id',
  `file_path` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文件路径',
  `file_type` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文件类型',
  `source_url` text COLLATE utf8mb4_general_ci COMMENT '来源链接',
  `dwd_id` bigint DEFAULT NULL COMMENT '数仓代理键',
  `table_data_source` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '数据来源标记（源表恒 NULL）',
  `is_deleted` smallint DEFAULT NULL COMMENT '删除标记（两表恒 0）',
  `insert_remark` smallint DEFAULT NULL,
  `operator_remarks` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `creater` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `updater` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `created_time` datetime DEFAULT NULL,
  `updated_time` datetime DEFAULT NULL,
  PRIMARY KEY (`report_id`),
  KEY `idx_title_cn` (`title_cn`(191)),
  KEY `idx_title_en` (`title_en`(191)),
  KEY `idx_pub_year` (`pub_year`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='研究报告（dwd_zh_report+dwd_en_report 合一，一实体一表）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_product`
--

DROP TABLE IF EXISTS `v_product`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_product` (
  `product_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键=md5(NFKC+casefold(name))',
  `name` mediumtext COLLATE utf8mb4_general_ci COMMENT 'æ”¹text:å›¾ä¸Š1518å­—ç¬¦äº§å“ä¸²',
  `category` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '← target_item_type/industry_class',
  `description` mediumtext COLLATE utf8mb4_general_ci COMMENT '← description/main_activities',
  `organization_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_update_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `producer_org_ids` json DEFAULT NULL COMMENT '生产商机构id清单←dwd_org_org_product_info(org_id,main_prod)+dwd_forg_product_info(org_id,main_products) 按产品聚合(10-26补,PRODUCES完整连接键;organization_id单值只能存一个生产商)',
  PRIMARY KEY (`product_id`),
  KEY `idx_name` (`name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产品';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_industry_chain`
--

DROP TABLE IF EXISTS `v_industry_chain`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_industry_chain` (
  `chain_code` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `chain_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M8 产业链行/M9 摘要',
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`chain_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `v_industry_node`
--

DROP TABLE IF EXISTS `v_industry_node`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `v_industry_node` (
  `node_id` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键',
  `node_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'M8 链节点/M9 核心技术层 label',
  `node_type` int DEFAULT NULL COMMENT '2=叶子环节（企业多挂叶）；M9 副标题候选',
  `level` int DEFAULT NULL,
  `node_seq` int DEFAULT NULL,
  `node_imp_level` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `node_stage` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `node_path` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_table` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_batch` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ingest_time` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `extra_json` mediumtext COLLATE utf8mb4_general_ci,
  `chain_code` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_system` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`node_id`),
  KEY `idx_node_name` (`node_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链节点';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_acquires`
--

DROP TABLE IF EXISTS `ev_acquires`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_acquires` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_actual_controller_of`
--

DROP TABLE IF EXISTS `ev_actual_controller_of`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_actual_controller_of` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_affiliated_with`
--

DROP TABLE IF EXISTS `ev_affiliated_with`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_affiliated_with` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(259) COLLATE utf8mb4_general_ci NOT NULL DEFAULT '',
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_applied_by`
--

DROP TABLE IF EXISTS `ev_applied_by`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_applied_by` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_authored_by`
--

DROP TABLE IF EXISTS `ev_authored_by`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_authored_by` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_belongs_to_node`
--

DROP TABLE IF EXISTS `ev_belongs_to_node`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_belongs_to_node` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_beneficial_owner_of`
--

DROP TABLE IF EXISTS `ev_beneficial_owner_of`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_beneficial_owner_of` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_cites`
--

DROP TABLE IF EXISTS `ev_cites`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_cites` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_coauthor_with`
--

DROP TABLE IF EXISTS `ev_coauthor_with`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_coauthor_with` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_executive_of`
--

DROP TABLE IF EXISTS `ev_executive_of`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_executive_of` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_funded_by`
--

DROP TABLE IF EXISTS `ev_funded_by`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_funded_by` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_has_keyword`
--

DROP TABLE IF EXISTS `ev_has_keyword`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_has_keyword` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_has_news`
--

DROP TABLE IF EXISTS `ev_has_news`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_has_news` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_has_node`
--

DROP TABLE IF EXISTS `ev_has_node`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_has_node` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_has_participant`
--

DROP TABLE IF EXISTS `ev_has_participant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_has_participant` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_invented_by`
--

DROP TABLE IF EXISTS `ev_invented_by`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_invented_by` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_invests_in`
--

DROP TABLE IF EXISTS `ev_invests_in`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_invests_in` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_involved_in`
--

DROP TABLE IF EXISTS `ev_involved_in`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_involved_in` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_leads`
--

DROP TABLE IF EXISTS `ev_leads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_leads` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_legal_rep_of`
--

DROP TABLE IF EXISTS `ev_legal_rep_of`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_legal_rep_of` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_member_of_family`
--

DROP TABLE IF EXISTS `ev_member_of_family`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_member_of_family` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_produces`
--

DROP TABLE IF EXISTS `ev_produces`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_produces` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_published_in`
--

DROP TABLE IF EXISTS `ev_published_in`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_published_in` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_shareholder_of`
--

DROP TABLE IF EXISTS `ev_shareholder_of`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_shareholder_of` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ev_subsidiary_of`
--

DROP TABLE IF EXISTS `ev_subsidiary_of`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ev_subsidiary_of` (
  `src_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-27 18:36:48
