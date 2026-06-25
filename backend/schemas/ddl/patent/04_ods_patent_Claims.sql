CREATE TABLE `ods_patent_Claims` (
  `patent_id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利主键ID',
  `pn` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利公开(公告)号',
  `claims` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '权利要求信息',
  `claim_count` int DEFAULT NULL COMMENT '权利要求统计',
  PRIMARY KEY (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='全球专利-权利要求';
