CREATE TABLE IF NOT EXISTS dwd_forg_executive_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `executives_name` VARCHAR(255) COMMENT '高管姓名',
    `executives_position` VARCHAR(255) COMMENT '职位名称',
    `dm_birthdate` DATE COMMENT '高管出生日期(新增字段)',
    `dm_nationalities` VARCHAR(255) COMMENT '高管国籍(新增字段)',
    `dm_biography` VARCHAR(255) COMMENT '高管履历(新增字段)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外机构高管信息';
