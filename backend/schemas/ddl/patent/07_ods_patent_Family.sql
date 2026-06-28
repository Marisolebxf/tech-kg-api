CREATE TABLE `ods_patent_Family` (
  `patent_id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利主键ID',
  `pn` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利公开(公告)号',
  `patent_family` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '专利家族信息',
  PRIMARY KEY (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='全球专利-专利家族';
