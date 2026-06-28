CREATE TABLE `dwd_zh_author` (
  `id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '文献作者的唯一主键 id',
  `paper_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '文献记录的唯一主键标识。',
  `en_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '文献作者的英文名称',
  `zh_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT '文献作者中文名',
  `affiliation` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '文献作者地址',
  `email` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin COMMENT '文献作者email',
  `correspond` tinyint DEFAULT NULL COMMENT '是否为通讯作者',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='深势-中文文献作者详情信息';
