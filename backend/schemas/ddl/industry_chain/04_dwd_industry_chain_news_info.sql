CREATE TABLE IF NOT EXISTS dwd_industry_chain_news_info (
    `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链唯一id，用于关联其它表。',
    `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称',
    `news_id` VARCHAR(255) NOT NULL COMMENT '资讯唯一id',
    `title` VARCHAR(255) COMMENT '标题',
    `relaese_date` DATE COMMENT '发布时间',
    `summary` TEXT COMMENT '摘要',
    `source` VARCHAR(255) COMMENT '来源',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_chain_code` (`chain_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产业动态资讯';
