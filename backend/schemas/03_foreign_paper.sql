CREATE TABLE paper_en (
    -- 1. 文献基础信息
    paper_id VARCHAR(64) PRIMARY KEY COMMENT '文献id',
    publisher VARCHAR(255) COMMENT '出版商',
    publisher_id VARCHAR(64) COMMENT '出版商id',
    publication_id VARCHAR(64) COMMENT '关联出版物信息；期刊id/会议id/预印本id',
    publication_en_name VARCHAR(255) COMMENT '出版物英文名称',
    publication_type VARCHAR(255) COMMENT '出版物类型',
    paper_type VARCHAR(255) COMMENT '文献类型',
    paper_url TEXT COMMENT '文献官网链接',
    doi VARCHAR(255) COMMENT '论文唯一识别号',
    cover_date_start DATE COMMENT '文献发表时间',
    funds TEXT COMMENT '基金',

    -- 2. 文献内容与摘要
    en_name VARCHAR(500) COMMENT '文献英文名',
    en_abstract TEXT COMMENT '摘要',
    graphical_abstract TEXT COMMENT '摘要图',
    keywords TEXT COMMENT '论文关键词',

    -- 3. 文献刊载与页码
    volume VARCHAR(64) COMMENT '文献所在期刊的卷号',
    issue VARCHAR(64) COMMENT '文献所在期刊的期号',
    first_page VARCHAR(32) COMMENT '论文在期刊的首页页码',
    last_page VARCHAR(32) COMMENT '论文在期刊的末尾页码',

    -- 4. 文献刊载与引文
    reference_nums INT COMMENT '引用文献数量',
    reference_content TEXT COMMENT '引用文献内容',
    reference_id_list JSON COMMENT '引用文献ID列表；英文名为自定义，图中仅提供中文字段描述',
    citation_nums INT COMMENT '被引用文献数量',
    citation_content TEXT COMMENT '被引用文献内容',
    citation_id_list JSON COMMENT '被引用文献ID列表；英文名为自定义，图中仅提供中文字段描述',
    relevant TEXT COMMENT '相关文献',

    -- 5. 作者与机构
    authors JSON COMMENT '作者信息列表',
    `authors[].id` VARCHAR(64) COMMENT '作者ID',
    `authors[].organizationInfos` JSON COMMENT '所属机构列表',
    `authors[].organizationInfos[].id` VARCHAR(64) COMMENT '机构ID',
    `authors[].organizationInfos[].englishAddress` TEXT COMMENT '英文地址',
    `authors[].organizationInfos[].englishOrganizationName` VARCHAR(255) COMMENT '机构英文名称',
    `authors[].personinfo` JSON COMMENT '作者个人信息',
    `authors[].personinfo.englishFullName` VARCHAR(255) COMMENT '英文全名',
    `authors[].personinfo.englishProfessionalTitle` VARCHAR(255) COMMENT '英文专业职称',
    `authors[].role` VARCHAR(255) COMMENT '作者角色（如通讯作者等）',

    -- 6. 期刊基础信息
    journal_id VARCHAR(64) COMMENT '期刊id/会议id/预印本id',
    issn VARCHAR(64) COMMENT 'ISSN',
    eissn VARCHAR(64) COMMENT 'EISSN',
    journal_name_zh VARCHAR(255) COMMENT '期刊/顶会名/预印本（中文）',
    journal_name_en VARCHAR(255) COMMENT '期刊/顶会名/预印本（英文）',
    journal_type VARCHAR(255) COMMENT '期刊/顶会类别/预印本',
    journal_abbreviation VARCHAR(255) COMMENT '简称',
    journal_alias VARCHAR(255) COMMENT '期刊/顶会/预印本别名',
    country VARCHAR(128) COMMENT '国家',
    en_name VARCHAR(255) COMMENT '期刊英文名',
    name_abbr VARCHAR(255) COMMENT '英文名简写',
    en_description TEXT COMMENT '期刊描述',
    founding_time DATE COMMENT '创刊时间',
    language_classify VARCHAR(64) COMMENT '语种',
    
    -- 7. 出版信息
    postal_code VARCHAR(32) COMMENT '邮发代号',
    chief_editor VARCHAR(255) COMMENT '主编',
    organizer VARCHAR(255) COMMENT '主办单位',
    publisher_place VARCHAR(255) COMMENT '出版地',
    publication_cycle VARCHAR(128) COMMENT '出版周期',
    mobile VARCHAR(64) COMMENT '期刊出版商电话',
    address TEXT COMMENT '期刊出版商地址',
    in_official TEXT COMMENT '期刊官网',
    layout_cost DECIMAL(12,2) COMMENT '版面费',

    -- 8. 期刊评价与指标
    cite_nums INT COMMENT '被引用量',
    fund_nums INT COMMENT '基金论文量',
    paper_nums INT COMMENT '出版论文量',
    review VARCHAR(64) COMMENT '是否综述',
    annual_publication INT COMMENT '年文章数',
    impact_factor DECIMAL(10,4) COMMENT '影响因子',
    jcr_zone VARCHAR(64) COMMENT 'JCR分区',
    journal_db_str TEXT COMMENT '收录数据库',
    number_of_cites INT COMMENT '国人占比',
    open_access VARCHAR(32) COMMENT '是否OA',
    review_period VARCHAR(128) COMMENT '平均审稿周期',
    scope TEXT COMMENT '中科院分区：大类学科',
    scope_zone TEXT COMMENT '中科院分区：分区',
    self_rate DECIMAL(10,4) COMMENT '自引率',
    top_flag VARCHAR(32) COMMENT '是否顶刊',
    warning_flag BOOLEAN COMMENT '是否预警',

    -- 9. 其它字段需求
    `partition.source` VARCHAR(64) COMMENT '期刊分类来源',
    `partition.subject_level` VARCHAR(64) COMMENT '期刊学科分类级别',
    `partition.partition` VARCHAR(64) COMMENT '期刊学科分类分区',
    content TEXT COMMENT '论文正文',
    location VARCHAR(255) COMMENT '发表机构地点经纬度',
    pdf TEXT COMMENT '论文PDF文件'
);