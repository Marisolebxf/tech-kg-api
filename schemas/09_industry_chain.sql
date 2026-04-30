CREATE TABLE industry_chain (
    -- 1. 产业链分类信息
    chain_name VARCHAR(255) COMMENT '产业技术链名称',
    node_id VARCHAR(64) COMMENT '节点ID',
    node_name VARCHAR(255) COMMENT '节点名称',
    level INT COMMENT '节点层级',

    -- 2. 产业链关系信息
    parent_id VARCHAR(64) COMMENT '父级节点ID',
    parent_name VARCHAR(255) COMMENT '父级节点名称',
    company_count INT COMMENT '节点企业数量',

    -- 3. 产业链关联企业信息
    antitypic VARCHAR(64) COMMENT '节点企业ID',
    company_name VARCHAR(255) COMMENT '节点企业名称',
    credit_code VARCHAR(64) COMMENT '节点企业统一社会信用代码',
    tech_product TEXT COMMENT '企业的TOP5产品技术词',

    -- 4. 产业链关联产品信息
    sales_volume DECIMAL(18,2) COMMENT '销量',
    sales DECIMAL(18,2) COMMENT '销售额',
    output DECIMAL(18,2) COMMENT '产量',
    price DECIMAL(18,2) COMMENT '价格',

    -- 5. 产业链关联专利信息
    patent_count INT COMMENT '节点专利数量',
    patent_id VARCHAR(64) COMMENT '专利ID',
    pn VARCHAR(128) COMMENT '专利公开(公告)号',
    pbdt DATE COMMENT '公开(公告)日',
    apno VARCHAR(128) COMMENT '申请号',
    apdt DATE COMMENT '申请日',
    title VARCHAR(500) COMMENT '标题',
    original_assignee VARCHAR(255) COMMENT '原始申请人',
    current_assignee VARCHAR(255) COMMENT '当前申请(专利权)人',
    inventors TEXT COMMENT '发明人',

    -- 6. 产业动态资讯
    title VARCHAR(500) COMMENT '标题',
    summary TEXT COMMENT '摘要',
    release_date DATE COMMENT '发布时间',
    author VARCHAR(255) COMMENT '作者',
    source VARCHAR(255) COMMENT '来源',

    -- 7. 产业统计年鉴
    yearbook TEXT COMMENT '产业统计年鉴（自定义）',

    -- 8. 产业链关联论文信息
    paper_count INT COMMENT '节点关联论文数量',
    paper_id VARCHAR(64) COMMENT '论文ID',
    paper_name VARCHAR(500) COMMENT '论文名称',
    paper_keyword TEXT COMMENT '论文关键词',
    paper_category VARCHAR(255) COMMENT '论文类别',
    research_direction VARCHAR(255) COMMENT '论文研究方向',

    -- 9. 产业链关联人才信息
    expert_count INT COMMENT '节点关联专家数量',
    expert_id VARCHAR(64) COMMENT '专家ID',
    expert_name VARCHAR(255) COMMENT '专家姓名',
    basic_info TEXT COMMENT '基本信息',
    org_name VARCHAR(255) COMMENT '所属机构名称',
    title_position VARCHAR(255) COMMENT '职称/职级',
    research_area VARCHAR(255) COMMENT '研究方向',

    -- 10. 产业链关联项目信息
    project_id VARCHAR(64) COMMENT '节点关联项目ID(z自定义)'
);