CREATE TABLE org_domestic (
    -- =========================
    -- 1. 机构基本信息
    -- =========================
    name_cn VARCHAR(255) COMMENT '机构名称',
    external_id VARCHAR(64) COMMENT '统一社会信用代码',
    province VARCHAR(128) COMMENT '所在省份',
    city VARCHAR(128) COMMENT '所在城市',
    address TEXT COMMENT '公司地址',
    lng_lat VARCHAR(64) COMMENT '经纬度',
    postal_code VARCHAR(32) COMMENT '邮政编码',
    phone VARCHAR(64) COMMENT '联系方式',
    fax VARCHAR(64) COMMENT '传真号码',
    email VARCHAR(128) COMMENT '电子邮箱',
    website VARCHAR(255) COMMENT '公司网站',

    affiliates_name VARCHAR(255) COMMENT '下属公司名称',
    affiliates_company_id VARCHAR(64) COMMENT '下属公司统一社会信用代码',
    affiliates_ownership_percentage DECIMAL(5,2) COMMENT '下属所有权比例',

    operational_status VARCHAR(64) COMMENT '运营状态',
    representative_name VARCHAR(128) COMMENT '法人名字',
    legal_form VARCHAR(128) COMMENT '企业登记注册类型',
    company_type VARCHAR(128) COMMENT '企业类型',
    company_tag VARCHAR(255) COMMENT '企业认证标签（高新技术企业、专精特新、瞪羚企业等）',
    registration_org VARCHAR(255) COMMENT '登记机关',

    incorporation_year INT COMMENT '成立年份',
    incorporation_date DATE COMMENT '成立日期',
    dissolve_date DATE COMMENT '注销日期',

    start_date DATE COMMENT '经营期限自',
    end_date DATE COMMENT '经营期限至',

    listing_status VARCHAR(64) COMMENT '上市状态',
    listing_date DATE COMMENT '上市日期',

    registered_capital_value DECIMAL(18,2) COMMENT '注册资本',
    paid_capital_value DECIMAL(18,2) COMMENT '实缴资本',
    capital_currency_code VARCHAR(16) COMMENT '资本货币代码',

    -- =========================
    -- 2. 股东信息
    -- =========================
    owners_name VARCHAR(255) COMMENT '持股者名称',
    owners_type VARCHAR(128) COMMENT '持股者类别',
    ownership_percentage DECIMAL(5,2) COMMENT '所有权占比',

    -- =========================
    -- 3. 高管信息
    -- =========================
    executives_name VARCHAR(255) COMMENT '高管姓名',
    executives_position_code VARCHAR(64) COMMENT '职位编码',
    executives_position VARCHAR(128) COMMENT '职位名称',
    is_representative VARCHAR(32) COMMENT '是否法定代表人',

    -- =========================
    -- 4. 公司经营信息
    -- =========================
    industry_class VARCHAR(128) COMMENT '公司行业分类',
    main_activities VARCHAR(255) COMMENT '公司主要业务行业',
    description TEXT COMMENT '业务描述',
    main_products TEXT COMMENT '主要产品',

    -- =========================
    -- 5. 年报财务信息
    -- =========================
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

    -- =========================
    -- 6. 重点资讯
    -- =========================
    news_title VARCHAR(500) COMMENT '资讯标题',
    news_classification VARCHAR(255) COMMENT '资讯分类（业融资、并购、战略合作、新品发布等）',
    news_date DATE COMMENT '资讯日期',
    news_content TEXT COMMENT '资讯正文',
    original_textlink TEXT COMMENT '资讯原文链接',

    -- =========================
    -- 7. 企业工商变更
    -- =========================
    former_name VARCHAR(255) COMMENT '企业曾用名',
    update_content TEXT COMMENT '变更项',
    current_name VARCHAR(255) COMMENT '变更前名称',
    update_name VARCHAR(255) COMMENT '变更后名称',
    update_date DATE COMMENT '变更日期',

    -- =========================
    -- 8. 并购事件
    -- =========================
    acquisition_party VARCHAR(255) COMMENT '并购方',
    acquisition_type VARCHAR(128) COMMENT '并购方式',
    acquisition_amount DECIMAL(18,2) COMMENT '并购金额',
    acquisition_currency_code VARCHAR(16) COMMENT '并购金额币种',

    -- =========================
    -- 9. 融资事件
    -- =========================
    funding_round VARCHAR(128) COMMENT '投资轮次',
    funding_amount DECIMAL(18,2) COMMENT '获投金额',
    funding_currency_code VARCHAR(16) COMMENT '币种',
    post_valuation DECIMAL(18,2) COMMENT '投后估值',
    pre_valuation DECIMAL(18,2) COMMENT '投前估值',
    completion_date DATE COMMENT '融资完成时间',
    investors_name TEXT COMMENT '投资方列表',

    -- =========================
    -- 10. 投资事件
    -- =========================
    portfolio_name VARCHAR(255) COMMENT '被投企业名称',
    portfolio_external_id VARCHAR(64) COMMENT '被投企业外部ID',
    investment_amount DECIMAL(18,2) COMMENT '投资金额',
    investment_ratio DECIMAL(5,2) COMMENT '投资比例',

    -- =========================
    -- 11. 招投标事件
    -- =========================
    client_name VARCHAR(255) COMMENT '甲方名称',
    contractor_name VARCHAR(255) COMMENT '乙方名称',
    announcement_title VARCHAR(500) COMMENT '公告标题',
    announcement_content TEXT COMMENT '公告正文',
    announcement_date DATE COMMENT '公告发布日期',

    -- =========================
    -- 12. 招聘信息
    -- =========================
    job_title VARCHAR(255) COMMENT '工作类型',
    job_description TEXT COMMENT '职位描述',
    work_place VARCHAR(255) COMMENT '工作地点',
    release_date DATE COMMENT '发布日期',
    hiring_number INT COMMENT '招聘人数'
);