CREATE TABLE IF NOT EXISTS dwd_forg_act_contro_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `country_code` VARCHAR(255) COMMENT '企业国家代码',
    `entity_eid` VARCHAR(255) COMMENT '实控人ID',
    `entity_name` VARCHAR(255) COMMENT '实控人名称',
    `entity_type` VARCHAR(255) COMMENT '实控人类型',
    `entity_country_code` VARCHAR(255) COMMENT '实控人国家代码',
    `direct_pct` VARCHAR(255) COMMENT '直接持股比例',
    `total_pct` VARCHAR(255) COMMENT '总持股比例',
    `direct_pct_num` DECIMAL(20,2) COMMENT '直接持股比例数值',
    `total_pct_num` DECIMAL(20,2) COMMENT '总持股比例数值',
    `path` TEXT COMMENT '路径'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外机构实控人信息（新增表）';
