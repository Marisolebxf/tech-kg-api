CREATE TABLE `dwd_scholar_research_direction` (
  `id` bigint NOT NULL COMMENT '逻辑ID',
  `scholar_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '' COMMENT '学者ID',
  `fields` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '研究方向',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录最后更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_scholar_id` (`scholar_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='深势-学者研究方向表';
