CREATE TABLE `dwd_org_tb_judicial_sale` (
  `notice_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '公告名',
  `asset_disposal_unit` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '资产处置单位',
  `notice_time` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '公告时间',
  `notice_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '公告id',
  `source_website` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源网站',
  `notice_content_path` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '公告内容存储路径',
  `auction_start_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '拍卖开始日期',
  `auction_end_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '拍卖截止日期',
  `original_link` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci COMMENT '原始链接',
  `use_flag` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '使用标志',
  `data_source` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '数据来源',
  `created_time` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_time` datetime DEFAULT NULL COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='司法拍卖表';
