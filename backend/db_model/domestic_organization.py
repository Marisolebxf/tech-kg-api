from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
)

from db_model.base import Base


class DwdOrgAnnualFinancialInfo(Base):
    """前海数据机构年报财务信息"""

    __tablename__ = "dwd_org_annual_financial_info"
    __table_args__ = {"comment": "前海数据机构年报财务信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    org_type = Column("org_type", String(50), nullable=True, comment="机构类型")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    year = Column("year", Integer(), nullable=True, comment="年报年度")
    total_assets = Column("total_assets", Float(), nullable=True, comment="资产总额")
    total_fixed_assets = Column(
        "total_fixed_assets", Float(), nullable=True, comment="固定资产总额"
    )
    total_liabilities = Column("total_liabilities", Float(), nullable=True, comment="负债总额")
    operating_revenue = Column("operating_revenue", Float(), nullable=True, comment="营业收入")
    main_business_revenue = Column(
        "main_business_revenue", Float(), nullable=True, comment="主营业务收入"
    )
    total_profit = Column("total_profit", Float(), nullable=True, comment="利润总额")
    pure_profit = Column("pure_profit", Float(), nullable=True, comment="净利润")
    total_tax_paid = Column("total_tax_paid", Float(), nullable=True, comment="纳税总额")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgBankruptcyPublicCases(Base):
    """破产案件表"""

    __tablename__ = "dwd_org_bankruptcy_public_cases"
    __table_args__ = {"comment": "破产案件表"}

    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    case_type = Column("case_type", String(255), nullable=True, comment="案件类型")
    handling_court = Column("handling_court", String(255), nullable=True, comment="经办法院")
    applicant_info = Column("applicant_info", Text(), nullable=True, comment="申请人信息")
    respondent_info = Column("respondent_info", Text(), nullable=True, comment="被申请人信息")
    admin_org = Column("admin_org", String(255), nullable=True, comment="管理人机构")
    admin_org_id = Column("admin_org_id", String(255), nullable=True, comment="管理人机构id")
    admin_principal = Column(
        "admin_principal", String(255), nullable=True, comment="管理人主要负责人"
    )
    public_date = Column("public_date", String(255), nullable=True, comment="公开时间")
    link = Column("link", Text(), nullable=True, comment="链接")
    is_deleted = Column("is_deleted", String(255), nullable=True, comment="是否删除")
    history_status = Column("history_status", String(255), nullable=True, comment="历史状态")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [case_no]}


class DwdOrgBankruptcyPublicCasesList(Base):
    """破产案件当事人表"""

    __tablename__ = "dwd_org_bankruptcy_public_cases_list"
    __table_args__ = {"comment": "破产案件当事人表"}

    bankruptcy_party_id = Column(
        "bankruptcy_party_id", String(255), nullable=True, comment="唯一索引id"
    )
    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    related_person_name = Column(
        "related_person_name", String(255), nullable=True, comment="相关人名称"
    )
    party_role_type = Column(
        "party_role_type", String(255), nullable=True, comment="当事人角色类型"
    )
    party_type = Column("party_type", String(255), nullable=True, comment="当事人类型")
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    public_date = Column("public_date", String(255), nullable=True, comment="公开时间")
    is_deleted = Column("is_deleted", String(255), nullable=True, comment="是否删除")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [bankruptcy_party_id]}


class DwdOrgBidInfo(Base):
    """前海数据机构招投标事件"""

    __tablename__ = "dwd_org_bid_info"
    __table_args__ = {"comment": "前海数据机构招投标事件"}

    tender_org_id = Column("tender_org_id", String(50), nullable=True, comment="采购单位id")
    tender_name_cn = Column("tender_name_cn", String(255), nullable=True, comment="采购单位名称")
    tender_social_credit_code = Column(
        "tender_social_credit_code", String(50), nullable=True, comment="采购单位统一社会信用代码"
    )
    winner_org_id = Column("winner_org_id", String(50), nullable=True, comment="中标单位id")
    winner_name_cn = Column("winner_name_cn", String(255), nullable=True, comment="中标单位名称")
    winner_social_credit_code = Column(
        "winner_social_credit_code", String(50), nullable=True, comment="中标单位统一社会信用代码"
    )
    announcement_title = Column(
        "announcement_title", String(255), nullable=True, comment="公告标题"
    )
    announcement_content = Column(
        "announcement_content", String(50), nullable=True, comment="中标成交信息"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [tender_org_id]}


