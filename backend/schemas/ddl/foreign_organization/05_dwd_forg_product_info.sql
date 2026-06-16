CREATE TABLE IF NOT EXISTS dwd_forg_product_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `description` VARCHAR(255) COMMENT '业务描述',
    `main_products` VARCHAR(255) COMMENT '主要产品'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外机构公司经营信息';
