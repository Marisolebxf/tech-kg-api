CREATE TABLE IF NOT EXISTS dwd_org_shareholder_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称',
    `external_id` VARCHAR(255) COMMENT '统一社会信用代码',
    `inv_org_id` VARCHAR(255) COMMENT '机构身份唯一id，用于关联其它表。',
    `owners_name` VARCHAR(255) NOT NULL COMMENT '股东名称',
    `owners_type` VARCHAR(255) COMMENT '股东类型',
    `ownership_percentage` DECIMAL(20,2) COMMENT '所有权占比(%)',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_dwd_org_shareholder_info_org_id` (`org_id`),
    KEY `idx_dwd_org_shareholder_info_external_id` (`external_id`),
    KEY `idx_dwd_org_shareholder_info_inv_org_id` (`inv_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股东信息';
