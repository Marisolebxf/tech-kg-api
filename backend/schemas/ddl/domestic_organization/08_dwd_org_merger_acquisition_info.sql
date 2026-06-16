CREATE TABLE IF NOT EXISTS dwd_org_merger_acquisition_info (
    `acquiring_org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `acquiring_name` VARCHAR(255) NOT NULL COMMENT '发起收购企业名称',
    `acquired_org_id` VARCHAR(255) NOT NULL COMMENT '机构身份唯一id，用于关联其它表。',
    `acquired_name` VARCHAR(255) NOT NULL COMMENT '被收购企业名称',
    `ma_amount` DECIMAL(20,2) COMMENT '并购金额(元)',
    `currency_code` VARCHAR(255) COMMENT '并购金额币种',
    KEY `idx_dwd_org_merger_acquisition_info_acquiring_org_id` (`acquiring_org_id`),
    KEY `idx_dwd_org_merger_acquisition_info_acquired_org_id` (`acquired_org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='并购事件';
