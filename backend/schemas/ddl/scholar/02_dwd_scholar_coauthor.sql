CREATE TABLE `dwd_scholar_coauthor` (
  `id` bigint NOT NULL COMMENT '自增主键ID',
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '学者ID，当前学者记录的业务唯一标识',
  `co_scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '合作学者ID，合作学者记录的业务唯一标识',
  `co_scholar_name_en` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '合作学者英文名',
  `co_scholar_name_zh` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '合作学者中文名',
  `co_scholar_avatar` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '合作学者头像URL',
  `co_scholar_org_name_en` text CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '合作学者所属机构英文名',
  `co_scholar_org_name_zh` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '合作学者所属机构中文名',
  `co_scholar_org_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '合作学者所属机构ID',
  `co_paper_count` int NOT NULL DEFAULT '0' COMMENT '合作论文数量',
  `status` int NOT NULL DEFAULT '1' COMMENT '状态：0:无效,1:有效',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录最后更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='深势-学者合作者关系表';
