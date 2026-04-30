CREATE TABLE org_foreign (
    -- 1. 机构基本信息
    name_en VARCHAR(255) COMMENT '机构名称',
    name_alias TEXT COMMENT '机构的各类别名（含大小写变体、多语言变体）',
    country VARCHAR(128) COMMENT '国家',
    external_id VARCHAR(64) COMMENT '当地官方唯一注册码',
    province VARCHAR(128) COMMENT '所在州',
    city VARCHAR(128) COMMENT '所在城市',
    address TEXT COMMENT '公司地址',
    postal_code VARCHAR(32) COMMENT '邮政编码',
    phone VARCHAR(64) COMMENT '联系方式',
    fax VARCHAR(64) COMMENT '传真号码',
    email VARCHAR(128) COMMENT '电子邮箱',
    website VARCHAR(255) COMMENT '公司网站',
    operational_status VARCHAR(64) COMMENT '运营状态',
    legal_form VARCHAR(128) COMMENT '企业登记注册类型',
    registration_org VARCHAR(255) COMMENT '注册机构',
    incorporation_year INT COMMENT '成立年份',
    incorporation_date DATE COMMENT '成立日期/注册日期/核准日期',
    listing_status VARCHAR(64) COMMENT '上市状态',
    registered_capital_value DECIMAL(18,2) COMMENT '注册资本',
    registered_capital_currency VARCHAR(32) COMMENT '注册资本货币代码',

    -- 2. 股东、股权及出资信息
    owners_name VARCHAR(255) COMMENT '持股者名称',
    ownership_percentage DECIMAL(8,4) COMMENT '所有权占比',
    affiliates_name VARCHAR(255) COMMENT '下属公司名称',
    affiliates_country VARCHAR(128) COMMENT '下属公司国家',
    affiliates_company_id VARCHAR(64) COMMENT '下属公司唯一注册码',
    affiliates_ownership_percentage DECIMAL(8,4) COMMENT '下属公司所有权明细',

    -- 3. 高管信息
    executives_name VARCHAR(255) COMMENT '高管姓名',
    executives_position_code VARCHAR(64) COMMENT '职位编码',
    executives_position VARCHAR(128) COMMENT '职位名称',

    -- 4. 公司经营信息
    industry_class VARCHAR(128) COMMENT '公司业务行业分类',
    main_activities VARCHAR(255) COMMENT '公司主要业务行业',
    market_segments TEXT COMMENT '市场细分',
    description TEXT COMMENT '业务描述',
    main_products TEXT COMMENT '主要产品',

    -- 5. 年报财务信息
    year INT COMMENT '年报年度',
    total_assets DECIMAL(18,2) COMMENT '资产总额',
    fixed_assets DECIMAL(18,2) COMMENT '固定资产总额',
    total_liabilities DECIMAL(18,2) COMMENT '负债总额',
    operating_revenue DECIMAL(18,2) COMMENT '营业收入',
    main_business_revenue DECIMAL(18,2) COMMENT '主营业务收入',
    total_profit DECIMAL(18,2) COMMENT '利润总额',
    pure_profit DECIMAL(18,2) COMMENT '净利润',
    total_tax_paid DECIMAL(18,2) COMMENT '纳税总额',
    oper_cash_flow DECIMAL(18,2) COMMENT '经营活动现金流',
    owners_equity DECIMAL(18,2) COMMENT '所有者权益合计',
    employees_number INT COMMENT '从业人数',
    research_development_amount DECIMAL(18,2) COMMENT '研发投入金额',
    research_development_employees_number INT COMMENT '研发人员数',

    -- 6. 重点资讯
    news_title VARCHAR(500) COMMENT '资讯标题',
    news_classification VARCHAR(255) COMMENT '资讯分类（业融资、并购、战略合作、新品发布等）',
    news_date DATE COMMENT '资讯日期',
    news_content TEXT COMMENT '资讯正文',

    -- 7. 投融资记录
    company_id VARCHAR(64) COMMENT '国内外公司机构ID',
    turn VARCHAR(128) COMMENT '融资轮次',
    amount DECIMAL(18,2) COMMENT '融资金额',
    currency VARCHAR(32) COMMENT '币种',
    post_investment DECIMAL(18,2) COMMENT '投后估值',
    pre_investment DECIMAL(18,2) COMMENT '投前估值',
    close_date DATE COMMENT '融资完成时间',
    investor_ids TEXT COMMENT '投资方列表',
    lead_investor VARCHAR(255) COMMENT '领投方',
    co_investors TEXT COMMENT '跟投方',
    is_strategic_investment VARCHAR(32) COMMENT '是否为战略投资',
    is_merge VARCHAR(32) COMMENT '是否为并购',
    use_of_funds TEXT COMMENT '资金用途',
    highlights TEXT COMMENT '融资亮点',
    tags TEXT COMMENT '技术/产品方向标签',
    is_first VARCHAR(32) COMMENT '是否为首次融资/连续融资'
);