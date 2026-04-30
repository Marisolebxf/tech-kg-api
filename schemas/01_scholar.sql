CREATE TABLE scholar (

    -- ========================
    -- 1. 学者基础身份信息
    -- ========================
    scholarId VARCHAR(64) PRIMARY KEY COMMENT '学者ID',
    nameEn VARCHAR(255) COMMENT '英文名',
    nameZh VARCHAR(255) COMMENT '中文名',
    avatar TEXT COMMENT '头像URL',

    profileImageBase64 TEXT COMMENT '头像（base64）文件；英文名为自定义，图中仅提供中文字段描述',
    thesisBaiduNetdiskUrl TEXT COMMENT '论文作者ID映射列表；英文名为自定义，图中仅提供中文字段描述',

    -- ========================
    -- 2. 学术影响力指标
    -- ========================
    paperNums INT COMMENT '论文数量',
    citationNums INT COMMENT '被引数量',
    hIndex INT COMMENT 'H指数',

    -- ========================
    -- 3. 组织与职业信息
    -- ========================
    scholarOrgNameEn VARCHAR(255) COMMENT '所属机构英文名',
    scholarOrgNameZh VARCHAR(255) COMMENT '所属机构中文名',

    scholarOrgId VARCHAR(64) COMMENT '所属机构ID；英文名为自定义，图中仅提供中文字段描述',
    workExperienceOrgId VARCHAR(64) COMMENT '工作经历机构ID；英文名为自定义，图中仅提供中文字段描述',
    workExperienceOrgName VARCHAR(255) COMMENT '工作经历机构名称；英文名为自定义，图中仅提供中文字段描述',
    workExperienceOrgNameEn VARCHAR(255) COMMENT '所属机构英文名（工作经历语境复用）',
    workExperienceOrgNameZh VARCHAR(255) COMMENT '所属机构中文名（工作经历语境复用）',

    workExperienceEn TEXT COMMENT '工作经历（英文）',
    workExperienceZh TEXT COMMENT '工作经历（中文）',

    -- ========================
    -- 4. 研究领域与背景
    -- ========================
    researchDirection TEXT COMMENT '研究方向',
    educationBackgroundEn TEXT COMMENT '教育背景（英文）',
    educationBackgroundZh TEXT COMMENT '教育背景（中文）',

    -- ========================
    -- 5. 学术产出与合作（仅字段映射，不做关系扩展）
    -- ========================
    paperId VARCHAR(64) COMMENT '论文唯一ID',
    title VARCHAR(500) COMMENT '论文标题',
    enName VARCHAR(500) COMMENT '英文题目',
    zhName VARCHAR(500) COMMENT '中文题目',
    authors JSON COMMENT '作者列表',
    publicationEnName VARCHAR(255) COMMENT '期刊/会议名称',
    coverDateStart DATE COMMENT '发表时间',
    impactFactor DECIMAL(10,4) COMMENT '影响因子',
    doi VARCHAR(255) COMMENT 'DOI',
    enAbstract TEXT COMMENT '英文摘要',
    zhAbstract TEXT COMMENT '中文摘要',
    paperUrl TEXT COMMENT '论文原始链接',

    coPaperCount INT COMMENT '合作论文数量',

    -- ========================
    -- 6. 其他人才信息
    -- ========================
    is_Academician BOOLEAN COMMENT '是否院士',
    professional_title_level VARCHAR(255) COMMENT '当前职称级别',
    emails TEXT COMMENT '学者邮箱',
    gender VARCHAR(32) COMMENT '性别',
    bio TEXT COMMENT '个人简介/学术简介',
    bio_zh TEXT COMMENT '个人简介/学术简介（中文）',
    address TEXT COMMENT '通讯地址',
    birth DATE COMMENT '出生日期',
    patent TEXT COMMENT '专利信息',
    fax VARCHAR(128) COMMENT '传真号',
    passaway DATE COMMENT '逝世日期（如有）',
    position_en VARCHAR(255) COMMENT '职位（英文）',
    personal_homepage TEXT COMMENT '个人主页',

    -- ========================
    -- 7. 心理信息
    -- ========================
    integrity_records TEXT COMMENT '科研诚信记录',
    misconduct_events TEXT COMMENT '学术不端事件',
    award_records TEXT COMMENT '奖项信息',
    integrity_score DECIMAL(10,4) COMMENT '诚信评分',
    political_score DECIMAL(10,4) COMMENT '政治评分',
    sentiment_score DECIMAL(10,4) COMMENT '情感评分',
    risk_assessment TEXT COMMENT '风险评估结果',

    -- ========================
    -- 8. 迁徙信息
    -- ========================
    flowSourceCode VARCHAR(255) COMMENT '来源地编码；英文名为自定义，图中仅提供中文字段描述',
    flowDestinationCode VARCHAR(255) COMMENT '目的地编码；英文名为自定义，图中仅提供中文字段描述',
    flowTime DATE COMMENT '流动时间；英文名为自定义，图中仅提供中文字段描述',
    flowReason TEXT COMMENT '流动原因；英文名为自定义，图中仅提供中文字段描述',
    updateDate DATETIME COMMENT '更新日期；英文名为自定义，图中仅提供中文字段描述'

);