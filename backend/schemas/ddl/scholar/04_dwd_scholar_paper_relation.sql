CREATE TABLE IF NOT EXISTS dwd_scholar_paper_relation (
    paper_id BIGINT COMMENT '论文记录的唯一标识',
    `year` BIGINT COMMENT '论文发表年份',
    scholar_id VARCHAR(32) COMMENT '学者记录的业务唯一标识',
    citations BIGINT COMMENT '论文被引用次数',
    publish_time DATE COMMENT '论文发布时间',
    status TINYINT COMMENT '记录状态，0 表示无效，1 表示有效',
    create_time DATETIME COMMENT '记录创建时间',
    update_time DATETIME COMMENT '记录最后更新时间',
    publication_id BIGINT COMMENT '期刊或会议记录的唯一标识',
    related_paper_id BIGINT COMMENT '关联论文库的唯一标识'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学者论文关系';

