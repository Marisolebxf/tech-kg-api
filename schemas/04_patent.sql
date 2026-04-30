CREATE TABLE patent (
    -- 1. 专利基本信息
    id VARCHAR(64) PRIMARY KEY COMMENT '专利id（与DOCDB兼容）',
    publication_Number VARCHAR(64) COMMENT '专利公开号',
    application_Number VARCHAR(64) COMMENT '专利申请号',
    country VARCHAR(64) COMMENT '国家',
    country_Code VARCHAR(32) COMMENT '国家代码',
    kind_Code VARCHAR(32) COMMENT '种类代码',
    application_Kind VARCHAR(32) COMMENT '专利申请类型',
    pct_PublicationNumber VARCHAR(64) COMMENT 'PCT国际申请的公开号',
    pct_Number VARCHAR(64) COMMENT 'PCT申请号',
    spif_Application_Number VARCHAR(64) COMMENT 'SPIF标准申请号',
    spif_Publication_Number VARCHAR(64) COMMENT 'SPIF标准公开号',

    title_Localized TEXT COMMENT '标题',
    abstract_Localized TEXT COMMENT '摘要',
    claims_Localized TEXT COMMENT '权利要求',
    description_Localized TEXT COMMENT '说明书',
    publication_Year INT COMMENT '发布年份',
    filing_Year INT COMMENT '申请年份',
    publication_Date DATE COMMENT '发布日期',
    filing_Date DATE COMMENT '申请日期',

    inventor TEXT COMMENT '发明人',
    grant_Number VARCHAR(64) COMMENT '授权号；英文名为自定义，图中仅提供中文字段描述',
    inventor_Harmonized TEXT COMMENT '发明者信息',
    assignee TEXT COMMENT '受让人/申请人',
    assignee_id VARCHAR(64) COMMENT '受让人/申请人ID（跨库绑定）；英文名为自定义，图中仅提供中文字段描述',
    assignee_Harmonized TEXT COMMENT '受让人/申请人信息',

    ipc TEXT COMMENT '国际专利分类',
    cpc TEXT COMMENT '合作专利分类',
    figures TEXT COMMENT '专利图',
    `language` VARCHAR(64) COMMENT '原文语言',
    keywords TEXT COMMENT '关键词',
    concepts TEXT COMMENT '概念',
    definitions TEXT COMMENT '定义',
    landscapes TEXT COMMENT '技术领域分类',

    -- 2. 专利引用信息
    patent_Citations TEXT COMMENT '专利引用',
    citation_Nums INT COMMENT '专利引用数量',
    cited_By TEXT COMMENT '专利被引用',
    cited_By_Nums INT COMMENT '专利被引数量',
    family_Citations TEXT COMMENT '家族内引用',
    cited_By_Family TEXT COMMENT '家族内被引用',
    non_Patent_Citations TEXT COMMENT '非专利引用',
    docdb_Family TEXT COMMENT '专利家族',
    family_id VARCHAR(64) COMMENT '专利家族ID；英文名为自定义，图中仅提供中文字段描述',

    -- 3. 关联信息
    worldwides TEXT COMMENT '全球同族专利',
    priority_Filings TEXT COMMENT '优先权信息',
    expiration_Year INT COMMENT '优先权年',
    priority_Date DATE COMMENT '优先权日',
    priority_Claim TEXT COMMENT '优先权声明',
    prior_Art_Year INT COMMENT '现有技术年份',
    prior_Art_Date DATE COMMENT '现有技术日期',
    relevants TEXT COMMENT '相关专利',
    other_Versions TEXT COMMENT '其他版本',

    -- 4. 法律状态
    `status` VARCHAR(64) COMMENT '专利状态',
    expiration_Year_legal INT COMMENT '到期年份；字段名因与 expiration_Year 重名而加后缀，原图字段名同为 expiration_Year',
    anticipated_Expiration DATE COMMENT '预计到期日',
    current_Assignee VARCHAR(255) COMMENT '当前受让人/申请人',
    legal_Events TEXT COMMENT '法律事件',

    -- 5. 代理信息
    ipc_class VARCHAR(64) COMMENT 'IPC分类号',
    abstract_en TEXT COMMENT '英文摘要',
    title_en TEXT COMMENT '英文标题',
    agent_org VARCHAR(255) COMMENT '代理机构名称',
    agent_org_id VARCHAR(64) COMMENT '代理机构名称ID；英文名为自定义，图中仅提供中文字段描述',
    agent_person VARCHAR(255) COMMENT '代理人姓名',
    agent_contact VARCHAR(255) COMMENT '联系方式',
    priority_country VARCHAR(128) COMMENT '优先权所属国家 / 地区',

    -- 6. 专利原文
    `content` TEXT COMMENT '专利原文'
);