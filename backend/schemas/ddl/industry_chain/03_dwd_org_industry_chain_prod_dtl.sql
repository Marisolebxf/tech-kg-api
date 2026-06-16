CREATE TABLE IF NOT EXISTS dwd_org_industry_chain_prod_dtl (
    `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链唯一id，用于关联其它表。',
    `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称',
    `antitypic` VARCHAR(255) NOT NULL COMMENT '企业身份唯一id，用于关联其它表。',
    `company_name` VARCHAR(500) COMMENT '企业名称',
    `credit_code` VARCHAR(255) COMMENT '统一社会信用代码',
    `tech_product` VARCHAR(255) NOT NULL COMMENT '主营产品名称',
    `tech_product_seq` BIGINT COMMENT '主营产品排序',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_chain_code` (`chain_code`),
    KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产业链企业关联产品信息';
