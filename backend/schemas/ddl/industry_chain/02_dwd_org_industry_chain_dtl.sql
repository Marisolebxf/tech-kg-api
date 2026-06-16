CREATE TABLE IF NOT EXISTS dwd_org_industry_chain_dtl (
    `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链唯一id，用于关联其它表。',
    `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称',
    `node_id` VARCHAR(255) NOT NULL COMMENT '产业链节点唯一id，用于关联其它表。',
    `node_name` VARCHAR(255) NOT NULL COMMENT '节点名称',
    `antitypic` VARCHAR(255) NOT NULL COMMENT '企业身份唯一id，用于关联其它表。',
    `credit_code` VARCHAR(255) COMMENT '统一社会信用代码',
    `chain_score` DECIMAL(20,2) COMMENT '产业链评分',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_chain_code` (`chain_code`),
    KEY `idx_node_id` (`node_id`),
    KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产业关联企业信息';
