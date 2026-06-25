CREATE TABLE `dwd_scholar_paper_relation` (
  `id` bigint NOT NULL COMMENT '主键',
  `paper_id` bigint NOT NULL DEFAULT '0' COMMENT '论文id',
  `related_paper_id` bigint DEFAULT NULL COMMENT '关联论文库的唯一标识',
  `year` bigint NOT NULL DEFAULT '0' COMMENT '论文发表年份',
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '' COMMENT '学者id',
  `citations` int NOT NULL DEFAULT '0' COMMENT '被引用次数',
  `publish_time` datetime DEFAULT NULL COMMENT '发布时间',
  `status` int NOT NULL DEFAULT '1' COMMENT '状态：0:无效,1:有效',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录最后更新时间',
  `publication_id` bigint NOT NULL DEFAULT '0' COMMENT '期刊id',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='深势-学者论文关系表';
