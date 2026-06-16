CREATE TABLE IF NOT EXISTS dwd_en_paper_related (
    `logical_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键',
    `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识。',
    `related_papers` JSON COMMENT '与当前文献内容或主题相关的文献信息。',
    `related_doi` VARCHAR(512) NOT NULL COMMENT '论文的唯一标识编码。',
    `related_name_en` VARCHAR(1024) COMMENT '相关文献的英文标题名称。',
    `data_source` VARCHAR(255) NOT NULL COMMENT '来源贴源库表名',
    `created_time` DATETIME NOT NULL COMMENT '数据在要素库中的创建时间。',
    `updated_time` DATETIME NOT NULL COMMENT '该条数据最近一次更新的时间。',
    KEY `idx_10_logical_id` (`logical_id`),
    KEY `idx_10_paper_id` (`paper_id`),
    KEY `idx_10_related_doi` (`related_doi`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='英文论文关联文献信息';
