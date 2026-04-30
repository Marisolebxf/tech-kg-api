CREATE TABLE paper_cn (

    -- ========================
    -- 1. 文献基础信息
    -- ========================
    paper_id VARCHAR(64) PRIMARY KEY COMMENT '文献id',
    publisher VARCHAR(255) COMMENT '出版商',
    publisher_id VARCHAR(64) COMMENT '出版商id',
    publication_id VARCHAR(64) COMMENT '关联出版物信息；期刊/顶会id/预印本',
    publication_name VARCHAR(255) COMMENT '出版物中文名称',
    publication_type VARCHAR(255) COMMENT '出版物类型',
    paper_type VARCHAR(255) COMMENT '文献类型',
    paper_url TEXT COMMENT '文献官网链接',
    doi VARCHAR(255) COMMENT '论文唯一识别号',
    cover_date_start DATE COMMENT '文献发表时间',

    -- ========================
    -- 2. 文献内容与摘要
    -- ========================
    zh_name VARCHAR(500) COMMENT '文献中文名',
    zh_abstract TEXT COMMENT '中文摘要',
    keywords TEXT COMMENT '论文关键词',

    -- ========================
    -- 3. 期刊卷期页
    -- ========================
    volume VARCHAR(64) COMMENT '文献所在期刊的卷号',
    issue VARCHAR(64) COMMENT '文献所在期刊的期号',
    first_page VARCHAR(32) COMMENT '论文在期刊的首页页码',
    last_page VARCHAR(32) COMMENT '论文在期刊的末页页码',

    -- ========================
    -- 4. 引用与被引
    -- ========================
    reference_nums INT COMMENT '引用文献数量',
    reference_content TEXT COMMENT '引用文献内容',
    reference_id_list JSON COMMENT '引用文献ID列表；英文名为自定义，图中仅提供中文字段描述',

    citation_nums INT COMMENT '被引用文献数量',
    citation_content TEXT COMMENT '被引用文献内容',
    citation_id_list JSON COMMENT '被引用文献ID列表；英文名为自定义，图中仅提供中文字段描述',

    relevant TEXT COMMENT '相关文章',

    -- ========================
    -- 5. 作者与机构（保持原始嵌套路径）
    -- ========================
    authors JSON COMMENT '作者信息列表',

    `authors[].id` VARCHAR(64) COMMENT '作者ID',
    `authors[].organizationInfos[].id` VARCHAR(64) COMMENT '机构ID',
    `authors[].organizationInfos[].address` TEXT COMMENT '中文地址',
    `authors[].organizationInfos[].organizationName` VARCHAR(255) COMMENT '机构中文名称',

    `authors[].personinfo.fullName` VARCHAR(255) COMMENT '中文全名',
    `authors[].personinfo.professionalTitle` VARCHAR(255) COMMENT '中文专业职称',

    `authors[].role` VARCHAR(255) COMMENT '作者角色（如通讯作者等）',

    -- ========================
    -- 6. 期刊基础信息
    -- ========================
    iscn VARCHAR(64) COMMENT '国内刊号',
    issn VARCHAR(64) COMMENT 'ISSN',
    eissn VARCHAR(64) COMMENT 'EISSN',

    journal_name_zh VARCHAR(255) COMMENT '期刊/顶会名/预印本（中文）',
    journal_name_en VARCHAR(255) COMMENT '期刊/顶会名/预印本（英文）',
    journal_type VARCHAR(255) COMMENT '期刊/顶会类别或预印本',

    journal_abbreviation VARCHAR(255) COMMENT '简称',
    journal_alias VARCHAR(255) COMMENT '期刊/顶会别名',
    country VARCHAR(128) COMMENT '国家',

    zh_description TEXT COMMENT '期刊/顶会描述',
    format VARCHAR(64) COMMENT '开本',
    founding_time DATE COMMENT '创刊时间',
    language VARCHAR(64) COMMENT '语言',
      -- ========================
    -- 7. 出版信息
    -- ========================
    postal_code VARCHAR(32) COMMENT '邮发代号',
    chief_editor VARCHAR(255) COMMENT '主编',
    organizer VARCHAR(255) COMMENT '主办单位',
    publisher_place VARCHAR(255) COMMENT '出版地',
    publication_cycle VARCHAR(128) COMMENT '出版周期',
    mobile VARCHAR(64) COMMENT '期刊出版商电话',
    address TEXT COMMENT '期刊出版商地址',
    in_official TEXT COMMENT '期刊官网',

    -- ========================
    -- 8. 期刊评价指标
    -- ========================
    award TEXT COMMENT '获奖情况',
    cite_nums INT COMMENT '被引用量',
    fund_nums INT COMMENT '基金论文量',
    paper_nums INT COMMENT '出版论文量',
    download_nums INT COMMENT '下载量',
    review VARCHAR(64) COMMENT '是否为综述性期刊',
    annual_publication INT COMMENT '年文章数',

    impact_factor DECIMAL(10,4) COMMENT '影响因子',
    journal_db_str TEXT COMMENT '收录数据库',
    open_access VARCHAR(32) COMMENT '是否OA',

    scope TEXT COMMENT '中科院分类：大类学科',
    scope_zone TEXT COMMENT '中科院分类：小类学科',

    warning_flag BOOLEAN COMMENT '是否预警',

    -- ========================
    -- 9. 其它字段需求（完全按图）
    -- ========================
    `partition.source` VARCHAR(64) COMMENT '期刊分类来源（SCI/WOS/CCF/JCR）',
    `partition.subject_level` VARCHAR(64) COMMENT '期刊学科分类级别',
    `partition.partition` VARCHAR(64) COMMENT '期刊学科分区（Q1/Q2等）',

    content TEXT COMMENT '论文正文',
    location VARCHAR(255) COMMENT '发表机构地点经纬度',
    pdf TEXT COMMENT '论文PDF文件'

);