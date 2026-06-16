CREATE TABLE IF NOT EXISTS dwd_scholar_research_direction (
    scholar_id VARCHAR(32) COMMENT '关联学者记录的业务唯一标识',
    fields TEXT COMMENT '学者研究方向',
    create_time DATETIME COMMENT '记录创建时间',
    update_time DATETIME COMMENT '记录最后更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学者研究方向';