class DwdOrgChangeRecordInfo(Base):
    """前海数据机构工商变更信息"""

    __tablename__ = "dwd_org_change_record_info"
    __table_args__ = {"comment": "前海数据机构工商变更信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    update_content = Column("update_content", String(50), nullable=True, comment="变更类型")
    current_name = Column("current_name", String(1000), nullable=True, comment="变更前内容")
    update_name = Column("update_name", String(1000), nullable=True, comment="变更后内容")
    update_date = Column("update_date", String(50), nullable=True, comment="变更日期")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgCompanyAbnormal(Base):
    """前海数据机构经营异常事件"""

    __tablename__ = "dwd_org_company_abnormal"
    __table_args__ = {"comment": "前海数据机构经营异常事件"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    abnormal_id = Column("abnormal_id", String(50), nullable=True, comment="经营异常记录id")
    abn_reason = Column("abn_reason", String(1000), nullable=True, comment="列入原因")
    abn_date = Column("abn_date", String(50), nullable=True, comment="列入时间")
    abn_org = Column("abn_org", String(50), nullable=True, comment="列入机关")
    remove_reason = Column("remove_reason", String(1000), nullable=True, comment="移除原因")
    remove_date = Column("remove_date", String(50), nullable=True, comment="移除时间")
    remove_org = Column("remove_org", String(50), nullable=True, comment="移除机关")
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标记")
    status_code = Column("status_code", Integer(), nullable=True, comment="状态")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgCompanyChattel(Base):
    """动产抵押表"""

    __tablename__ = "dwd_org_company_chattel"
    __table_args__ = {"comment": "动产抵押表"}

    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    reg_no = Column("reg_no", String(255), nullable=True, comment="登记编号")
    reg_date = Column("reg_date", String(255), nullable=True, comment="登记日期")
    reg_org = Column("reg_org", String(255), nullable=True, comment="登记机关")
    guarantee_type = Column("guarantee_type", String(255), nullable=True, comment="被担保债权种类")
    guarantee_amount = Column(
        "guarantee_amount", String(255), nullable=True, comment="被担保债权数额"
    )
    guarantee_scope = Column("guarantee_scope", Text(), nullable=True, comment="担保范围")
    public_date = Column("public_date", String(255), nullable=True, comment="公示日期")
    debt_term = Column("debt_term", String(255), nullable=True, comment="债务人履行债务的期限")
    debt_remark = Column("debt_remark", Text(), nullable=True, comment="主债权信息备注")
    status = Column("status", String(255), nullable=True, comment="状态")
    cancel_date = Column("cancel_date", String(255), nullable=True, comment="注销日期")
    cancel_reason = Column("cancel_reason", Text(), nullable=True, comment="注销原因")
    status_code = Column("status_code", String(255), nullable=True, comment="状态代码")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标记")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgCompanyIllegal(Base):
    """前海数据机构严重违法"""

    __tablename__ = "dwd_org_company_illegal"
    __table_args__ = {"comment": "前海数据机构严重违法"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    sv_id = Column("sv_id", String(50), nullable=True, comment="严重违法记录id")
    category = Column("category", String(50), nullable=True, comment="类别")
    abn_reason = Column("abn_reason", String(1000), nullable=True, comment="列入原因")
    abn_date = Column("abn_date", String(50), nullable=True, comment="列入时间")
    abn_org = Column("abn_org", String(50), nullable=True, comment="列入机关")
    remove_reason = Column("remove_reason", String(1000), nullable=True, comment="移除原因")
    remove_date = Column("remove_date", String(50), nullable=True, comment="移除时间")
    remove_org = Column("remove_org", String(50), nullable=True, comment="移除机关")
    status = Column("status", Integer(), nullable=True, comment="状态")
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标记")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgCompanyJustice(Base):
    """股权冻结表"""

    __tablename__ = "dwd_org_company_justice"
    __table_args__ = {"comment": "股权冻结表"}

    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    judicial_assist_id = Column(
        "judicial_assist_id", String(255), nullable=True, comment="司法协助记录id"
    )
    executed_person = Column("executed_person", String(255), nullable=True, comment="被执行人")
    equity_amount = Column("equity_amount", String(255), nullable=True, comment="股权数额")
    exec_court = Column("exec_court", String(255), nullable=True, comment="执行法院")
    exec_notice_no = Column("exec_notice_no", String(255), nullable=True, comment="执行通知书文号")
    type_status = Column("type_status", String(255), nullable=True, comment="类型|状态")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标记")
    status = Column("status", String(255), nullable=True, comment="状态")
    executed_person_type = Column(
        "executed_person_type", String(255), nullable=True, comment="被执行人类型"
    )
    executed_company_id = Column(
        "executed_company_id", String(255), nullable=True, comment="被执行人的company_id"
    )
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgCompanyPledge(Base):
    """股权出质表"""

    __tablename__ = "dwd_org_company_pledge"
    __table_args__ = {"comment": "股权出质表"}

    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    pledge_id = Column("pledge_id", String(255), nullable=True, comment="股权出质记录id")
    reg_no = Column("reg_no", String(255), nullable=True, comment="登记编号")
    pledgor = Column("pledgor", String(255), nullable=True, comment="出质人")
    pledgor_id_no = Column("pledgor_id_no", String(255), nullable=True, comment="出质人证件号码")
    pledgee = Column("pledgee", String(255), nullable=True, comment="质权人")
    pledgee_id_no = Column("pledgee_id_no", String(255), nullable=True, comment="质权人证件号码")
    equity_amount = Column("equity_amount", String(255), nullable=True, comment="出质股权数额")
    pledge_reg_date = Column(
        "pledge_reg_date", String(255), nullable=True, comment="股权出质设立登记日期"
    )
    status = Column("status", String(255), nullable=True, comment="状态")
    public_date = Column("public_date", String(255), nullable=True, comment="公示日期")
    cancel_date = Column("cancel_date", String(255), nullable=True, comment="注销日期")
    cancel_reason = Column("cancel_reason", Text(), nullable=True, comment="注销原因")
    invalid_date = Column("invalid_date", String(255), nullable=True, comment="失效时间")
    invalid_reason = Column("invalid_reason", Text(), nullable=True, comment="失效原因")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标记")
    status_code = Column("status_code", String(255), nullable=True, comment="状态代码")
    province_abbr = Column("province_abbr", String(255), nullable=True, comment="省份简称")
    pledgor_company_id = Column(
        "pledgor_company_id", String(255), nullable=True, comment="机构出质人的company_id"
    )
    pledgor_company_name = Column(
        "pledgor_company_name", String(255), nullable=True, comment="机构出质人名称"
    )
    pledgor_credit_code = Column(
        "pledgor_credit_code", String(255), nullable=True, comment="机构出质人统一社会信用代码"
    )
    pledgor_type = Column("pledgor_type", String(255), nullable=True, comment="出质人类型")
    pledgee_company_id = Column(
        "pledgee_company_id", String(255), nullable=True, comment="机构质权人的company_id"
    )
    pledgee_company_name = Column(
        "pledgee_company_name", String(255), nullable=True, comment="机构质权人名称"
    )
    pledgee_credit_code = Column(
        "pledgee_credit_code", String(255), nullable=True, comment="机构质权人统一社会信用代码"
    )
    pledgee_type = Column("pledgee_type", String(255), nullable=True, comment="质权人类型")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgCompanyPunish(Base):
    """前海数据机构行政处罚记录"""

    __tablename__ = "dwd_org_company_punish"
    __table_args__ = {"comment": "前海数据机构行政处罚记录"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    penalty_id = Column("penalty_id", String(50), nullable=True, comment="行政处罚记录id")
    decision_no = Column("decision_no", String(50), nullable=True, comment="决定书文号")
    violation_type = Column("violation_type", String(256), nullable=True, comment="违法行为类型")
    penalty_content = Column("penalty_content", Text(), nullable=True, comment="行政处罚内容")
    decision_org = Column("decision_org", String(50), nullable=True, comment="决定机关")
    penalty_date = Column("penalty_date", String(50), nullable=True, comment="处罚决定日期")
    public_date = Column("public_date", String(50), nullable=True, comment="公示日期")
    penalty_basis = Column("penalty_basis", String(512), nullable=True, comment="处罚依据")
    violation_fact = Column("violation_fact", Text(), nullable=True, comment="主要违法事实")
    penalty_type = Column("penalty_type", String(512), nullable=True, comment="处罚种类")
    fine_amount = Column("fine_amount", String(100), nullable=True, comment="罚款金额")
    confiscate_amount = Column("confiscate_amount", String(100), nullable=True, comment="没收金额")
    license_info = Column(
        "license_info", String(50), nullable=True, comment="暂扣或吊销证照名称及编号"
    )
    validity_period = Column("validity_period", String(50), nullable=True, comment="处罚有效期")
    public_deadline = Column("public_deadline", String(50), nullable=True, comment="公示截止日期")
    remark = Column("remark", String(50), nullable=True, comment="备注")
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标记")
    status_code = Column("status_code", Integer(), nullable=True, comment="状态代码")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgExecutiveInfo(Base):
    """前海数据机构高管信息"""

    __tablename__ = "dwd_org_executive_info"
    __table_args__ = {"comment": "前海数据机构高管信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    executives_name = Column("executives_name", String(50), nullable=True, comment="高管姓名")
    executives_position = Column(
        "executives_position", String(50), nullable=True, comment="职位名称"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgFinancingInfo(Base):
    """前海数据机构融资事件"""

    __tablename__ = "dwd_org_financing_info"
    __table_args__ = {"comment": "前海数据机构融资事件"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    funding_round = Column("funding_round", String(50), nullable=True, comment="融资轮次")
    funding_amount = Column("funding_amount", BigInteger(), nullable=True, comment="获投金额")
    funding_currency_code = Column(
        "funding_currency_code", String(50), nullable=True, comment="金额币种"
    )
    post_valuation = Column("post_valuation", BigInteger(), nullable=True, comment="投后估值")
    completion_date = Column("completion_date", String(50), nullable=True, comment="融资完成时间")
    investors_name = Column("investors_name", String(500), nullable=True, comment="投资方列表")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgHelsInfo(Base):
    """前海数据高校与科研机构信息"""

    __tablename__ = "dwd_org_hels_info"
    __table_args__ = {"comment": "前海数据高校与科研机构信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="高校id")
    name_cn = Column("name_cn", String(256), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    org_name = Column("org_name", String(256), nullable=True, comment="高校/科研机构名称(中文)")
    org_name_en = Column(
        "org_name_en", String(256), nullable=True, comment="高校/科研机构名称(英文)"
    )
    org_desc = Column("org_desc", Text(), nullable=True, comment="高校/科研机构描述")
    address = Column("address", String(500), nullable=True, comment="地址(国家、区域、城市)")
    addr_lng = Column("addr_lng", Float(), nullable=True, comment="地址对应经度")
    addr_lat = Column("addr_lat", Float(), nullable=True, comment="地址对应维度")
    province = Column("province", String(50), nullable=True, comment="地址所在省")
    city = Column("city", String(50), nullable=True, comment="地址所在市")
    univ_type = Column("univ_type", String(50), nullable=True, comment="高校类型")
    web_link = Column("web_link", String(100), nullable=True, comment="官方网址")
    postal_code = Column("postal_code", String(50), nullable=True, comment="邮政编码")
    contact_number = Column("contact_number", String(500), nullable=True, comment="联系电话")
    email = Column("email", Text(), nullable=True, comment="电子邮箱")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgImportantNewsInfo(Base):
    """前海数据机构重点资讯"""

    __tablename__ = "dwd_org_important_news_info"
    __table_args__ = {"comment": "前海数据机构重点资讯"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    news_title = Column("news_title", String(1000), nullable=True, comment="资讯标题")
    news_date = Column("news_date", String(50), nullable=True, comment="资讯日期")
    news_content = Column("news_content", String(1000), nullable=True, comment="资讯内容")
    original_textlink = Column(
        "original_textlink", String(255), nullable=True, comment="咨询原文链接"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgInnovationCarrier(Base):
    """前海数据机构创新载体信息"""

    __tablename__ = "dwd_org_innovation_carrier"
    __table_args__ = {"comment": "前海数据机构创新载体信息"}

    carrier_type = Column("carrier_type", String(50), nullable=True, comment="载体/平台/中心类型")
    carrier_name = Column("carrier_name", String(200), nullable=True, comment="载体/平台/中心名称")
    carrier_level = Column("carrier_level", String(50), nullable=True, comment="载体/平台/中心级别")
    create_year = Column("create_year", Integer(), nullable=True, comment="组建/认定/立项年份")
    area = Column("area", String(50), nullable=True, comment="载体/平台/中心所在地区")
    area_code = Column("area_code", String(50), nullable=True, comment="所在地区行政区划代码")
    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    org_name = Column("org_name", String(200), nullable=True, comment="关联单位名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    announcement = Column("announcement", String(500), nullable=True, comment="公告名称")
    publish_org = Column("publish_org", String(50), nullable=True, comment="发布单位")
    publish_date = Column("publish_date", String(50), nullable=True, comment="发布日期")
    source_url = Column("source_url", String(500), nullable=True, comment="来源链接")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [carrier_type]}


class DwdOrgInvestInfo(Base):
    """前海数据机构投资事件"""

    __tablename__ = "dwd_org_invest_info"
    __table_args__ = {"comment": "前海数据机构投资事件"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    inv_org_id = Column("inv_org_id", String(50), nullable=True, comment="被投企业id")
    inv_name = Column("inv_name", String(50), nullable=True, comment="被投资企业名称")
    inv_social_credit_code = Column(
        "inv_social_credit_code", String(50), nullable=True, comment="被投资企业统一社会信用代码"
    )
    investment_amount = Column("investment_amount", Float(), nullable=True, comment="投资金额(元)")
    investment_ratio = Column("investment_ratio", Float(), nullable=True, comment="股权占比(%)")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgMergerAcquisitionInfo(Base):
    """前海数据机构并购事件"""

    __tablename__ = "dwd_org_merger_acquisition_info"
    __table_args__ = {"comment": "前海数据机构并购事件"}

    event_time = Column("event_time", String(50), nullable=True, comment="公告日期")
    ma_amount = Column("ma_amount", Float(), nullable=True, comment="交易金额")
    currency_code = Column("currency_code", String(50), nullable=True, comment="币种")
    acquiring_org_id = Column(
        "acquiring_org_id", String(50), nullable=True, comment="发起收购企业id"
    )
    acquiring_name = Column("acquiring_name", String(50), nullable=True, comment="发起收购企业名称")
    acquired_org_id = Column("acquired_org_id", String(50), nullable=True, comment="被收购企业id")
    acquired_name = Column("acquired_name", String(50), nullable=True, comment="被收购企业")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [event_time]}


class DwdOrgOptJudicialCase(Base):
    """前海数据机构司法案件事件"""

    __tablename__ = "dwd_org_opt_judicial_case"
    __table_args__ = {"comment": "前海数据机构司法案件事件"}

    company_name = Column("company_name", String(50), nullable=True, comment="企业名称")
    reg_no = Column("reg_no", String(50), nullable=True, comment="注册号")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    case_id = Column("case_id", String(50), nullable=True, comment="司法案件唯一标识")
    case_title = Column("case_title", String(1000), nullable=True, comment="案件标题")
    case_type_tag = Column("case_type_tag", String(100), nullable=True, comment="案件类型标签")
    case_no = Column("case_no", String(1000), nullable=True, comment="案号")
    case_cause = Column("case_cause", String(500), nullable=True, comment="案由")
    case_role = Column("case_role", String(500), nullable=True, comment="案件身份")
    current_procedure = Column(
        "current_procedure", String(50), nullable=True, comment="当前审理程序"
    )
    procedure_date = Column("procedure_date", String(50), nullable=True, comment="当前审理程序日期")
    data_use_flag = Column("data_use_flag", Integer(), nullable=True, comment="数据使用标识")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [company_name]}


class DwdOrgOrgProductInfo(Base):
    """前海数据机构经营信息"""

    __tablename__ = "dwd_org_org_product_info"
    __table_args__ = {"comment": "前海数据机构经营信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    industry_class = Column("industry_class", String(50), nullable=True, comment="公司行业分类")
    main_activities = Column("main_activities", Text(), nullable=True, comment="公司经营范围")
    description = Column("description", Text(), nullable=True, comment="业务描述")
    main_prod = Column("main_prod", Text(), nullable=True, comment="主要产品")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgRecruitInfo(Base):
    """前海数据招聘信息"""

    __tablename__ = "dwd_org_recruit_info"
    __table_args__ = {"comment": "前海数据招聘信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    job_title = Column("job_title", String(255), nullable=True, comment="岗位")
    job_description = Column("job_description", Text(), nullable=True, comment="工作描述")
    work_place = Column("work_place", String(500), nullable=True, comment="工作地点")
    release_date = Column("release_date", String(50), nullable=True, comment="发布日期")
    hiring_number = Column("hiring_number", String(50), nullable=True, comment="招聘人数")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgRegInfo(Base):
    """前海数据机构基本信息"""

    __tablename__ = "dwd_org_reg_info"
    __table_args__ = {"comment": "前海数据机构基本信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    province = Column("province", String(50), nullable=True, comment="所在省份")
    city = Column("city", String(50), nullable=True, comment="所在城市")
    address = Column("address", String(1000), nullable=True, comment="公司地址")
    addr_lng = Column("addr_lng", Float(), nullable=True, comment="地址经度")
    addr_lat = Column("addr_lat", Float(), nullable=True, comment="地址纬度")
    postal_code = Column("postal_code", String(50), nullable=True, comment="邮编")
    lerep = Column("lerep", String(50), nullable=True, comment="法人代表")
    registration_org = Column("registration_org", String(50), nullable=True, comment="登记机关")
    incorporation_year = Column("incorporation_year", Integer(), nullable=True, comment="成立年")
    incorporation_date = Column("incorporation_date", String(50), nullable=True, comment="成立日期")
    start_date = Column("start_date", String(50), nullable=True, comment="经营期限自")
    end_date = Column("end_date", String(50), nullable=True, comment="经营期限至")
    listing_status = Column("listing_status", String(50), nullable=True, comment="上市状态")
    listing_date = Column("listing_date", String(50), nullable=True, comment="上市日期")
    registered_capital_value = Column(
        "registered_capital_value", Float(), nullable=True, comment="注册资本金"
    )
    capital_currency_code = Column(
        "capital_currency_code", String(50), nullable=True, comment="资本货币代码"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgRiskCourtAnnouncement(Base):
    """法院公告表"""

    __tablename__ = "dwd_org_risk_court_announcement"
    __table_args__ = {"comment": "法院公告表"}

    notice_id = Column("notice_id", String(255), nullable=True, comment="公告id")
    notice_no = Column("notice_no", String(255), nullable=True, comment="公告号")
    notice_name = Column("notice_name", String(255), nullable=True, comment="公告名称")
    notice_type = Column("notice_type", String(255), nullable=True, comment="公告类型")
    notice_type_name = Column(
        "notice_type_name", String(255), nullable=True, comment="公告类型名称"
    )
    notice_date = Column("notice_date", String(255), nullable=True, comment="公告日期")
    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    title = Column("title", Text(), nullable=True, comment="标题")
    notice_content = Column("notice_content", Text(), nullable=True, comment="公告内容")
    court_name = Column("court_name", String(255), nullable=True, comment="法院名称")
    handle_level = Column("handle_level", String(255), nullable=True, comment="处理等级")
    handle_level_name = Column(
        "handle_level_name", String(255), nullable=True, comment="处理等级名称"
    )
    judge = Column("judge", String(255), nullable=True, comment="法官")
    judge_phone = Column("judge_phone", String(255), nullable=True, comment="法官电话")
    mobile_phone = Column("mobile_phone", String(255), nullable=True, comment="手机号")
    plaintiff = Column("plaintiff", String(255), nullable=True, comment="原告")
    party = Column("party", String(255), nullable=True, comment="当事人")
    province = Column("province", String(255), nullable=True, comment="省份")
    case_cause = Column("case_cause", String(255), nullable=True, comment="案由")
    notice_year = Column("notice_year", String(100), nullable=True, comment="公告年份")
    publish_date = Column("publish_date", String(255), nullable=True, comment="公告刊登日期")
    publish_page_no = Column(
        "publish_page_no", String(255), nullable=True, comment="公告刊登版面页码"
    )
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    original_url = Column("original_url", Text(), nullable=True, comment="原始连接URL")
    content_md5 = Column("content_md5", String(255), nullable=True, comment="公告内容的md5值")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [notice_id]}


class DwdOrgRiskCourtAnnouncementList(Base):
    """法院公告当事人表"""

    __tablename__ = "dwd_org_risk_court_announcement_list"
    __table_args__ = {"comment": "法院公告当事人表"}

    notice_id = Column("notice_id", String(255), nullable=True, comment="公告id")
    party_identity = Column("party_identity", String(255), nullable=True, comment="当事人身份")
    party_type = Column("party_type", String(255), nullable=True, comment="当事人类型")
    party_role_type = Column(
        "party_role_type", String(255), nullable=True, comment="当事人角色类型"
    )
    related_person_name = Column(
        "related_person_name", String(255), nullable=True, comment="相关人名称"
    )
    publish_date = Column("publish_date", String(255), nullable=True, comment="公告刊登日期")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [notice_id]}


class DwdOrgRiskCourtFiledCase(Base):
    """法院立案表"""

    __tablename__ = "dwd_org_risk_court_filed_case"
    __table_args__ = {"comment": "法院立案表"}

    case_unique_id = Column("case_unique_id", String(255), nullable=True, comment="案件唯一id")
    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    norm_case_no = Column("norm_case_no", String(255), nullable=True, comment="归一化案号")
    case_cause = Column("case_cause", String(255), nullable=True, comment="案由")
    trial_procedure = Column("trial_procedure", String(255), nullable=True, comment="审理程序")
    case_status = Column("case_status", String(255), nullable=True, comment="案件状态")
    norm_case_status = Column(
        "norm_case_status", String(255), nullable=True, comment="归一化后案件状态"
    )
    filing_date = Column("filing_date", String(255), nullable=True, comment="立案日期")
    closing_date = Column("closing_date", String(255), nullable=True, comment="结案日期")
    hearing_date = Column("hearing_date", String(255), nullable=True, comment="开庭日期")
    court_name = Column("court_name", String(255), nullable=True, comment="法院")
    undertaking_dept = Column("undertaking_dept", String(255), nullable=True, comment="承办部门")
    judge = Column("judge", String(255), nullable=True, comment="法官")
    assistant_judge = Column("assistant_judge", String(255), nullable=True, comment="助理法官")
    party_info = Column("party_info", String(5000), nullable=True, comment="当事人信息")
    court_province = Column("court_province", String(255), nullable=True, comment="法院所在省")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [case_unique_id]}


class DwdOrgRiskCourtFiledCaseLitigant(Base):
    """法院立案当事人表"""

    __tablename__ = "dwd_org_risk_court_filed_case_litigant"
    __table_args__ = {"comment": "法院立案当事人表"}

    case_unique_id = Column("case_unique_id", String(255), nullable=True, comment="案件唯一id")
    filing_date = Column("filing_date", String(255), nullable=True, comment="立案日期")
    party_name = Column("party_name", String(255), nullable=True, comment="当事人名称")
    party_role = Column("party_role", String(255), nullable=True, comment="当事人角色")
    classified_org_type = Column(
        "classified_org_type", String(255), nullable=True, comment="归类后企业类型"
    )
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [case_unique_id]}


class DwdOrgRiskCourtNotice(Base):
    """开庭公告表"""

    __tablename__ = "dwd_org_risk_court_notice"
    __table_args__ = {"comment": "开庭公告表"}

    notice_id = Column("notice_id", String(255), nullable=True, comment="公告id")
    court_name = Column("court_name", String(255), nullable=True, comment="法院")
    courtroom = Column("courtroom", String(255), nullable=True, comment="法庭")
    undertaking_dept = Column("undertaking_dept", String(255), nullable=True, comment="承办部门")
    hearing_date = Column("hearing_date", String(255), nullable=True, comment="开庭日期")
    scheduling_date = Column("scheduling_date", String(255), nullable=True, comment="排期日期")
    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    case_cause = Column("case_cause", String(255), nullable=True, comment="案由")
    case_type = Column("case_type", String(255), nullable=True, comment="案件类型")
    jurisdiction_area = Column(
        "jurisdiction_area", String(255), nullable=True, comment="案件管辖区域"
    )
    plaintiff_appellant = Column(
        "plaintiff_appellant", String(255), nullable=True, comment="原告上诉人"
    )
    defendant_appellee = Column(
        "defendant_appellee", String(255), nullable=True, comment="被告被上诉人"
    )
    party = Column("party", String(255), nullable=True, comment="当事人")
    presiding_judge = Column("presiding_judge", String(255), nullable=True, comment="审判长主审人")
    title = Column("title", Text(), nullable=True, comment="标题")
    notice_content = Column("notice_content", Text(), nullable=True, comment="公告内容")
    province = Column("province", String(255), nullable=True, comment="省份")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    original_url = Column("original_url", Text(), nullable=True, comment="原始连接URL")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    data_source_2 = Column(
        "data_source_2",
        String(255),
        nullable=True,
        comment="数据来源（重复字段，已重命名避免冲突）",
    )
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [notice_id]}


class DwdOrgRiskCourtNoticeList(Base):
    """开庭公告当事人表"""

    __tablename__ = "dwd_org_risk_court_notice_list"
    __table_args__ = {"comment": "开庭公告当事人表"}

    notice_id = Column("notice_id", String(255), nullable=True, comment="公告id")
    party_role = Column("party_role", String(255), nullable=True, comment="当事人角色")
    party_role_type = Column(
        "party_role_type", String(255), nullable=True, comment="当事人角色类型"
    )
    party_type = Column("party_type", String(255), nullable=True, comment="当事人类型")
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    related_person_name = Column(
        "related_person_name", String(255), nullable=True, comment="相关人名称"
    )
    hearing_date = Column("hearing_date", String(255), nullable=True, comment="开庭日期")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    case_cause = Column("case_cause", String(255), nullable=True, comment="案由")
    reserve_field = Column("reserve_field", String(255), nullable=True, comment="预留字段")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [notice_id]}


class DwdOrgRiskLawsuit(Base):
    """裁判文书"""

    __tablename__ = "dwd_org_risk_lawsuit"
    __table_args__ = {"comment": "裁判文书"}

    judgment_doc_id = Column(
        "judgment_doc_id", String(255), nullable=True, comment="裁判文书网文书id"
    )
    defendant = Column("defendant", String(255), nullable=True, comment="被告")
    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    case_type_code = Column("case_type_code", String(255), nullable=True, comment="案件类型编码")
    case_type = Column("case_type", String(255), nullable=True, comment="案件类型")
    doc_type_code = Column("doc_type_code", String(255), nullable=True, comment="文书类型编码")
    doc_type = Column("doc_type", String(255), nullable=True, comment="文书类型")
    province = Column("province", String(255), nullable=True, comment="省份")
    city = Column("city", String(255), nullable=True, comment="地市")
    district = Column("district", String(255), nullable=True, comment="区县")
    main_doc_id = Column("main_doc_id", String(255), nullable=True, comment="主表docid")
    court_name = Column("court_name", String(255), nullable=True, comment="法院名称")
    trial_procedure = Column("trial_procedure", String(255), nullable=True, comment="审理程序名称")
    judgment_year = Column("judgment_year", Integer(), nullable=True, comment="裁判年份")
    judgment_date = Column("judgment_date", String(255), nullable=True, comment="裁判日期")
    case_cause = Column("case_cause", String(255), nullable=True, comment="案由")
    doc_title = Column("doc_title", Text(), nullable=True, comment="文书标题")
    doc_full_text = Column("doc_full_text", Text(), nullable=True, comment="文书全文")
    publish_date = Column("publish_date", String(255), nullable=True, comment="公布日期")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    original_url = Column("original_url", Text(), nullable=True, comment="原始连接URL")
    plaintiff = Column("plaintiff", String(255), nullable=True, comment="原告")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    source = Column("source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [judgment_doc_id]}


class DwdOrgRiskLawsuitList(Base):
    """裁判文书当事人表"""

    __tablename__ = "dwd_org_risk_lawsuit_list"
    __table_args__ = {"comment": "裁判文书当事人表"}

    main_doc_id = Column("main_doc_id", String(255), nullable=True, comment="主表docid")
    party_identity = Column("party_identity", String(255), nullable=True, comment="当事人身份")
    party_role_type = Column(
        "party_role_type", String(255), nullable=True, comment="当事人角色类型"
    )
    party_type = Column("party_type", String(255), nullable=True, comment="当事人类型")
    related_person_name = Column(
        "related_person_name", String(255), nullable=True, comment="相关人名称"
    )
    doc_publish_date = Column(
        "doc_publish_date", String(255), nullable=True, comment="文书公布日期"
    )
    case_cause = Column("case_cause", String(255), nullable=True, comment="案由")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [main_doc_id]}


class DwdOrgRiskShixin(Base):
    """前海数据机构失信被执行人记录"""

    __tablename__ = "dwd_org_risk_shixin"
    __table_args__ = {"comment": "前海数据机构失信被执行人记录"}

    dishonest_id = Column("dishonest_id", String(50), nullable=True, comment="失信被执行人id")
    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    official_id = Column("official_id", String(50), nullable=True, comment="官网id")
    case_no = Column("case_no", String(50), nullable=True, comment="案号")
    dishonest_name = Column("dishonest_name", String(50), nullable=True, comment="失信人名称")
    gender = Column("gender", Integer(), nullable=True, comment="性别")
    age = Column("age", Integer(), nullable=True, comment="年龄")
    reg_no = Column("reg_no", String(50), nullable=True, comment="企业注册号")
    display_id_no = Column("display_id_no", String(50), nullable=True, comment="展示用证件号码")
    legal_person = Column("legal_person", String(50), nullable=True, comment="法定代表人或负责人")
    exec_court = Column("exec_court", String(50), nullable=True, comment="执行法院")
    province_id = Column("province_id", String(50), nullable=True, comment="省份id")
    province = Column("province", String(50), nullable=True, comment="省份")
    dishonest_type = Column("dishonest_type", Integer(), nullable=True, comment="失信人类型")
    exec_basis_no = Column("exec_basis_no", String(200), nullable=True, comment="执行依据文号")
    exec_basis_org = Column("exec_basis_org", String(50), nullable=True, comment="做出执行依据单位")
    legal_obligation = Column(
        "legal_obligation", Text(), nullable=True, comment="生效法律文书确定的义务"
    )
    fulfillment_status = Column(
        "fulfillment_status", String(50), nullable=True, comment="被执行人的履行情况"
    )
    dishonest_behavior = Column(
        "dishonest_behavior", String(50), nullable=True, comment="失信被执行人行为具体情形"
    )
    publish_date = Column("publish_date", String(50), nullable=True, comment="发布时间")
    filing_date = Column("filing_date", String(50), nullable=True, comment="立案时间")
    exec_part = Column("exec_part", String(50), nullable=True, comment="执行部分")
    unexec_part = Column("unexec_part", String(50), nullable=True, comment="未执行部分")
    is_history = Column("is_history", Integer(), nullable=True, comment="是否历史数据")
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标记")
    is_hidden = Column("is_hidden", Integer(), nullable=True, comment="是否不展示")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [dishonest_id]}


class DwdOrgRiskTaxPunish(Base):
    """前海数据机构税收违法"""

    __tablename__ = "dwd_org_risk_tax_punish"
    __table_args__ = {"comment": "前海数据机构税收违法"}

    taxpayer_name = Column("taxpayer_name", String(50), nullable=True, comment="纳税人名称")
    tax_vio_id = Column("tax_vio_id", String(50), nullable=True, comment="税收违法id")
    report_period = Column("report_period", String(50), nullable=True, comment="案件上报期")
    taxpayer_id = Column("taxpayer_id", String(50), nullable=True, comment="纳税人识别码")
    org_code = Column("org_code", String(50), nullable=True, comment="组织机构代码")
    reg_address = Column("reg_address", String(512), nullable=True, comment="注册地址")
    publish_date = Column("publish_date", String(50), nullable=True, comment="发布日期")
    legal_name = Column("legal_name", String(50), nullable=True, comment="法定代表人或者负责人姓名")
    legal_gender = Column(
        "legal_gender", String(50), nullable=True, comment="法定代表人或者负责人性别"
    )
    legal_id_type = Column(
        "legal_id_type", String(50), nullable=True, comment="法定代表人或者负责人证件类型"
    )
    legal_id_no = Column(
        "legal_id_no", String(50), nullable=True, comment="法定代表人或者负责人证件号码"
    )
    case_type = Column("case_type", String(256), nullable=True, comment="案件性质")
    illegal_fact = Column("illegal_fact", String(1000), nullable=True, comment="主要违法事实")
    punish_basis = Column(
        "punish_basis", String(1000), nullable=True, comment="相关法律依据及税务处理处罚情况"
    )
    tax_authority = Column("tax_authority", String(50), nullable=True, comment="所属税务机关")
    original_link = Column("original_link", String(256), nullable=True, comment="数据原始连接")
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标志")
    original_source = Column("original_source", String(50), nullable=True, comment="原始数据来源")
    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    is_history = Column("is_history", Integer(), nullable=True, comment="是否历史")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [taxpayer_name]}


class DwdOrgRiskXianxiao(Base):
    """前海机构限制高消费记录"""

    __tablename__ = "dwd_org_risk_xianxiao"
    __table_args__ = {"comment": "前海机构限制高消费记录"}

    xhfgk_id = Column("xhfgk_id", String(50), nullable=True, comment="限制高消费官网id")
    rhc_person_name = Column(
        "rhc_person_name", String(50), nullable=True, comment="限制高消费人员名称"
    )
    filing_date = Column("filing_date", String(50), nullable=True, comment="立案时间")
    case_no = Column("case_no", String(200), nullable=True, comment="案号")
    gender = Column("gender", String(50), nullable=True, comment="性别")
    company_info = Column("company_info", String(50), nullable=True, comment="企业信息")
    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    company_cert_no = Column("company_cert_no", String(50), nullable=True, comment="企业证件号")
    xhfgk_doc_url = Column(
        "xhfgk_doc_url", String(500), nullable=True, comment="限制高消费令文件url"
    )
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标记")
    is_history = Column("is_history", Integer(), nullable=True, comment="是否是历史限制高消费")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [xhfgk_id]}


class DwdOrgRiskZhixing(Base):
    """前海数据机构被执行人记录"""

    __tablename__ = "dwd_org_risk_zhixing"
    __table_args__ = {"comment": "前海数据机构被执行人记录"}

    exec_person_id = Column("exec_person_id", String(50), nullable=True, comment="唯一索引id")
    exec_person_type = Column("exec_person_type", Integer(), nullable=True, comment="被执行人类型")
    exec_person_name = Column("exec_person_name", String(50), nullable=True, comment="被执行人名称")
    gender = Column("gender", String(50), nullable=True, comment="性别")
    id_no = Column("id_no", String(50), nullable=True, comment="证件号码")
    exec_court = Column("exec_court", String(50), nullable=True, comment="执行法院")
    case_no = Column("case_no", String(200), nullable=True, comment="案号")
    exec_basis_no = Column("exec_basis_no", String(50), nullable=True, comment="执行依据文号")
    exec_status = Column("exec_status", String(50), nullable=True, comment="执行状态")
    exec_target = Column("exec_target", String(50), nullable=True, comment="执行标的")
    web_id = Column("web_id", String(50), nullable=True, comment="执行信息公开网id")
    filing_date = Column("filing_date", String(50), nullable=True, comment="立案时间")
    use_flag = Column("use_flag", Integer(), nullable=True, comment="使用标记")
    is_hidden = Column("is_hidden", Integer(), nullable=True, comment="是否不展示")
    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [exec_person_id]}


class DwdOrgRiskZhongben(Base):
    """终本案件表"""

    __tablename__ = "dwd_org_risk_zhongben"
    __table_args__ = {"comment": "终本案件表"}

    official_id = Column("official_id", String(255), nullable=True, comment="官网id")
    executed_person_name = Column(
        "executed_person_name", String(255), nullable=True, comment="被执行人姓名名称"
    )
    gender = Column("gender", String(255), nullable=True, comment="性别")
    case_no = Column("case_no", String(255), nullable=True, comment="案号")
    executed_person_type = Column(
        "executed_person_type", String(255), nullable=True, comment="被执行人类型"
    )
    id_no = Column("id_no", String(255), nullable=True, comment="证件号码")
    exec_court = Column("exec_court", String(255), nullable=True, comment="执行法院")
    filing_date = Column("filing_date", String(255), nullable=True, comment="立案日期")
    termination_date = Column("termination_date", String(255), nullable=True, comment="终本日期")
    address = Column("address", Text(), nullable=True, comment="地址")
    exec_target_amount = Column(
        "exec_target_amount", Numeric(20, 2), nullable=True, comment="执行标的金额"
    )
    unfulfilled_amount = Column(
        "unfulfilled_amount", Numeric(20, 2), nullable=True, comment="未履行标的金额"
    )
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源zxgk")
    data_use_flag = Column("data_use_flag", String(255), nullable=True, comment="数据使用标记")
    is_history = Column("is_history", String(255), nullable=True, comment="是否是历史数据")
    is_hidden = Column("is_hidden", String(255), nullable=True, comment="是否不展示")
    data_source2 = Column("data_source2", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [official_id]}


class DwdOrgShareholderInfo(Base):
    """前海数据机构股东信息"""

    __tablename__ = "dwd_org_shareholder_info"
    __table_args__ = {"comment": "前海数据机构股东信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    inv_org_id = Column("inv_org_id", String(50), nullable=True, comment="股东id")
    owners_name = Column("owners_name", String(50), nullable=True, comment="股东名称")
    owners_type = Column("owners_type", String(50), nullable=True, comment="股东类型")
    ownership_percentage = Column(
        "ownership_percentage", Float(), nullable=True, comment="所有权占比(%)"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgStockBase(Base):
    """前海数据上市企业基本信息"""

    __tablename__ = "dwd_org_stock_base"
    __table_args__ = {"comment": "前海数据上市企业基本信息"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    stock_code = Column("stock_code", String(50), nullable=True, comment="股票代码")
    stock_noun = Column("stock_noun", String(50), nullable=True, comment="股票简称")
    stock_type = Column("stock_type", String(50), nullable=True, comment="上市板块")
    listed_date = Column("listed_date", String(50), nullable=True, comment="上市日期")
    listed_status = Column("listed_status", String(50), nullable=True, comment="上市状态")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgStockFinanceInfo(Base):
    """前海数据上市企业主要财务指标"""

    __tablename__ = "dwd_org_stock_finance_info"
    __table_args__ = {"comment": "前海数据上市企业主要财务指标"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    stock_code = Column("stock_code", String(50), nullable=True, comment="股票代码")
    occur_period = Column("occur_period", String(50), nullable=True, comment="数据期")
    total_assets = Column("total_assets", Numeric(20, 2), nullable=True, comment="资产总额(元)")
    fixed_assets = Column("fixed_assets", Numeric(20, 2), nullable=True, comment="固定资产总额(元)")
    total_liabilities = Column(
        "total_liabilities", Numeric(20, 2), nullable=True, comment="负债总额(元)"
    )
    operating_revenue = Column(
        "operating_revenue", Numeric(20, 2), nullable=True, comment="营业收入(元)"
    )
    gross_revenue = Column("gross_revenue", Numeric(20, 2), nullable=True, comment="营业总收入(元)")
    main_business_revenue = Column(
        "main_business_revenue", Numeric(20, 2), nullable=True, comment="主营业务收入(元)"
    )
    total_profit = Column("total_profit", Numeric(20, 2), nullable=True, comment="利润总额(元)")
    pure_profit = Column("pure_profit", Numeric(20, 2), nullable=True, comment="净利润(元)")
    total_tax_paid = Column("total_tax_paid", Numeric(20, 2), nullable=True, comment="纳税总额(元)")
    oper_cash_flow = Column(
        "oper_cash_flow", Numeric(20, 2), nullable=True, comment="经营活动现金流(元)"
    )
    owners_equity = Column(
        "owners_equity", Numeric(20, 2), nullable=True, comment="所有者权益合计(元)"
    )
    employees_number = Column("employees_number", Integer(), nullable=True, comment="从业人数")
    research_development_amount = Column(
        "research_development_amount", Numeric(20, 2), nullable=True, comment="研发投入金额(元)"
    )
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgTagInfo(Base):
    """前海数据机构标签表"""

    __tablename__ = "dwd_org_tag_info"
    __table_args__ = {"comment": "前海数据机构标签表"}

    org_id = Column("org_id", String(50), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(50), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(50), nullable=True, comment="统一社会信用代码"
    )
    org_tag = Column("org_tag", String(50), nullable=True, comment="企业标签")
    tag_level = Column("tag_level", String(50), nullable=True, comment="级别")
    data_source = Column("data_source", String(50), nullable=True, comment="数据来源")
    created_time = Column("created_time", String(50), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [org_id]}


class DwdOrgTbJudicialSale(Base):
    """司法拍卖表"""

    __tablename__ = "dwd_org_tb_judicial_sale"
    __table_args__ = {"comment": "司法拍卖表"}

    notice_name = Column("notice_name", Text(), nullable=True, comment="公告名")
    asset_disposal_unit = Column(
        "asset_disposal_unit", String(255), nullable=True, comment="资产处置单位"
    )
    notice_time = Column("notice_time", String(255), nullable=True, comment="公告时间")
    notice_id = Column("notice_id", String(255), nullable=True, comment="公告id")
    source_website = Column("source_website", String(255), nullable=True, comment="来源网站")
    notice_content_path = Column(
        "notice_content_path", Text(), nullable=True, comment="公告内容存储路径"
    )
    auction_start_date = Column(
        "auction_start_date", String(255), nullable=True, comment="拍卖开始日期"
    )
    auction_end_date = Column(
        "auction_end_date", String(255), nullable=True, comment="拍卖截止日期"
    )
    original_link = Column("original_link", Text(), nullable=True, comment="原始链接")
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标志")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [notice_name]}


class DwdOrgTbJudicialSaleInfoCompany(Base):
    """司法拍卖当事人表"""

    __tablename__ = "dwd_org_tb_judicial_sale_info_company"
    __table_args__ = {"comment": "司法拍卖当事人表"}

    notice_id = Column("notice_id", String(255), nullable=True, comment="公告id")
    related_company = Column("related_company", String(255), nullable=True, comment="相关公司")
    org_id = Column("org_id", String(255), nullable=True, comment="机构id")
    name_cn = Column("name_cn", String(255), nullable=True, comment="机构名称")
    social_credit_code = Column(
        "social_credit_code", String(255), nullable=True, comment="统一社会信用代码"
    )
    use_flag = Column("use_flag", String(255), nullable=True, comment="使用标记")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [notice_id]}
