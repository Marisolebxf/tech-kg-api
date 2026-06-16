CREATE TABLE IF NOT EXISTS dwd_scholar (
    scholar_id VARCHAR(32) COMMENT '学者记录的业务唯一标识',
    name_en VARCHAR(128) COMMENT '学者的英文姓名',
    name_zh VARCHAR(128) COMMENT '学者的中文姓名',
    avatar VARCHAR(256) COMMENT '学者头像图片的访问链接',
    scholar_org_name_en VARCHAR(4096) COMMENT '学者所属机构的英文名称',
    scholar_org_name_zh VARCHAR(1024) COMMENT '学者所属机构的中文名称',
    bio TEXT COMMENT '学者的个人或学术简介信息',
    bio_zh TEXT COMMENT '学者的中文个人或学术简介信息',
    work_experience_en TEXT COMMENT '学者英文工作经历信息',
    work_experience_zh TEXT COMMENT '学者中文工作经历信息',
    education_background_en TEXT COMMENT '学者的英文教育经历信息',
    education_background_zh TEXT COMMENT '学者的中文教育经历信息',
    paper_nums BIGINT COMMENT '学者已发表论文的数量',
    citation_nums BIGINT COMMENT '学者论文被引用的总次数',
    h_index BIGINT COMMENT '衡量学者学术影响力的 H 指数',
    status TINYINT COMMENT '记录状态，0 表示无效，1 表示有效',
    create_time DATETIME COMMENT '记录创建时间',
    update_time DATETIME COMMENT '记录最后更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学者';

