
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
DROP TABLE IF EXISTS `dwd_bid_base_out`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`u_id`),
  KEY `idx_u_id` (`u_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标公告基础表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_bid_purchase_agency_out`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_u_id` (`u_id`),
  KEY `idx_company_id` (`company_id`),
  KEY `idx_company_name` (`company_name`)
) ENGINE=InnoDB AUTO_INCREMENT=101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标采购代理表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_bid_target_item_out`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_u_id` (`u_id`)
) ENGINE=InnoDB AUTO_INCREMENT=101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标标的物表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_bid_win_candidate_out`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_u_id` (`u_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招投标中标候选人表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_author`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_author` (
  `paper_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `author_sequence` int NOT NULL COMMENT '作者顺序/int ',
  `author_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者 id/varchar(32) ',
  `en_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者英文名/varchar(255) ',
  `zh_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献作者中文名/varchar(255) ',
  `email` json DEFAULT NULL COMMENT '文献作者email/json ',
  `correspond` tinyint DEFAULT NULL COMMENT '是否为通讯作者/tinyint ',
  `institution` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '作者单位名称/text ',
  `affiliation` json DEFAULT NULL COMMENT '文献作者地址/json ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`paper_id`,`author_sequence`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_author_sequence` (`author_sequence`),
  KEY `idx_author_id` (`author_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文文献作者详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`publication_id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_en_name` (`en_name`(191)),
  KEY `idx_name_abbr` (`name_abbr`),
  KEY `idx_issn_print` (`issn_print`),
  KEY `idx_issn_online` (`issn_online`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文期刊详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_abstract`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_paper_abstract` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `abstract_sequence` int NOT NULL COMMENT '摘要序号/int ',
  `language` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语种/varchar(255) ',
  `original_abstract` tinyint NOT NULL COMMENT '是否原始摘要/tinyint ',
  `en_abstract` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '摘要 英文/longtext ',
  `zh_abstract` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '摘要 中文/longtext ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`id`,`abstract_sequence`),
  KEY `idx_id` (`id`),
  KEY `idx_abstract_sequence` (`abstract_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文摘要信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_citation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_paper_citation` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献英文名/varchar(1024) ',
  `publication_en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献出版物英文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_en_name` (`publication_en_name`(191))
) ENGINE=InnoDB AUTO_INCREMENT=528 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文引用文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_classification`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文分类信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_funding`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_paper_funding` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `funds` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '基金/longtext ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文基金信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_reference`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_en_name` (`publication_en_name`(191)),
  KEY `idx_cover_year_start` (`cover_year_start`)
) ENGINE=InnoDB AUTO_INCREMENT=66990 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文参考文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_related`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_paper_related` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `relevant` json DEFAULT NULL COMMENT '相关文献/json ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '相关文献英文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文关联文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_paper_title`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_paper_title` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `title_sequence` int NOT NULL COMMENT '标题序号/int ',
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献英文名/varchar(1024) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献中文名/varchar(1024) ',
  `language_code` varchar(12) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语言代码/varchar(12) ',
  `language` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语种/varchar(255) ',
  `original_title` tinyint DEFAULT NULL COMMENT '是否原始标题/tinyint ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`id`,`title_sequence`),
  KEY `idx_id` (`id`),
  KEY `idx_title_sequence` (`title_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文标题信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_project`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_discipline_code` (`discipline_code`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国外项目信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_project_output`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国外项目-产出信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_report` (
  `report_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '外文报告id/varchar(64) ',
  `report_number` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告编号/varchar(64) ',
  `title_en` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '英文题名/varchar(512) ',
  `publication_date` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '发布时间/出版日期/varchar(8) ',
  `authors` json DEFAULT NULL COMMENT '作者/json ',
  `corporate_author` json DEFAULT NULL COMMENT '团体作者/json ',
  `source_agency` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源机构/出版社/varchar(64) ',
  `source_url` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告原文链接/varchar(512) ',
  `abstract_en` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '英文摘要/longtext ',
  `keywords_en` json DEFAULT NULL COMMENT '英文关键词/json ',
  `page_count` int DEFAULT NULL COMMENT '全文页数/int ',
  `document_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文档类型/varchar(64) ',
  `contract_number` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '合同编号/varchar(32) ',
  `content` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '正文内容/longtext ',
  `related_literature` json DEFAULT NULL COMMENT '相关文献/json ',
  `related_scholars` json DEFAULT NULL COMMENT '相关学者/json ',
  `updated_time` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `literature_id` json DEFAULT NULL COMMENT '相关文献ID/json ',
  `org_id` json DEFAULT NULL COMMENT '相关机构ID/json ',
  `authors_id` json DEFAULT NULL COMMENT '相关作者ID/json ',
  `scholar_id` json DEFAULT NULL COMMENT '相关学者ID/json ',
  `file_path` json DEFAULT NULL COMMENT '文件路径/json ',
  PRIMARY KEY (`report_id`),
  KEY `idx_report_id` (`report_id`),
  KEY `idx_report_number` (`report_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_report_author`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_report_author` (
  `authors_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者唯一标识ID/varchar(64) ',
  `authors_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者名称/varchar(64) ',
  `authors_unit` json NOT NULL COMMENT '作者所属机构/json ',
  `report_id` json NOT NULL COMMENT '外文报告ID集合/json ',
  `report_source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '报告所属来源/varchar(32) ',
  PRIMARY KEY (`authors_id`),
  KEY `idx_authors_id` (`authors_id`),
  KEY `idx_authors_name` (`authors_name`),
  KEY `idx_report_source` (`report_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告与作者关联表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_en_report_org`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_en_report_org` (
  `org_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构ID/varchar(64) ',
  `org_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(200) ',
  `org_country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构国别/varchar(50) ',
  `report_id` json NOT NULL COMMENT '外文报告ID集合/json ',
  `report_source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '报告所属来源/varchar(32) ',
  `report_source_2` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '报告所属来源/varchar(32) ',
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_org_name` (`org_name`),
  KEY `idx_org_country` (`org_country`),
  KEY `idx_report_source` (`report_source`),
  KEY `idx_report_source_2` (`report_source_2`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告与机构关联表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_act_contro_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '路径/varchar(255) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`)
) ENGINE=InnoDB AUTO_INCREMENT=1128 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构实控人信息（新增表）';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_base_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `industry_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '行业分类标准（新增字段）/varchar(255) ',
  PRIMARY KEY (`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构基本信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_beneficiary_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `indirect_percent` decimal(20,2) DEFAULT NULL COMMENT '间接持股比例/decimal(20,2) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`)
) ENGINE=InnoDB AUTO_INCREMENT=6377 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构受益人信息（新增表）';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_executive_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_forg_executive_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `executives_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '高管姓名/varchar(255) ',
  `executives_position` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '职位名称/varchar(255) ',
  `dm_birthdate` datetime DEFAULT NULL COMMENT '高管出生日期(新增字段)/datetime ',
  `dm_nationalities` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '高管国籍(新增字段)/varchar(255) ',
  `dm_biography` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`)
) ENGINE=InnoDB AUTO_INCREMENT=4912 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构高管信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_product_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_forg_product_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `description` varchar(368) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `main_products` varchar(1520) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构公司经营信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_shareholder_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_forg_shareholder_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `owners_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东名称/varchar(255) ',
  `ownership_percentage` decimal(20,2) DEFAULT NULL COMMENT '股权占比(%)/decimal(20,2) ',
  `owners_country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东所在国家代码/varchar(255) ',
  `owners_country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股东所在国家/varchar(255) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`)
) ENGINE=InnoDB AUTO_INCREMENT=21198 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构股东股权关联信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_stock_fin_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `research_development_employees_number` decimal(20,2) DEFAULT NULL COMMENT '研发人员数（无数据）/decimal(20,2) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`)
) ENGINE=InnoDB AUTO_INCREMENT=101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外上市企业财务信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_forg_subsidiary_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_forg_subsidiary_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `affiliate` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司id/varchar(255) ',
  `affiliates_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司名称/varchar(255) ',
  `affiliates_country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司国家代码/varchar(255) ',
  `affiliates_country` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司国家/varchar(255) ',
  `affiliates_company_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子公司唯一注册码/varchar(255) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`)
) ENGINE=InnoDB AUTO_INCREMENT=12300 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='海外机构子公司股权关联信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_industry_chain_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`chain_code`,`node_id`),
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_node_imp_level` (`node_imp_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链图谱';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_industry_chain_news_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`chain_code`,`news_id`),
  KEY `idx_chain_code` (`chain_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业动态资讯';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_annual_financial_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`org_id`,`year`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='年报财务信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_bankruptcy_public_cases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`case_no`),
  KEY `idx_admin_org_id` (`admin_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='破产案件';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_bankruptcy_public_cases_list`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_bankruptcy_party_id` (`bankruptcy_party_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='破产案件当事人';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_base_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='机构基本信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_changerecord_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_update_date` (`update_date`)
) ENGINE=InnoDB AUTO_INCREMENT=101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='工商变更信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_company_abnormal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_abnormal_id` (`abnormal_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2063 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营异常';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_company_illegal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_sv_id` (`sv_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='严重违法';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_company_punish`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_penalty_id` (`penalty_id`)
) ENGINE=InnoDB AUTO_INCREMENT=336 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='行政处罚';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_executive_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_org_executive_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `executives_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '高管姓名/varchar(255) ',
  `executives_position` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '职位名称/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5601 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='高管信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_financing_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1074 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='融资事件';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_heis_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_org_heis_info` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学校名称/varchar(255) ',
  `school_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学校标识码/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `name_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学校英文名称/varchar(255) ',
  `est_year` decimal(20,0) DEFAULT NULL COMMENT '建立时间/decimal(20,0) ',
  `address` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '学校地址/text ',
  `addr_lng` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址对应经度/varchar(255) ',
  `addr_lat` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址对应维度/varchar(255) ',
  `province` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址所在省/varchar(255) ',
  `city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址所在市/varchar(255) ',
  `area` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址所在区/varchar(255) ',
  `univ_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '学校类型/varchar(255) ',
  `web_link` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '官方网址/text ',
  `comp_dept` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '主管部门/varchar(255) ',
  `school_nature` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '办学层次/varchar(255) ',
  `postal_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '邮政编码/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_school_code` (`school_code`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_name_en` (`name_en`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='高校基本信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_important_news_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_news_date` (`news_date`)
) ENGINE=InnoDB AUTO_INCREMENT=1014 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='重点资讯';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_industry_chain_dtl`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`chain_code`,`node_id`,`antitypic`),
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业关联企业信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_industry_chain_prod_dtl`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`chain_code`,`antitypic`,`tech_product`),
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链企业关联产品信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_invest_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_inv_org_id` (`inv_org_id`),
  KEY `idx_inv_external_id` (`inv_external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=4299 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='投资事件';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_merger_acquisition_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_acquiring_org_id` (`acquiring_org_id`),
  KEY `idx_acquiring_external_id` (`acquiring_external_id`),
  KEY `idx_acquired_org_id` (`acquired_org_id`),
  KEY `idx_acquired_external_id` (`acquired_external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1023 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='并购事件';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_opt_judicial_case`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_case_id` (`case_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='司法案件信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_org_product_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='经营信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_recruit_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='招聘信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_risk_shixin`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_dishonest_id` (`dishonest_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='失信被执行人';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_risk_tax_punish`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_tax_vio_id` (`tax_vio_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='税收违法';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_risk_zhixing`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_exec_person_id` (`exec_person_id`),
  KEY `idx_exec_basis_no` (`exec_basis_no`),
  KEY `idx_web_id` (`web_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2101 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='被执行人';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_shareholder_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_inv_org_id` (`inv_org_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2502 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='股东信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_stock_base`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_org_stock_base` (
  `stock_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '股票代码/varchar(255) ',
  `stock_noun` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '股票简称/varchar(255) ',
  `stock_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '上市板块/varchar(255) ',
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一社会信用代码/varchar(255) ',
  `listed_date` datetime DEFAULT NULL COMMENT '上市日期/datetime ',
  `listed_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '上市状态/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_external_id` (`external_id`)
) ENGINE=InnoDB AUTO_INCREMENT=5946 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业基本信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_org_stock_finance_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_stock_code` (`stock_code`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_occur_period` (`occur_period`)
) ENGINE=InnoDB AUTO_INCREMENT=5554 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='上市企业主要财务指标';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent_abstract`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent_cited`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent_family`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent_legal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent_title`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_patent_transfer`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_patent_transfer` (
  `id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `patent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `country` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `transfer_effective_date` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `transfer_before` json DEFAULT NULL,
  `transfer_after` json DEFAULT NULL,
  `db_source` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL,
  `update_time` datetime NOT NULL,
  PRIMARY KEY (`patent_id`),
  KEY `idx_dwd_patent_transfer_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='专利转移信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_research_institute_base_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_external_id` (`external_id`),
  KEY `idx_name_cn` (`name_cn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='科研机构基本信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_sample_source`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_sample_source` (
  `id` int NOT NULL,
  `title` varchar(512) DEFAULT NULL,
  `author_list` text,
  `pub_year` int DEFAULT NULL,
  `doi` varchar(128) DEFAULT NULL,
  `abstract` text,
  `source_type` varchar(32) DEFAULT NULL,
  `journal` varchar(128) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_scholar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`scholar_id`),
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_scholar_coauthor`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`scholar_id`,`co_scholar_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_co_scholar_id` (`co_scholar_id`),
  KEY `idx_co_scholar_name_en` (`co_scholar_name_en`),
  KEY `idx_co_scholar_name_zh` (`co_scholar_name_zh`),
  KEY `idx_status` (`status`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者合作者关系';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_scholar_paper_relation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`paper_id`,`scholar_id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_citations` (`citations`),
  KEY `idx_publish_time` (`publish_time`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者论文关系';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_scholar_papers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_scholar_papers` (
  `id` bigint DEFAULT NULL,
  `zh_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '中文题目/varchar(500) ',
  `en_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '英文题目/varchar(500) ',
  `authors` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '作者列表/text ',
  `paper_url` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '论文原始链接/varchar(1024) ',
  `cover_date_start` datetime DEFAULT NULL COMMENT '发表时间/datetime ',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间/datetime ',
  `status` int DEFAULT NULL COMMENT '状态/int ',
  `zh_abstract` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '中文摘要/text ',
  `en_abstract` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '英文摘要/text ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'DOI/varchar(512) ',
  `publication_en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '期刊/会议英文名/varchar(1024) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_en_name` (`en_name`),
  KEY `idx_cover_date_start` (`cover_date_start`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`),
  KEY `idx_doi` (`doi`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=334531 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='论文信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_scholar_research_direction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_scholar_research_direction` (
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `fields` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '研究方向/text ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`scholar_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者研究方向';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_scholar_talent_flag`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_scholar_talent_flag` (
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(32) ',
  `academician` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '是否为院士/varchar(128) ',
  `create_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `update_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`scholar_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_academician` (`academician`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_update_time` (`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者人才标识';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_special_aomen_company`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_special_aomen_company` (
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `org_loc_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构本地名称/varchar(255) ',
  `en_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构英文名称/varchar(255) ',
  `incorporation_year` decimal(20,0) DEFAULT NULL COMMENT '成立年份/decimal(20,0) ',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期/datetime ',
  `country_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册国家代码/varchar(255) ',
  `city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册城市/varchar(255) ',
  `listing_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '上市状态/varchar(255) ',
  `owners_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构经济类型/varchar(255) ',
  `person_num` decimal(20,0) DEFAULT NULL COMMENT '员工人数/decimal(20,0) ',
  `company_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '统一编号/varchar(255) ',
  `company_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '登记状态/varchar(255) ',
  `capital` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册资本/varchar(255) ',
  `currency_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '注册资本币种/varchar(255) ',
  `company_est_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构运营状态代码/varchar(255) ',
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '地址/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_org_loc_name` (`org_loc_name`),
  KEY `idx_en_name` (`en_name`),
  KEY `idx_company_code` (`company_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='澳门企业';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_special_hongkong_company`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_special_hongkong_company` (
  `province_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '省份(英文缩写)/varchar(255) ',
  `name_cn` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(255) ',
  `name_en` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构英文名称/varchar(255) ',
  `traditional_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构繁体名称/varchar(255) ',
  `org_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构id/varchar(255) ',
  `company_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构编号/varchar(255) ',
  `company_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构类别/varchar(255) ',
  `incorporation_date` datetime DEFAULT NULL COMMENT '成立日期/datetime ',
  `company_status` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '机构现况/varchar(255) ',
  `remark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注/varchar(255) ',
  `liquidation_mode` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '清盘模式/varchar(255) ',
  `cancel_date` datetime DEFAULT NULL COMMENT '解散日期/datetime ',
  `mortgage` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '押记登记册/varchar(255) ',
  `imp_matters` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '重要事项/varchar(255) ',
  `create_time` datetime NOT NULL COMMENT '入库时间/datetime ',
  `br_code` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '商业登记代码/varchar(255) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`org_id`),
  KEY `idx_name_cn` (`name_cn`),
  KEY `idx_name_en` (`name_en`),
  KEY `idx_traditional_name` (`traditional_name`),
  KEY `idx_org_id` (`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='香港企业';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_special_taiwan_company`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_company_name` (`company_name`),
  KEY `idx_n_company_name` (`n_company_name`),
  KEY `idx_company_code` (`company_code`),
  KEY `idx_history_company_code` (`history_company_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='台湾企业';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zck_intl_policy`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zck_intl_policy` (
  `recordId` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '唯一ID/varchar(255) ',
  `sy_urltitle` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题原文/varchar(1000) ',
  `fy_urltitle` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题译文/varchar(1000) ',
  `sy_content` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '正文原文/longtext ',
  `fy_content` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '正文译文/longtext ',
  `sy_abstract` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '摘要原文/varchar(2000) ',
  `sy_media_area` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '所属区域/varchar(255) ',
  `ir_urldate` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '发布时间/varchar(255) ',
  `sy_media_product_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '媒体名称/varchar(255) ',
  `ir_urlname` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'URL链接/varchar(1000) ',
  `ir_language` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '语种/varchar(255) ',
  `media_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '媒体类型/varchar(255) ',
  PRIMARY KEY (`recordId`),
  KEY `idx_recordId` (`recordId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国际政策信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_author`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_author` (
  `paper_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `author_sequence` int NOT NULL COMMENT '作者顺序/int ',
  `author_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者 id/varchar(32) ',
  `en_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者英文名/varchar(255) ',
  `zh_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献作者中文名/varchar(255) ',
  `email` json DEFAULT NULL COMMENT '文献作者email/json ',
  `correspond` tinyint DEFAULT NULL COMMENT '是否为通讯作者/tinyint ',
  `institution` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '作者单位名称/text ',
  `affiliation` json DEFAULT NULL COMMENT '文献作者地址/json ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`paper_id`,`author_sequence`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_author_sequence` (`author_sequence`),
  KEY `idx_author_id` (`author_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文文献作者详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`paper_id`,`publication_id`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_zh_name` (`zh_name`(191)),
  KEY `idx_name_abbr` (`name_abbr`),
  KEY `idx_en_name` (`en_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文期刊详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_en_name` (`en_name`(191)),
  KEY `idx_zh_name` (`zh_name`(191)),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper_abstract`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_paper_abstract` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `abstract_sequence` int NOT NULL COMMENT '摘要序号/int ',
  `language` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语种/varchar(255) ',
  `original_abstract` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '是否原始摘要/varchar(1) ',
  `en_abstract` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '摘要 英文/longtext ',
  `zh_abstract` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '摘要 中文/longtext ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`id`,`abstract_sequence`),
  KEY `idx_id` (`id`),
  KEY `idx_abstract_sequence` (`abstract_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文摘要信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper_citation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_paper_citation` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `publication_id` bigint NOT NULL COMMENT '关联出版物信息/bigint ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献中文名/varchar(1024) ',
  `publication_zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '引用文献出版物中文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191))
) ENGINE=InnoDB AUTO_INCREMENT=2033 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文引用文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper_classification`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_paper_classification` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `scope` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '大类学科分类/varchar(20) ',
  `scope_zone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '小类学科分类/varchar(20) ',
  `keywords` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '论文关键字/longtext ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文分类信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper_reference`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_id` (`id`),
  KEY `idx_publication_id` (`publication_id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_publication_zh_name` (`publication_zh_name`(191)),
  KEY `idx_cover_year_start` (`cover_year_start`)
) ENGINE=InnoDB AUTO_INCREMENT=23020 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文参考文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper_related`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_paper_related` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `relevant` json DEFAULT NULL COMMENT '相关文献/json ',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '相关文献文献唯一识别号/varchar(512) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '相关文献中文名/varchar(1024) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_id` (`id`),
  KEY `idx_doi` (`doi`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB AUTO_INCREMENT=39901 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文关联文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_paper_title`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_paper_title` (
  `id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献id/varchar(64) ',
  `title_sequence` int NOT NULL COMMENT '标题序号/int ',
  `en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献英文名/varchar(1024) ',
  `zh_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文献中文名/varchar(1024) ',
  `language_code` varchar(12) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语言代码/varchar(12) ',
  `language` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '语种/varchar(255) ',
  `original_title` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '是否原始标题/varchar(1) ',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` datetime NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` datetime NOT NULL COMMENT '更新时间/datetime ',
  PRIMARY KEY (`id`,`title_sequence`),
  KEY `idx_id` (`id`),
  KEY `idx_title_sequence` (`title_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文标题信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_project`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_discipline_code` (`discipline_code`),
  KEY `idx_approval_year` (`approval_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内项目信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_project_output`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内项目-产出信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_report` (
  `report_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '中文报告id/varchar(64) ',
  `report_category` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告类别/varchar(64) ',
  `title_cn` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '中文题名/varchar(512) ',
  `authors` json DEFAULT NULL COMMENT '作者/json ',
  `organization` json DEFAULT NULL COMMENT '作者单位/完成单位/json ',
  `abstract_cn` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '中文摘要/longtext ',
  `keywords_cn` json DEFAULT NULL COMMENT '中文关键词/json ',
  `report_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '报告类型/varchar(32) ',
  `page_count` int DEFAULT NULL COMMENT '全文页数/int ',
  `preparation_time` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '编制时间/varchar(8) ',
  `approval_year` int DEFAULT NULL COMMENT '立项批准年/int ',
  `related_literature` json DEFAULT NULL COMMENT '相关文献/json ',
  `related_scholars` json DEFAULT NULL COMMENT '相关学者/json ',
  `related_institutions` json DEFAULT NULL COMMENT '相关机构/json ',
  `related_projects` json DEFAULT NULL COMMENT '相关项目/json ',
  `source_org` json DEFAULT NULL COMMENT '报告来源/json ',
  `source_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '报告原文链接/text ',
  `visibility_scope` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '可见范围/varchar(16) ',
  `project_annual_number` int DEFAULT NULL COMMENT '项目年度编号/int ',
  `contact_phone` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '联系电话/varchar(64) ',
  `updated_time` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '更新时间/varchar(8) ',
  `scholar_id` json DEFAULT NULL COMMENT '相关学者ID/json ',
  `org_id` json DEFAULT NULL COMMENT '相关机构ID/json ',
  `paper_id` json DEFAULT NULL COMMENT '相关论文ID/json ',
  `project_id` json DEFAULT NULL COMMENT '相关项目ID/json ',
  `file_path` json DEFAULT NULL COMMENT '文件路径/json ',
  PRIMARY KEY (`report_id`),
  KEY `idx_report_id` (`report_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文科技报告信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_report_org`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_report_org` (
  `org_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构ID/varchar(64) ',
  `org_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '机构名称/varchar(200) ',
  `org_xydm` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`org_id`),
  KEY `idx_org_id` (`org_id`),
  KEY `idx_org_name` (`org_name`),
  KEY `idx_org_xydm` (`org_xydm`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-机构关联表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_report_paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_report_paper` (
  `paper_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '论文ID/varchar(64) ',
  `paper_name` varchar(320) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `paper_doi` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `report_source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '报告所属来源/varchar(32) ',
  `report_id` json NOT NULL COMMENT '中文报告ID集合/json ',
  `paper_source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '论文来源/varchar(32) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_paper_id` (`paper_id`),
  KEY `idx_paper_name` (`paper_name`),
  KEY `idx_paper_doi` (`paper_doi`),
  KEY `idx_report_source` (`report_source`),
  KEY `idx_paper_source` (`paper_source`)
) ENGINE=InnoDB AUTO_INCREMENT=12807 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-论文关联表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_report_project`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_report_project` (
  `project_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目ID/varchar(64) ',
  `project_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目名称/varchar(200) ',
  `project_subject` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目领域/varchar(100) ',
  `project_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目类别/varchar(100) ',
  `project_number` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目编号/varchar(100) ',
  `report_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '中文报告ID集合/varchar(64) ',
  `project_source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '项目来源/varchar(32) ',
  PRIMARY KEY (`project_id`),
  KEY `idx_project_id` (`project_id`),
  KEY `idx_project_name` (`project_name`),
  KEY `idx_project_subject` (`project_subject`),
  KEY `idx_project_type` (`project_type`),
  KEY `idx_project_number` (`project_number`),
  KEY `idx_project_source` (`project_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-项目关联表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dwd_zh_report_scholar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dwd_zh_report_scholar` (
  `scholar_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者ID/varchar(64) ',
  `scholar_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '学者名字/varchar(64) ',
  `scholar_unit` json NOT NULL COMMENT '学者所属机构/json ',
  `scholar_project` json NOT NULL COMMENT '学者参与项目名称/json ',
  `report_id` json NOT NULL COMMENT '中文报告ID集合/json ',
  `report_source` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '报告所属来源/varchar(32) ',
  PRIMARY KEY (`scholar_id`),
  KEY `idx_scholar_id` (`scholar_id`),
  KEY `idx_scholar_name` (`scholar_name`),
  KEY `idx_report_source` (`report_source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='报告-人才关联表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dws_zck_policy`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dws_zck_policy` (
  `id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '唯一ID/varchar(255) ',
  `datatype` decimal(2,0) NOT NULL COMMENT '数据类型/decimal(2,0) ',
  `docstatus` decimal(2,0) NOT NULL COMMENT '状态（20-已发布，30-已撤销）/decimal(2,0) ',
  `title` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题（纯文本）/varchar(1000) ',
  `titlena` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题（富文本）/varchar(1000) ',
  `content` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '内容（纯文本）/longtext ',
  `contentNa` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `url` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '原文链接地址/varchar(1000) ',
  `issueno` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '发文字号/varchar(255) ',
  `indexno` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '索引号/varchar(255) ',
  `sitename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '站点名称/varchar(255) ',
  `crtime` datetime DEFAULT NULL,
  `pubtime` datetime NOT NULL COMMENT '发文日期（发布日期）/datetime ',
  `effectivetime` datetime DEFAULT NULL,
  `pubyear` varchar(4) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '发布年份/varchar(4) ',
  `area` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '地区/varchar(255) ',
  `policylevel` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '政策层级/varchar(255) ',
  `region` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '政策地区/varchar(255) ',
  `attachments` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '附件信息/longtext ',
  `keywords` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '关键词/varchar(1000) ',
  `abs` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '摘要/longtext ',
  `maelements` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '政策主旨要素/text ',
  `ma_keypoints` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '政策要点/text ',
  `allfactors` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '政策扶持要素/text ',
  `complextaginfojson` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标签集/text ',
  `pedigree` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '政策谱系/longtext ',
  `ma_contenttypenew` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文件类型/varchar(255) ',
  `pubdeptname` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '发布单位名称/varchar(255) ',
  `topic_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `expiration_date` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内政策信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `external_api_client`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `external_api_client` (
  `client_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `business_name` varchar(200) COLLATE utf8mb4_general_ci NOT NULL,
  `api_key_hash` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `key_prefix` varchar(12) COLLATE utf8mb4_general_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `scopes` json NOT NULL,
  `expires_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_admin_audit_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_admin_audit_log` (
  `id` varchar(36) NOT NULL,
  `actor_id` varchar(128) NOT NULL,
  `actor_name` varchar(128) NOT NULL,
  `action` varchar(64) NOT NULL,
  `resource_type` varchar(64) NOT NULL,
  `resource_id` varchar(256) NOT NULL,
  `detail` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_kg_admin_audit_actor` (`actor_id`,`created_at`),
  KEY `idx_kg_admin_audit_resource` (`resource_type`,`resource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_algorithm_job`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_algorithm_job` (
  `job_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `graph_space` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `created_by` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`job_id`),
  KEY `ix_kg_business_algorithm_job_graph_space` (`graph_space`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_client`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_client` (
  `client_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(200) COLLATE utf8mb4_general_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_graph_space`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_graph_space` (
  `space_name` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `client_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `is_shared_production` tinyint(1) NOT NULL,
  `shared_key` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `provision_request_id` varchar(36) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`space_name`),
  UNIQUE KEY `shared_key` (`shared_key`),
  KEY `ix_business_space_client` (`client_id`),
  CONSTRAINT `kg_business_graph_space_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `kg_business_client` (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_member`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_member` (
  `user_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `client_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `role` varchar(16) COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`user_id`),
  KEY `ix_business_member_client` (`client_id`),
  CONSTRAINT `kg_business_member_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `kg_business_client` (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_membership` (
  `user_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `client_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `role` varchar(16) COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`user_id`,`client_id`),
  KEY `client_id` (`client_id`),
  CONSTRAINT `kg_business_membership_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `kg_business_client` (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_membership_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_membership_state` (
  `user_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_space_policy`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_space_policy` (
  `space_name` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `visibility` varchar(16) COLLATE utf8mb4_general_ci NOT NULL,
  `client_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`space_name`),
  KEY `client_id` (`client_id`),
  CONSTRAINT `kg_business_space_policy_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `kg_business_client` (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_business_space_request`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_business_space_request` (
  `id` varchar(36) COLLATE utf8mb4_general_ci NOT NULL,
  `client_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `space_name` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `active_space_name` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `reason` text COLLATE utf8mb4_general_ci NOT NULL,
  `status` varchar(24) COLLATE utf8mb4_general_ci NOT NULL,
  `requested_by` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `reviewed_by` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `review_note` text COLLATE utf8mb4_general_ci NOT NULL,
  `last_error` text COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_business_active_request` (`client_id`,`active_space_name`),
  KEY `ix_business_request_client_status` (`client_id`,`status`),
  CONSTRAINT `kg_business_space_request_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `kg_business_client` (`client_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_correction_projection`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_correction_projection` (
  `id` varchar(36) NOT NULL,
  `target_type` varchar(32) NOT NULL,
  `target_id` varchar(256) NOT NULL,
  `payload` json NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `version` int NOT NULL DEFAULT '1',
  `last_correction_id` varchar(36) NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_correction_projection_target` (`target_type`,`target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_correction_review`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_correction_review` (
  `id` varchar(36) NOT NULL,
  `correction_id` varchar(36) NOT NULL,
  `action` varchar(32) NOT NULL,
  `actor_id` varchar(128) NOT NULL,
  `actor_name` varchar(128) NOT NULL,
  `note` text NOT NULL,
  `snapshot` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_kg_correction_review_correction` (`correction_id`,`created_at`),
  CONSTRAINT `fk_kg_correction_review_correction` FOREIGN KEY (`correction_id`) REFERENCES `kg_manual_correction` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_correction_sync_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_correction_sync_task` (
  `id` varchar(36) NOT NULL,
  `correction_id` varchar(36) NOT NULL,
  `idempotency_key` varchar(128) NOT NULL,
  `status` varchar(32) NOT NULL,
  `mysql_status` varchar(32) NOT NULL,
  `graph_status` varchar(32) NOT NULL,
  `attempts` int NOT NULL DEFAULT '0',
  `max_attempts` int NOT NULL DEFAULT '8',
  `next_retry_at` datetime DEFAULT NULL,
  `last_error` text NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_correction_sync_correction` (`correction_id`),
  UNIQUE KEY `uk_kg_correction_sync_idempotency` (`idempotency_key`),
  KEY `idx_kg_correction_sync_due` (`status`,`next_retry_at`),
  CONSTRAINT `fk_kg_correction_sync_correction` FOREIGN KEY (`correction_id`) REFERENCES `kg_manual_correction` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_graph_space_profile`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_graph_space_profile` (
  `space_name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `description` varchar(200) COLLATE utf8mb4_general_ci NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`space_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_graph_space_vector_db`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_graph_space_vector_db` (
  `id` varchar(36) COLLATE utf8mb4_general_ci NOT NULL,
  `graph_space` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `vector_database` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_general_ci NOT NULL,
  `last_error` text COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_graph_space_vector_db` (`graph_space`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_indirect_relation_annotation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_indirect_relation_annotation` (
  `source_vid` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `target_vid` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `annotation` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL DEFAULT (now()),
  `update_time` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`source_vid`,`target_vid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_manual_correction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_manual_correction` (
  `id` varchar(36) NOT NULL,
  `target_type` varchar(32) NOT NULL,
  `operation` varchar(16) NOT NULL,
  `target_id` varchar(256) NOT NULL,
  `title` varchar(255) NOT NULL,
  `reason` text NOT NULL,
  `before_data` json NOT NULL,
  `after_data` json NOT NULL,
  `status` varchar(32) NOT NULL,
  `submitter_id` varchar(128) NOT NULL,
  `submitter_name` varchar(128) NOT NULL,
  `reviewer_id` varchar(128) DEFAULT NULL,
  `reviewer_name` varchar(128) DEFAULT NULL,
  `decision_note` text NOT NULL,
  `version` int NOT NULL DEFAULT '1',
  `submitted_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `reviewed_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_kg_manual_correction_submitter` (`submitter_id`,`created_at`),
  KEY `idx_kg_manual_correction_status` (`status`,`updated_at`),
  KEY `idx_kg_manual_correction_target` (`target_type`,`target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_platform_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_platform_user` (
  `user_id` varchar(128) NOT NULL,
  `username` varchar(128) NOT NULL DEFAULT '',
  `nickname` varchar(128) NOT NULL DEFAULT '',
  `email` varchar(255) NOT NULL DEFAULT '',
  `last_seen_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_platform_user_role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_platform_user_role` (
  `id` varchar(36) NOT NULL,
  `user_id` varchar(128) NOT NULL,
  `role_code` varchar(32) NOT NULL,
  `granted_by` varchar(128) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_platform_user_role` (`user_id`,`role_code`),
  KEY `idx_kg_platform_user_role_code` (`role_code`),
  CONSTRAINT `fk_kg_platform_user_role_user` FOREIGN KEY (`user_id`) REFERENCES `kg_platform_user` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_schema_definition`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_schema_definition` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `schema_key` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `kind` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'entity/relation',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `label` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `identity_key` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `attribute_identity_key` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `attribute_source` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `instance_count` bigint NOT NULL,
  `version` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `display_order` int NOT NULL,
  `is_core` tinyint(1) NOT NULL,
  `relation_category` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'fact/inferred，仅关系 Schema 使用',
  `is_system` tinyint(1) NOT NULL,
  `created_by` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `target_schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_expression` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `target_expression` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  `ddl_statement` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ddl_status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'pending',
  `ddl_error` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ddl_executed_at` datetime DEFAULT NULL,
  `llm_config_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `graph_space` varchar(64) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'dev',
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_definition_key` (`schema_key`),
  UNIQUE KEY `uk_kg_schema_definition_name` (`name`),
  KEY `source_schema_id` (`source_schema_id`),
  KEY `target_schema_id` (`target_schema_id`),
  KEY `idx_kg_schema_definition_kind_created` (`kind`,`created_at`),
  CONSTRAINT `kg_schema_definition_ibfk_1` FOREIGN KEY (`source_schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `kg_schema_definition_ibfk_2` FOREIGN KEY (`target_schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识图谱实体与关系 Schema 定义';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_schema_mapping`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_schema_mapping` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `source_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `position` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_mapping_source` (`schema_id`,`source_name`),
  CONSTRAINT `kg_schema_mapping_ibfk_1` FOREIGN KEY (`schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Schema 来源对象映射';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_schema_property`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_schema_property` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `data_type` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `required` tinyint(1) NOT NULL,
  `rule` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `category` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `position` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_property_name` (`schema_id`,`name`),
  CONSTRAINT `kg_schema_property_ibfk_1` FOREIGN KEY (`schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Schema 属性与约束';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_schema_script`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_schema_script` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `bucket` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `object_key` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `original_filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `content_type` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `size_bytes` bigint NOT NULL,
  `etag` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `sha256` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `uploaded_by` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `uploaded_at` datetime NOT NULL DEFAULT (now()),
  `workflow_definition_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `workflow_function_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `safety_summary` text COLLATE utf8mb4_general_ci,
  `safety_issues` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_script_schema` (`schema_id`),
  CONSTRAINT `kg_schema_script_ibfk_1` FOREIGN KEY (`schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Schema Python 处理脚本 S3 对象元数据';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_script_resource_grant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_script_resource_grant` (
  `run_key` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `record_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `graph_space` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `client_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `actor_user_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  PRIMARY KEY (`run_key`,`record_id`),
  KEY `ix_script_resource_grant_expiry` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_script_watermark`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_script_watermark` (
  `definition_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `step_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `watermark` datetime NOT NULL,
  `checkpoint` json DEFAULT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`definition_id`,`step_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_space_indirect_relation_annotation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_space_indirect_relation_annotation` (
  `graph_space` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `source_vid` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `target_vid` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `annotation` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `create_time` datetime NOT NULL DEFAULT (now()),
  `update_time` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`graph_space`,`source_vid`,`target_vid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_user_graph_space`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_user_graph_space` (
  `id` varchar(36) COLLATE utf8mb4_general_ci NOT NULL,
  `user_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `space_name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_user_graph_space` (`user_id`,`space_name`),
  KEY `idx_kg_user_graph_space_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `kg_user_graph_space_hidden`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `kg_user_graph_space_hidden` (
  `id` varchar(36) COLLATE utf8mb4_general_ci NOT NULL,
  `user_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `space_name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_user_graph_space_hidden` (`user_id`,`space_name`),
  KEY `idx_kg_user_graph_space_hidden_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_audit_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_audit_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `event_type` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `actor_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `actor_name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `request_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `old_status` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `new_status` varchar(32) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `detail` text COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_manual_review_audit_log_case_id` (`case_id`)
) ENGINE=InnoDB AUTO_INCREMENT=94074 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_case`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_case` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `dedupe_key` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `event_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_task_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `batch_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `node_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `pipeline_step_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `object_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `object_type` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `object_name` varchar(500) COLLATE utf8mb4_general_ci NOT NULL,
  `error_type` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `error_fingerprint` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `category` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `template_id` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `template_version` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `domain` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `phase` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `risk_level` varchar(8) COLLATE utf8mb4_general_ci NOT NULL,
  `scope` varchar(16) COLLATE utf8mb4_general_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `assignee_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `assignee_name` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `submitted_by` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `version` int NOT NULL,
  `sla_claim_at` datetime NOT NULL,
  `sla_resolve_at` datetime NOT NULL,
  `claimed_at` datetime DEFAULT NULL,
  `heartbeat_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `source_table` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `source_record_id` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `rule_version` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `model_version` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `workflow_type` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `workflow_id` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `workflow_run_id` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `task_queue` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `resume_token` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `exception_code` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `isolation_scope` varchar(16) COLLATE utf8mb4_general_ci NOT NULL,
  `template_payload_version` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `input_snapshot` text COLLATE utf8mb4_general_ci NOT NULL,
  `candidate_snapshot` text COLLATE utf8mb4_general_ci NOT NULL,
  `diagnosis` text COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `graph_space` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_manual_review_case_dedupe` (`dedupe_key`),
  UNIQUE KEY `event_id` (`event_id`),
  KEY `ix_review_queue` (`status`,`risk_level`,`domain`,`created_at`),
  KEY `ix_review_assignee` (`assignee_id`,`status`),
  KEY `ix_review_graph_space` (`graph_space`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_correction`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_correction` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `adapter` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `payload` text COLLATE utf8mb4_general_ci NOT NULL,
  `correction_version` int NOT NULL,
  `payload_sha256` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `rerun_step_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `attempts` int NOT NULL,
  `last_error` text COLLATE utf8mb4_general_ci,
  `created_at` datetime NOT NULL,
  `applied_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_manual_review_correction_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_decision`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_decision` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `action_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `result` text COLLATE utf8mb4_general_ci NOT NULL,
  `note` text COLLATE utf8mb4_general_ci NOT NULL,
  `submitted_by` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `approved_by` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `decided_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_manual_review_decision_case_id` (`case_id`)
) ENGINE=InnoDB AUTO_INCREMENT=83 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_draft`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_draft` (
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `payload` text COLLATE utf8mb4_general_ci NOT NULL,
  `updated_by` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_evidence`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_evidence` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `file_name` varchar(500) COLLATE utf8mb4_general_ci NOT NULL,
  `content_type` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `size_bytes` bigint NOT NULL,
  `sha256` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `bucket` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `object_key` varchar(1000) COLLATE utf8mb4_general_ci NOT NULL,
  `source` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `trust_level` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `uploaded_by` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_manual_review_evidence_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_execution`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_execution` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `resume_node` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `workflow_type` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `workflow_id` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `run_id` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `error` text COLLATE utf8mb4_general_ci,
  `created_at` datetime NOT NULL,
  `completed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_manual_review_execution_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_execution_event`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_execution_event` (
  `event_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `execution_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `event_type` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `stage` int NOT NULL,
  `payload` text COLLATE utf8mb4_general_ci NOT NULL,
  `occurred_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`event_id`),
  KEY `ix_manual_review_execution_event_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `manual_review_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manual_review_outbox` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `case_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `event_type` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `payload` text COLLATE utf8mb4_general_ci NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `attempts` int NOT NULL,
  `available_at` datetime NOT NULL,
  `locked_at` datetime DEFAULT NULL,
  `last_error` text COLLATE utf8mb4_general_ci,
  `created_at` datetime NOT NULL,
  `processed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_manual_review_outbox_case_id` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_author`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_author` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  `orcid` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者ORCID。/varchar(64) ',
  `author_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者类型/varchar(32) ',
  `surname` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者姓/varchar(255) ',
  `given_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者名/varchar(255) ',
  `initials` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者姓名首字母/varchar(32) ',
  `preferred_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '作者首选姓名/varchar(255) ',
  `city` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者单位所在城市/varchar(255) ',
  `state` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者单位所在州或省/varchar(255) ',
  `postal_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献作者单位邮政编码/varchar(64) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_orcid` (`orcid`),
  KEY `idx_surname` (`surname`),
  KEY `idx_given_name` (`given_name`),
  KEY `idx_preferred_name` (`preferred_name`),
  KEY `idx_city` (`city`),
  KEY `idx_state` (`state`),
  KEY `idx_postal_code` (`postal_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文文献作者详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_journal` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  `paper_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '文献记录的唯一主键标识/varchar(64) ',
  `publisher_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '期刊出版商名称/varchar(255) ',
  `correspond_method` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '通讯方式/varchar(255) ',
  `zh_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '期刊描述，中文描述/text ',
  `quartile` tinyint NOT NULL COMMENT '中国科学院期刊分区/tinyint ',
  `jci` double NOT NULL COMMENT 'JCI期刊引文指标/double ',
  `oa_quote_rate` double NOT NULL COMMENT '期刊OA文献被引用占比/double ',
  `article_rate` double NOT NULL COMMENT '期刊的研究性文章占比/double ',
  `correct_rate` double NOT NULL COMMENT '期刊出版后修正文章占比/double ',
  `revoke_rate` double NOT NULL COMMENT '期刊文献撤稿占比/double ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`),
  KEY `idx_paper_id` (`paper_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文期刊详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper` (
  `pmid` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'PubMed标识符。/varchar(64) ',
  PRIMARY KEY (`pmid`),
  KEY `idx_pmid` (`pmid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper_abstract`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper_abstract` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  `abstract_source` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '摘要来源/varchar(128) ',
  PRIMARY KEY (`logic_id`,`abstract_source`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文摘要信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper_citation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper_citation` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文引用文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper_classification`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper_classification` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文分类信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper_funding`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper_funding` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文基金信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper_reference`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper_reference` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文参考文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_paper_title`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_paper_title` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='英文论文标题信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_en_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_en_report` (
  `affiliation` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `pub_year` int NOT NULL COMMENT '出版年/int ',
  `document_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '资源类型/varchar(100) ',
  `category` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '分类/varchar(300) ',
  `row_pk` bigint unsigned NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`row_pk`),
  KEY `idx_affiliation` (`affiliation`(191)),
  KEY `idx_country` (`country`),
  KEY `idx_document_type` (`document_type`),
  KEY `idx_category` (`category`)
) ENGINE=InnoDB AUTO_INCREMENT=1001 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='外文科技报告信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_zh_journal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_zh_journal` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文期刊详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_zh_paper_abstract`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_zh_paper_abstract` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文摘要信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_zh_paper_author`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_zh_paper_author` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文文献作者详情信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_zh_paper_classification`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_zh_paper_classification` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题信息表逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文分类信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_zh_paper_reference`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_zh_paper_reference` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文参考文献信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `ods_zh_paper_title`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ods_zh_paper_title` (
  `logic_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '逻辑主键/varchar(128) ',
  PRIMARY KEY (`logic_id`),
  KEY `idx_logic_id` (`logic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文标题信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `perf_case14_source`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `perf_case14_source` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(200) COLLATE utf8mb4_general_ci NOT NULL,
  `category` varchar(50) COLLATE utf8mb4_general_ci DEFAULT 'perf',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `platform_embedding_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `platform_embedding_config` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_general_ci NOT NULL,
  `base_url` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `api_key` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `model` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `dimensions` int DEFAULT NULL,
  `owner` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `is_default` tinyint(1) NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_embedding_config_default_status` (`is_default`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `platform_llm_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `platform_llm_config` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_general_ci NOT NULL,
  `base_url` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `api_key` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `model` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `owner` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `is_default` tinyint(1) NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_llm_config_default_status` (`is_default`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `platform_milvus_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `platform_milvus_config` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_general_ci NOT NULL,
  `uri` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `token` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `default_db` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `owner` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `is_default` tinyint(1) NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_milvus_config_default_status` (`is_default`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `platform_mysql_datasource`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `platform_mysql_datasource` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_general_ci NOT NULL,
  `host` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `port` int NOT NULL,
  `default_database` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `username` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `password` varchar(256) COLLATE utf8mb4_general_ci NOT NULL,
  `owner` varchar(128) COLLATE utf8mb4_general_ci NOT NULL,
  `is_default` tinyint(1) NOT NULL,
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_mysql_datasource_default_status` (`is_default`,`status`)
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

