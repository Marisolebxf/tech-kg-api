CREATE TABLE IF NOT EXISTS dwd_zh_paper_title (
    `logical_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键',
    `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识。',
    `title_sequence` INT NOT NULL COMMENT '同一文献多个标题的顺序号。',
    `name_en` VARCHAR(1024) COMMENT '文献的英文标题名称。',
    `name_zh` VARCHAR(1024) COMMENT '文献的中文标题名称。',
    `language_code` VARCHAR(12) COMMENT '标题的语言代码。',
    `language` VARCHAR(255) COMMENT '标题的语言类型。',
    `is_original_title` VARCHAR(1) COMMENT '是否为原始标题。',
    `data_source` VARCHAR(255) NOT NULL COMMENT '来源贴源库表名',
    `created_time` DATETIME NOT NULL COMMENT '数据在要素库中的创建时间。',
    `updated_time` DATETIME NOT NULL COMMENT '该条数据最近一次更新的时间。',
    KEY `idx_02_logical_id` (`logical_id`),
    KEY `idx_02_paper_id` (`paper_id`),
    KEY `idx_02_title_sequence` (`title_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中文论文标题信息';
