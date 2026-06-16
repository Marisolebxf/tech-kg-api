CREATE TABLE IF NOT EXISTS dwd_forg_subsidiary_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `affiliate` VARCHAR(255) COMMENT '子公司id',
    `affiliates_name` VARCHAR(255) COMMENT '子公司名称',
    `affiliates_country_code` VARCHAR(255) COMMENT '子公司国家代码',
    `affiliates_country` VARCHAR(255) COMMENT '子公司国家',
    `affiliates_company_id` VARCHAR(255) COMMENT '子公司唯一注册码'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外机构子公司股权关联信息';
