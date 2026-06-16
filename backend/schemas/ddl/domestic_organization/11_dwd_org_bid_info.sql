CREATE TABLE IF NOT EXISTS dwd_org_bid_info (
    `tender_org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `tender_name_cn` VARCHAR(255) NOT NULL COMMENT '采购单位名称',
    `tender_external_id` VARCHAR(255) COMMENT '采购单位统一社会信用代码',
    `winner_org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `winner_name_cn` VARCHAR(255) NOT NULL COMMENT '中标单位名称',
    `winner_external_id` VARCHAR(255) COMMENT '中标单位统一社会信用代码',
    `announcement_title` TEXT COMMENT '公告标题',
    `announcement_content` TEXT COMMENT '中标成交信息',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_dwd_org_bid_info_tender_org_id` (`tender_org_id`),
    KEY `idx_dwd_org_bid_info_tender_external_id` (`tender_external_id`),
    KEY `idx_dwd_org_bid_info_winner_org_id` (`winner_org_id`),
    KEY `idx_dwd_org_bid_info_winner_external_id` (`winner_external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招投标事件';
