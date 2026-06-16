CREATE TABLE IF NOT EXISTS dwd_org_important_news_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称',
    `external_id` VARCHAR(255) COMMENT '统一社会信用代码',
    `news_title` TEXT COMMENT '资讯标题',
    `news_date` DATE COMMENT '资讯日期',
    `news_content` TEXT COMMENT '资讯内容',
    `original_textlink` TEXT COMMENT '咨询原文链接',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_dwd_org_important_news_info_org_id` (`org_id`),
    KEY `idx_dwd_org_important_news_info_external_id` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='重点资讯';
