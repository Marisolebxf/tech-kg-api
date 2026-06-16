CREATE TABLE IF NOT EXISTS dwd_scholar_coauthor (
    scholar_id VARCHAR(32) COMMENT '当前学者记录的业务唯一标识',
    co_scholar_id VARCHAR(32) COMMENT '合作学者记录的业务唯一标识',
    co_scholar_name_en VARCHAR(256) COMMENT '合作学者的英文姓名',
    co_scholar_name_zh VARCHAR(128) COMMENT '合作学者的中文姓名',
    co_scholar_avatar VARCHAR(512) COMMENT '合作学者头像图片的访问链接',
    co_scholar_org_name_en VARCHAR(2048) COMMENT '合作学者所属机构的英文名称',
    co_scholar_org_name_zh VARCHAR(1024) COMMENT '合作学者所属机构的中文名称',
    co_paper_count BIGINT COMMENT '与该学者合作发表的论文数量',
    status TINYINT COMMENT '记录状态，0 表示无效，1 表示有效',
    create_time DATETIME COMMENT '记录创建时间',
    update_time DATETIME COMMENT '记录最后更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学者合作者关系';

