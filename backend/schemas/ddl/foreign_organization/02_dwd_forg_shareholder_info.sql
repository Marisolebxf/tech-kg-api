CREATE TABLE IF NOT EXISTS dwd_forg_shareholder_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `owners_name` VARCHAR(255) COMMENT '股东名称',
    `ownership_percentage` DECIMAL(20,2) COMMENT '股权占比(%)',
    `owners_country_code` VARCHAR(255) COMMENT '股东所在国家代码',
    `owners_country` VARCHAR(255) COMMENT '股东所在国家'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外机构股东股权关联信息';
