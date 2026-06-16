CREATE TABLE IF NOT EXISTS dwd_en_paper_classification (
    `logical_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键',
    `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识。',
    `subject_category` VARCHAR(20) COMMENT '期刊或会议所属的大类学科领域。',
    `subject_subcategory` VARCHAR(20) COMMENT '期刊或会议所属的细分学科主题。',
    `keywords` LONGTEXT COMMENT '描述论文主题内容的关键词。',
    `data_source` VARCHAR(255) NOT NULL COMMENT '来源贴源库表名',
    `created_time` DATETIME NOT NULL COMMENT '数据在要素库中的创建时间。',
    `updated_time` DATETIME NOT NULL COMMENT '该条数据最近一次更新的时间。',
    KEY `idx_09_logical_id` (`logical_id`),
    KEY `idx_09_paper_id` (`paper_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='英文论文分类信息';
