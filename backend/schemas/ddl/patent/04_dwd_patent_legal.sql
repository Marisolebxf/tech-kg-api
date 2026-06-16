CREATE TABLE IF NOT EXISTS dwd_patent_legal (
    patent_id VARCHAR(64) NOT NULL COMMENT '关联 dwd_patent.patent_id 的专利唯一标识',
    legal_events TEXT COMMENT '专利生命周期中的法律状态变更事件',
    `patent_legal/prs_data` JSON COMMENT 'PRS 事件日期、代码和法律状态分类说明',
    db_source VARCHAR(64) NOT NULL COMMENT '数据来源贴源库',
    create_time DATETIME NOT NULL COMMENT '记录创建时间',
    update_time DATETIME NOT NULL COMMENT '记录最近更新时间',
    PRIMARY KEY (patent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='法律状态信息表';
