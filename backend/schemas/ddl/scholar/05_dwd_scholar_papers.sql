CREATE TABLE IF NOT EXISTS dwd_scholar_papers (
    zh_name VARCHAR(500) COMMENT '论文的中文标题名称',
    en_name VARCHAR(500) COMMENT '论文的英文标题名称',
    authors TEXT COMMENT '论文作者的姓名或信息列表',
    paper_url VARCHAR(1024) COMMENT '论文原始来源页面的访问链接',
    cover_date_start DATE COMMENT '论文正式发表或出版的时间',
    create_time DATETIME COMMENT '记录创建时间',
    update_time DATETIME COMMENT '记录最后更新时间',
    status TINYINT COMMENT '记录状态，0 表示无效，1 表示有效',
    zh_abstract TEXT COMMENT '论文内容的中文摘要信息',
    en_abstract TEXT COMMENT '论文内容的英文摘要信息',
    doi VARCHAR(512) COMMENT '论文的 DOI 唯一识别号',
    publication_en_name VARCHAR(1024) COMMENT '论文发表所在期刊或会议的英文名称'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='论文信息';

