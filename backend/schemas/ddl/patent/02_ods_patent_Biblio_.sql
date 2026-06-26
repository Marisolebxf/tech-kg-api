CREATE TABLE `ods_patent_Biblio_` (
  `patent_id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利主键ID',
  `pn` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利公开(公告)号',
  `exdt` int DEFAULT NULL COMMENT '智慧芽专利预估到期日',
  `parties` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '当事人信息(申请人、发明人等)',
  `abstracts` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '摘要信息',
  `patent_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '专利类型',
  `invention_title` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '标题信息',
  `priority_claims` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '优先权信息',
  `reference_cited` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '应用专利信息',
  `related_documents` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '分案申请、继续申请信息',
  `classification_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '分类数据',
  `application_reference` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '申请信息',
  `publication_reference` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '公开信息',
  `pct_or_regional_filing_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT 'PCT申请信息',
  `dates_of_public_availability` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '授权信息',
  `pct_or_regional_publishing_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT 'PCT公开信息',
  PRIMARY KEY (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='全球专利-著录项目';
