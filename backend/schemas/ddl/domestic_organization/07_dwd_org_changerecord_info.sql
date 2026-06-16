CREATE TABLE IF NOT EXISTS dwd_org_changerecord_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `name_cn` VARCHAR(255) NOT NULL COMMENT '机构名称',
    `external_id` VARCHAR(255) COMMENT '统一社会信用代码',
    `update_content` VARCHAR(255) NOT NULL COMMENT '变更类型',
    `current_name` TEXT COMMENT '变更前内容',
    `update_name` TEXT COMMENT '变更后内容',
    `update_date` DATE NOT NULL COMMENT '变更日期',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_dwd_org_changerecord_info_org_id` (`org_id`),
    KEY `idx_dwd_org_changerecord_info_external_id` (`external_id`),
    KEY `idx_dwd_org_changerecord_info_update_date` (`update_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工商变更信息';
