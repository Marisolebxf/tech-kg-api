CREATE TABLE IF NOT EXISTS dwd_org_invest_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称',
    `external_id` VARCHAR(255) COMMENT '统一社会信用代码',
    `inv_org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `inv_name` VARCHAR(255) NOT NULL COMMENT '被投资企业名称',
    `inv_external_id` VARCHAR(255) COMMENT '被投资企业统一社会信用代码',
    `investment_amount` DECIMAL(20,2) COMMENT '投资金额(元)',
    `investment_ratio` DECIMAL(20,2) COMMENT '股权占比(%)',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_dwd_org_invest_info_org_id` (`org_id`),
    KEY `idx_dwd_org_invest_info_external_id` (`external_id`),
    KEY `idx_dwd_org_invest_info_inv_org_id` (`inv_org_id`),
    KEY `idx_dwd_org_invest_info_inv_external_id` (`inv_external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='投资事件';
