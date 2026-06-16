CREATE TABLE IF NOT EXISTS dwd_zh_paper_author (
    `logical_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键',
    `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识。',
    `author_sequence` INT NOT NULL COMMENT '作者在文献中的顺序。',
    `author_id` VARCHAR(32) NOT NULL COMMENT '文献作者的唯一主键 id',
    `author_name_en` VARCHAR(255) NOT NULL COMMENT '文献作者的英文名称',
    `author_name_zh` VARCHAR(255) COMMENT '文献作者中文名',
    `author_email` JSON COMMENT '文献作者email',
    `is_corresponding_author` TINYINT COMMENT '是否为通讯作者',
    `organization_name` TEXT COMMENT '作者所属机构或单位的名称。',
    `author_address` JSON COMMENT '文献作者地址',
    `data_source` VARCHAR(255) NOT NULL COMMENT '来源贴源库表名',
    `created_time` DATETIME NOT NULL COMMENT '数据在要素库中的创建时间。',
    `updated_time` DATETIME NOT NULL COMMENT '该条数据最近一次更新的时间。',
    KEY `idx_04_logical_id` (`logical_id`),
    KEY `idx_04_paper_id` (`paper_id`),
    KEY `idx_04_author_sequence` (`author_sequence`),
    KEY `idx_04_author_id` (`author_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中文文献作者详情信息';
