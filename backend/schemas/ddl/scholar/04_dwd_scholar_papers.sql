CREATE TABLE `dwd_scholar_papers` (
  `id` bigint NOT NULL,
  `zh_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '中文题目',
  `en_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '英文题目',
  `authors` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '作者列表',
  `paper_url` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '' COMMENT '论文原始链接',
  `cover_date_start` datetime DEFAULT NULL COMMENT '发表时间',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '记录最后更新时间',
  `status` tinyint DEFAULT '1' COMMENT '状态：0:无效,1:有效',
  `zh_abstract` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '中文摘要',
  `en_abstract` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '英文摘要',
  `doi` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '',
  `publication_en_name` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '期刊/会议英文名',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='深势-论文信息表';
