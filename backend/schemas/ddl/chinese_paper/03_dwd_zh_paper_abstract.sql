CREATE TABLE IF NOT EXISTS dwd_zh_paper_abstract (
    `logical_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键',
    `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识。',
    `abstract_sequence` INT NOT NULL COMMENT '同一文献多个摘要的顺序号',
    `language` VARCHAR(255) COMMENT '文献或期刊出版使用的语言类型。',
    `is_original_abstract` VARCHAR(1) NOT NULL COMMENT '是否为原始摘要。',
    `abstract_en` LONGTEXT COMMENT '文献内容的英文摘要信息。',
    `abstract_zh` LONGTEXT COMMENT '文献内容的中文摘要信息。',
    `data_source` VARCHAR(255) NOT NULL COMMENT '来源贴源库表名',
    `created_time` DATETIME NOT NULL COMMENT '数据在要素库中的创建时间。',
    `updated_time` DATETIME NOT NULL COMMENT '该条数据最近一次更新的时间。',
    KEY `idx_03_logical_id` (`logical_id`),
    KEY `idx_03_paper_id` (`paper_id`),
    KEY `idx_03_abstract_sequence` (`abstract_sequence`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中文论文摘要信息';

