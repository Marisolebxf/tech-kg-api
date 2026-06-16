CREATE TABLE IF NOT EXISTS dwd_zh_paper_citation (
    `logical_id` VARCHAR(128) NOT NULL COMMENT '标题信息表逻辑主键',
    `paper_id` VARCHAR(64) NOT NULL COMMENT '文献记录的唯一主键标识。',
    `publication_id` BIGINT NOT NULL COMMENT '关联出版物的id，用于获取期刊详情信息',
    `citation_doi` VARCHAR(512) NOT NULL COMMENT '论文的唯一标识编码。',
    `citation_name_zh` VARCHAR(1024) COMMENT '引用文献的中文标题名称。',
    `citation_publication_name_zh` VARCHAR(1024) COMMENT '参考文献出版物的中文名称。',
    `data_source` VARCHAR(255) NOT NULL COMMENT '来源贴源库表名',
    `created_time` DATETIME NOT NULL COMMENT '数据在要素库中的创建时间。',
    `updated_time` DATETIME NOT NULL COMMENT '该条数据最近一次更新的时间。',
    KEY `idx_07_logical_id` (`logical_id`),
    KEY `idx_07_paper_id` (`paper_id`),
    KEY `idx_07_publication_id` (`publication_id`),
    KEY `idx_07_citation_doi` (`citation_doi`),
    KEY `idx_07_citation_publication_name_zh` (`citation_publication_name_zh`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='中文论文引用文献信息';
