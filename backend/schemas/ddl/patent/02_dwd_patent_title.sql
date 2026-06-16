CREATE TABLE IF NOT EXISTS dwd_patent_title (
    patent_id VARCHAR(64) NOT NULL COMMENT '关联 dwd_patent.patent_id 的专利唯一标识',
    title_localized JSON COMMENT '原文标题和英文标题',
    db_source VARCHAR(64) NOT NULL COMMENT '数据来源贴源库',
    create_time DATETIME NOT NULL COMMENT '记录创建时间',
    update_time DATETIME NOT NULL COMMENT '记录最近更新时间',
    PRIMARY KEY (patent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='专利标题信息表';
