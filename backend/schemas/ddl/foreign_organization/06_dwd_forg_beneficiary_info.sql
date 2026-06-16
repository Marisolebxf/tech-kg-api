CREATE TABLE IF NOT EXISTS dwd_forg_beneficiary_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `bo_name` VARCHAR(255) COMMENT '受益人名称',
    `bo_gender` VARCHAR(255) COMMENT '受益人性别',
    `bo_birthdate` DATE COMMENT '受益人出生日期',
    `bo_country_code` VARCHAR(255) COMMENT '受益人所在国家代码',
    `path` VARCHAR(255) COMMENT '受益人关系路径',
    `bo_manager` VARCHAR(255) COMMENT '受益人是否同时是管理层',
    `total_percent` DECIMAL(20,2) COMMENT '总持股比例',
    `direct_percent` DECIMAL(20,2) COMMENT '直接持股比例',
    `indirect_percent` DECIMAL(20,2) COMMENT '间接持股比例'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外机构受益人信息（新增表）';
