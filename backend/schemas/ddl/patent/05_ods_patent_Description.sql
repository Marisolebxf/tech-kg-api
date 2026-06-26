CREATE TABLE `ods_patent_Description` (
  `patent_id` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利主键ID',
  `pn` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '专利公开(公告)号',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '说明书信息',
  PRIMARY KEY (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='全球专利-说明书';
