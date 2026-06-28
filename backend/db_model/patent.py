from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import JSON

from db_model.base import Base


class OdsPatent(Base):
    """深势-专利信息表"""

    __tablename__ = "ods_patent"
    __table_args__ = {"comment": "深势-专利信息表"}

    id = Column(
        "id", String(20), primary_key=True, nullable=False, comment="专利公布号(与DOCDB兼容)"
    )
    publication_number = Column(
        "publication_number", String(20), nullable=True, comment="专利公布号"
    )
    pct_publication_number = Column(
        "pct_publication_number", String(20), nullable=True, comment="pct公开号"
    )
    application_number = Column(
        "application_number", String(20), nullable=True, comment="专利申请号"
    )
    country_code = Column("country_code", String(2), nullable=True, comment="国家代码")
    kind_code = Column("kind_code", String(2), nullable=True, comment="种类代码")
    application_kind = Column("application_kind", String(1), nullable=True, comment="应用程序类型")
    application_number_formatted = Column(
        "application_number_formatted", String(20), nullable=True, comment="格式化的申请号"
    )
    pct_number = Column("pct_number", String(17), nullable=True, comment="PCT编号")
    family_id = Column("family_id", String(8), nullable=True, comment="家庭ID")
    spif_publication_number = Column(
        "spif_publication_number", String(20), nullable=True, comment="SPIF标准发布编号"
    )
    spif_application_number = Column(
        "spif_application_number", String(20), nullable=True, comment="SPIF标准申请号"
    )
    title_localized = Column("title_localized", Text(), nullable=True, comment="标题")
    abstract_localized = Column("abstract_localized", Text(), nullable=True, comment="摘要")
    claims_localized = Column("claims_localized", Text(), nullable=True, comment="权利要求")
    claims_localized_html = Column(
        "claims_localized_html", Text(), nullable=True, comment="权利要求html"
    )
    description_localized = Column("description_localized", Text(), nullable=True, comment="说明书")
    description_localized_html = Column(
        "description_localized_html", Text(), nullable=True, comment="说明书html"
    )
    publication_year = Column("publication_year", Integer(), nullable=True, comment="发布年份")
    filing_year = Column("filing_year", Integer(), nullable=True, comment="申请年份")
    grant_year = Column("grant_year", Integer(), nullable=True, comment="授予年份")
    priority_year = Column("priority_year", Integer(), nullable=True, comment="优先权年")
    expiration_year = Column("expiration_year", Integer(), nullable=True, comment="失效年")
    citation_nums = Column("citation_nums", Integer(), nullable=True, comment="专利引用数量")
    cited_by_nums = Column("cited_by_nums", Integer(), nullable=True, comment="专利施引数量")
    publication_date = Column("publication_date", Date(), nullable=True, comment="发布日期")
    filing_date = Column("filing_date", Date(), nullable=True, comment="申请日期")
    grant_date = Column("grant_date", Date(), nullable=True, comment="授予日期")
    priority_date = Column("priority_date", Date(), nullable=True, comment="优先权日")
    priority_claim = Column("priority_claim", Text(), nullable=True, comment="本出版物")
    inventor = Column("inventor", Text(), nullable=True, comment="发明人")
    inventor_harmonized = Column("inventor_harmonized", Text(), nullable=True, comment="发明者信息")
    assignee = Column("assignee", Text(), nullable=True, comment="受让人/申请人")
    current_assignee = Column(
        "current_assignee", Text(), nullable=True, comment="当前受让人/申请人"
    )
    assignee_harmonized = Column(
        "assignee_harmonized", Text(), nullable=True, comment="受让人/申请人信息"
    )
    examiner = Column("examiner", Text(), nullable=True, comment="审查员信息")
    uspc = Column("uspc", Text(), nullable=True, comment="美国专利")
    ipc = Column("ipc", Text(), nullable=True, comment="国际专利分类")
    cpc = Column("cpc", Text(), nullable=True, comment="合作专利分类")
    fi = Column("fi", Text(), nullable=True, comment="FI分类")
    fterm = Column("fterm", Text(), nullable=True, comment="fterm分类")
    locarno = Column("locarno", Text(), nullable=True, comment="Locarno分类")
    citation = Column("citation", Text(), nullable=True, comment="出版物引用")
    parent = Column("parent", Text(), nullable=True, comment="父申请")
    child = Column("child", Text(), nullable=True, comment="子申请")
    entity_status = Column(
        "entity_status", String(7), nullable=True, comment="美国专利商标局实体状态"
    )
    art_unit = Column("art_unit", String(4), nullable=True, comment="美国专利商标局艺术单位")
    status = Column("status", String(55), nullable=True, comment="专利状态")
    figures = Column("figures", Text(), nullable=True, comment="专利图")
    pdf_url = Column("pdf_url", Text(), nullable=True, comment="专利文件链接")
    patent_citations = Column("patent_citations", Text(), nullable=True, comment="专利引用")
    family_citations = Column("family_citations", Text(), nullable=True, comment="家族内引用")
    cited_by = Column("cited_by", Text(), nullable=True, comment="被引用")
    cited_by_family = Column("cited_by_family", Text(), nullable=True, comment="家庭内被引用")
    events = Column("events", Text(), nullable=True, comment="事件")
    non_patent_citations = Column(
        "non_patent_citations", Text(), nullable=True, comment="非专利引用"
    )
    legal_events = Column("legal_events", Text(), nullable=True, comment="法律事件")
    anticipated_expiration = Column(
        "anticipated_expiration", Date(), nullable=True, comment="预计到期日"
    )
    language = Column("language", String(10), nullable=True, comment="原文语言")
    relevants = Column("relevants", Text(), nullable=True, comment="相关专利")
    priority_filings = Column("priority_filings", Text(), nullable=True, comment="优先权信息")
    precis_graph = Column("precis_graph", Text(), nullable=True, comment="摘要图AI生成OSS链接")
    targets = Column("targets", Text(), nullable=True, comment="靶点")
    keywords = Column("keywords", Text(), nullable=True, comment="关键词")
    concepts = Column("concepts", Text(), nullable=True, comment="概念")
    definitions = Column("definitions", Text(), nullable=True, comment="定义")
    worldwides = Column("worldwides", Text(), nullable=True, comment="全球专利")
    docdb_family = Column("docdb_family", Text(), nullable=True, comment="家族专利")
    prior_art_date = Column("prior_art_date", Date(), nullable=True, comment="Prior art date")
    prior_art_year = Column("prior_art_year", Integer(), nullable=True, comment="Prior art year")
    country = Column("country", String(50), nullable=True, comment="国家")
    other_versions = Column("other_versions", Text(), nullable=True, comment="其他版本")
    external_links = Column("external_links", Text(), nullable=True, comment="外部链接")
    landscapes = Column("landscapes", Text(), nullable=True, comment="技术领域分类")
    dwpi_basic = Column(
        "dwpi_basic",
        String(20),
        nullable=True,
        comment="DWPI基本专利，指第一个输入到DWPI数据库的同族专利成员",
    )
    dwpi_family = Column("dwpi_family", Text(), nullable=True, comment="DWPI同族公开号")
    main_family = Column("main_family", Text(), nullable=True, comment="同族专利公开号")
    complete_family = Column("complete_family", Text(), nullable=True, comment="拓展同族公开号")
    legal_status = Column("legal_status", Text(), nullable=True, comment="法律状态")
    transferor = Column("transferor", Text(), nullable=True, comment="转让人")
    transfer_count = Column("transfer_count", Integer(), nullable=True, comment="转让次数")
    transfer_price = Column("transfer_price", Text(), nullable=True, comment="转让价格")
    transfer_record = Column("transfer_record", Text(), nullable=True, comment="转让时间序列")
    license_type = Column(
        "license_type",
        Integer(),
        nullable=True,
        comment="许可类型，如独占许可、排他许可、普通许可等许可方式",
    )
    license_country = Column(
        "license_country", Text(), nullable=True, comment="许可地国家，专利许可在哪些国家或地区有效"
    )
    license_price = Column("license_price", Text(), nullable=True, comment="许可费用")
    examination_detail = Column("examination_detail", Text(), nullable=True, comment="审察详细信息")
    technical_abstract = Column("technical_abstract", Text(), nullable=True, comment="技术摘要")
    page_count = Column("page_count", Integer(), nullable=True, comment="文献页数")
    subject_classification = Column(
        "subject_classification", Text(), nullable=True, comment="学科分类"
    )
    dwpi_classification = Column("dwpi_classification", Text(), nullable=True, comment="DWPI分类")
    dwpi_title = Column("dwpi_title", Text(), nullable=True, comment="DWPI标题")
    dwpi_priority_number = Column(
        "dwpi_priority_number", String(20), nullable=True, comment="DWPI优先权号"
    )
    dwpi_priority_country = Column(
        "dwpi_priority_country", String(2), nullable=True, comment="DWPI优先权国别"
    )
    dwpi_assignee = Column("dwpi_assignee", Text(), nullable=True, comment="DWPI专利权人")
    dwpi_inventor = Column("dwpi_inventor", Text(), nullable=True, comment="DWPI发明人")
    inpadoc_family_id = Column(
        "inpadoc_family_id", String(8), nullable=True, comment="INPADOC同族编号"
    )
    independent_claims_localized = Column(
        "independent_claims_localized", Text(), nullable=True, comment="独立权利要求"
    )
    independent_claims_localized_html = Column(
        "independent_claims_localized_html", Text(), nullable=True, comment="独立权利要求html"
    )
    problem_sum = Column("problem_sum", Text(), nullable=True, comment="技术问题")
    method_sum = Column("method_sum", Text(), nullable=True, comment="技术手段")
    benefit_sum = Column("benefit_sum", Text(), nullable=True, comment="技术功效")
    current_assignee_harmonized = Column(
        "current_assignee_harmonized", Text(), nullable=True, comment="当前受让人/申请人信息"
    )
    current_inventor = Column("current_inventor", Text(), nullable=True, comment="当前发明人")
    current_inventor_harmonized = Column(
        "current_inventor_harmonized", Text(), nullable=True, comment="当前发明者信息"
    )
    agent = Column("agent", Text(), nullable=True, comment="代理人")
    current_agent = Column("current_agent", Text(), nullable=True, comment="当前代理人")
    agency = Column("agency", Text(), nullable=True, comment="代理机构")
    current_agency = Column("current_agency", Text(), nullable=True, comment="当前代理机构")
    assistant_examiner = Column(
        "assistant_examiner", Text(), nullable=True, comment="助理审查员信息"
    )
    priority_country = Column(
        "priority_country", String(2), nullable=True, comment="优先权国家/地区"
    )
    epds = Column("epds", String(2), nullable=True, comment="EP指定国家/地区")
    business_information = Column("business_information", Text(), nullable=True, comment="工商信息")
    first_publication_date = Column(
        "first_publication_date", Date(), nullable=True, comment="首次公开日"
    )
    examine_date = Column("examine_date", Date(), nullable=True, comment="实质审查生效日")
    pct_entry_date = Column("pct_entry_date", Date(), nullable=True, comment="PCT进入国家阶段日")
    legal_status_date = Column("legal_status_date", Date(), nullable=True, comment="法律状态更新日")
    earliest_priority_date = Column(
        "earliest_priority_date", Date(), nullable=True, comment="最早优先权日"
    )
    gbc = Column("gbc", Text(), nullable=True, comment="国民经济行业分类号")
    adc = Column("adc", Text(), nullable=True, comment="应用领域分类")
    ttc = Column("ttc", Text(), nullable=True, comment="技术主题分类")
    seic = Column("seic", Text(), nullable=True, comment="战略新兴产业分类")
    cite_category = Column("cite_category", String(3), nullable=True, comment="引用类别")
    epds_count = Column("epds_count", Integer(), nullable=True, comment="EP指定国家/地区数量")
    up_status = Column("up_status", Integer(), nullable=True, comment="欧洲统一法院状态")
    epds_legal_status = Column(
        "epds_legal_status", Integer(), nullable=True, comment="EP指定国家/地区法律状态"
    )
    patent_value = Column("patent_value", Integer(), nullable=True, comment="专利价值(美元)")
    gov = Column("gov", Text(), nullable=True, comment="政府利益")
    examine_period = Column("examine_period", Integer(), nullable=True, comment="审查时长")
    sep = Column("sep", Text(), nullable=True, comment="标准专利")
    award = Column("award", Text(), nullable=True, comment="奖励")
    sub_case = Column("sub_case", Text(), nullable=True, comment="分案")
    priority_country_count = Column(
        "priority_country_count", Integer(), nullable=True, comment="优先权国家/地区个数"
    )
    case_number = Column("case_number", Text(), nullable=True, comment="案件号")
    court = Column("court", Text(), nullable=True, comment="审查法院")
    judge = Column("judge", Text(), nullable=True, comment="审判员")
    chief_judge = Column("chief_judge", Text(), nullable=True, comment="审判长")
    plaintiff = Column("plaintiff", Text(), nullable=True, comment="原告")
    defendant = Column("defendant", Text(), nullable=True, comment="被告")
    case_filing_date = Column("case_filing_date", Date(), nullable=True, comment="立案日期")
    verdict_date = Column("verdict_date", Date(), nullable=True, comment="裁判日期")
    hearing_date = Column("hearing_date", Date(), nullable=True, comment="听证日期")
    trial_grade = Column("trial_grade", Text(), nullable=True, comment="审理程序")
    case = Column("case", Text(), nullable=True, comment="案件")
    case_close_date = Column("case_close_date", Date(), nullable=True, comment="结案日期")
    outcome = Column("outcome", Text(), nullable=True, comment="案件结果")
    litigation_count = Column("litigation_count", Integer(), nullable=True, comment="诉讼次数")
    case_doc_type = Column("case_doc_type", Integer(), nullable=True, comment="文书类型")
    court_grade = Column("court_grade", String(4), nullable=True, comment="法院级别")
    verdict = Column("verdict", Text(), nullable=True, comment="判决结果")
    party = Column("party", Text(), nullable=True, comment="当事人")
    amount_plaintiff = Column("amount_plaintiff", Integer(), nullable=True, comment="申请赔偿总额")
    damages_amount = Column("damages_amount", Integer(), nullable=True, comment="判赔总额")
    case_filing_year = Column("case_filing_year", Integer(), nullable=True, comment="立案年份")
    litigation_product = Column("litigation_product", Text(), nullable=True, comment="涉及产品")
    licensor = Column("licensor", Text(), nullable=True, comment="许可人")
    licensee = Column("licensee", Text(), nullable=True, comment="被许可人")
    license_number = Column("license_number", Text(), nullable=True, comment="许可合同备案号")
    exclusivity = Column("exclusivity", Text(), nullable=True, comment="许可排他性")
    license_effective_date = Column(
        "license_effective_date", Date(), nullable=True, comment="许可生效日"
    )
    license_count = Column("license_count", Integer(), nullable=True, comment="许可次数")
    transfer = Column("transfer", Text(), nullable=True, comment="权利转移")
    review_invalid_applicant = Column(
        "review_invalid_applicant", Text(), nullable=True, comment="复审/无效请求人"
    )
    review_invalid_decision_number = Column(
        "review_invalid_decision_number", Text(), nullable=True, comment="决定号"
    )
    review_invalid_commission_number = Column(
        "review_invalid_commission_number", Text(), nullable=True, comment="委内编号"
    )
    review_invalid_decision_date = Column(
        "review_invalid_decision_date", Date(), nullable=True, comment="决定/发文日"
    )
    review_invalid_decision_type = Column(
        "review_invalid_decision_type", Text(), nullable=True, comment="决定类型"
    )
    review_invalid_decision = Column(
        "review_invalid_decision", Text(), nullable=True, comment="决定"
    )
    review_invalid_decision_point = Column(
        "review_invalid_decision_point", Text(), nullable=True, comment="决定要点"
    )
    review_invalid_decision_case_mainpoint = Column(
        "review_invalid_decision_case_mainpoint", Text(), nullable=True, comment="案由"
    )
    review_invalid_legal_basis = Column(
        "review_invalid_legal_basis", Text(), nullable=True, comment="法律依据"
    )
    review_invalid_fulltext = Column(
        "review_invalid_fulltext", Text(), nullable=True, comment="复审/无效全文"
    )
    invalid_count = Column("invalid_count", Integer(), nullable=True, comment="无效次数")
    pledgor = Column("pledgor", Text(), nullable=True, comment="质押人")
    pledgee = Column("pledgee", Text(), nullable=True, comment="质权人")
    pledgeno = Column("pledgeno", Text(), nullable=True, comment="质押登记号")
    pledge = Column("pledge", Text(), nullable=True, comment="质押信息")
    summarize = Column("summarize", Text(), nullable=True, comment="总结")
    spare_zero = Column("spare_zero", Text(), nullable=True, comment="备用0")
    spare_one = Column("spare_one", Text(), nullable=True, comment="备用1")
    spare_two = Column("spare_two", Text(), nullable=True, comment="备用2")
    spare_three = Column("spare_three", Text(), nullable=True, comment="备用3")
    spare_four = Column("spare_four", Text(), nullable=True, comment="备用4")
    spare_five = Column("spare_five", Text(), nullable=True, comment="备用5")
    spare_six = Column("spare_six", Text(), nullable=True, comment="备用6")
    spare_seven = Column("spare_seven", Text(), nullable=True, comment="备用7")
    spare_eight = Column("spare_eight", String(1024), nullable=True, comment="备用8")
    spare_nine = Column("spare_nine", String(1024), nullable=True, comment="备用9")
    spare_ten = Column("spare_ten", String(1024), nullable=True, comment="备用10")
    state = Column("state", SmallInteger(), nullable=True, comment="逻辑删除(1:存在，0:不存在)")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")


class OdsPatentBiblio(Base):
    """全球专利-著录项目"""

    __tablename__ = "ods_patent_Biblio_"
    __table_args__ = {"comment": "全球专利-著录项目"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    exdt = Column("exdt", Integer(), nullable=True, comment="智慧芽专利预估到期日")
    parties = Column("parties", Text(), nullable=True, comment="当事人信息(申请人、发明人等)")
    abstracts = Column("abstracts", Text(), nullable=True, comment="摘要信息")
    patent_type = Column("patent_type", String(20), nullable=True, comment="专利类型")
    invention_title = Column("invention_title", Text(), nullable=True, comment="标题信息")
    priority_claims = Column("priority_claims", Text(), nullable=True, comment="优先权信息")
    reference_cited = Column("reference_cited", Text(), nullable=True, comment="应用专利信息")
    related_documents = Column(
        "related_documents", Text(), nullable=True, comment="分案申请、继续申请信息"
    )
    classification_data = Column("classification_data", Text(), nullable=True, comment="分类数据")
    application_reference = Column(
        "application_reference", Text(), nullable=True, comment="申请信息"
    )
    publication_reference = Column(
        "publication_reference", Text(), nullable=True, comment="公开信息"
    )
    pct_or_regional_filing_data = Column(
        "pct_or_regional_filing_data", Text(), nullable=True, comment="PCT申请信息"
    )
    dates_of_public_availability = Column(
        "dates_of_public_availability", Text(), nullable=True, comment="授权信息"
    )
    pct_or_regional_publishing_data = Column(
        "pct_or_regional_publishing_data", Text(), nullable=True, comment="PCT公开信息"
    )


class OdsPatentCited(Base):
    """全球专利-专利被引用"""

    __tablename__ = "ods_patent_Cited"
    __table_args__ = {"comment": "全球专利-专利被引用"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    patent_cited = Column("patent_cited", Text(), nullable=True, comment="被引用详情")


class OdsPatentClaims(Base):
    """全球专利-权利要求"""

    __tablename__ = "ods_patent_Claims"
    __table_args__ = {"comment": "全球专利-权利要求"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    claims = Column("claims", Text(), nullable=True, comment="权利要求信息")
    claim_count = Column("claim_count", Integer(), nullable=True, comment="权利要求统计")


class OdsPatentDescription(Base):
    """全球专利-说明书"""

    __tablename__ = "ods_patent_Description"
    __table_args__ = {"comment": "全球专利-说明书"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    description = Column("description", Text(), nullable=True, comment="说明书信息")


class OdsPatentDrawing(Base):
    """全球专利-摘要附图"""

    __tablename__ = "ods_patent_Drawing"
    __table_args__ = {"comment": "全球专利-摘要附图"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    abstract_drawing = Column("abstract_drawing", Text(), nullable=True, comment="摘要附图信息")


class OdsPatentFamily(Base):
    """全球专利-专利家族"""

    __tablename__ = "ods_patent_Family"
    __table_args__ = {"comment": "全球专利-专利家族"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    patent_family = Column("patent_family", Text(), nullable=True, comment="专利家族信息")


class OdsPatentLegalStatus(Base):
    """全球专利-法律状态"""

    __tablename__ = "ods_patent_LegalStatus"
    __table_args__ = {"comment": "全球专利-法律状态"}

    patent_id = Column(
        "patent_id", String(20), primary_key=True, nullable=False, comment="专利主键ID"
    )
    pn = Column("pn", String(32), nullable=False, comment="专利公开(公告)号")
    legal_date = Column("legal_date", String(20), nullable=True, comment="法定日期")
    patent_legal = Column("patent_legal", Text(), nullable=True, comment="法律状态详情")


class OdsPatentWeipu(Base):
    """维普专利信息"""

    __tablename__ = "ods_patent_weipu"
    __table_args__ = {"comment": "维普专利信息"}

    lngid = Column("lngid", String(50), nullable=True)
    media_c = Column("media_c", String(50), nullable=True)
    years = Column("years", Integer(), nullable=True)
    title_c = Column("title_c", Text(), nullable=True)
    title_e = Column("title_e", Text(), nullable=True)
    keyword_c = Column("keyword_c", Text(), nullable=True)
    keyword_e = Column("keyword_e", Text(), nullable=True)
    remark_c = Column("remark_c", Text(), nullable=True)
    remark_e = Column("remark_e", Text(), nullable=True)
    class_ = Column("class", String(50), nullable=True)
    firstclass = Column("firstclass", String(50), nullable=True)
    beginpage = Column("beginpage", String(50), nullable=True)
    endpage = Column("endpage", String(50), nullable=True)
    jumppage = Column("jumppage", String(50), nullable=True)
    pagecount = Column("pagecount", Integer(), nullable=True)
    showwriter = Column("showwriter", String(512), nullable=True)
    author_e = Column("author_e", String(512), nullable=True)
    showorgan = Column("showorgan", String(512), nullable=True)
    intpdf = Column("intpdf", Integer(), nullable=True)
    country = Column("country", String(50), nullable=True)
    language = Column("language", Integer(), nullable=True)
    type = Column("type", Integer(), nullable=True)
    classtypes = Column("classtypes", String(512), nullable=True)
    showclasstypes = Column("showclasstypes", String(512), nullable=True)
    fulltextaddress = Column("fulltextaddress", Text(), nullable=True)
    zlmaintype = Column("zlmaintype", String(50), nullable=True)
    zlapplicantaddr = Column("zlapplicantaddr", Text(), nullable=True)
    zlprovincecode = Column("zlprovincecode", String(50), nullable=True)
    zlapplicationnum = Column("zlapplicationnum", String(50), nullable=True)
    zlapplicationdata = Column("zlapplicationdata", Integer(), nullable=True)
    zlopendata = Column("zlopendata", Integer(), nullable=True)
    zlpriority = Column("zlpriority", Text(), nullable=True)
    zlprioritynumber = Column("zlprioritynumber", String(50), nullable=True)
    zlmainclassnum = Column("zlmainclassnum", String(50), nullable=True)
    zlclassnum = Column("zlclassnum", String(128), nullable=True)
    zlinternationalpub = Column("zlinternationalpub", String(50), nullable=True)
    zlinternationalapp = Column("zlinternationalapp", String(50), nullable=True)
    zlcomeindata = Column("zlcomeindata", Integer(), nullable=True)
    zlsovereignty = Column("zlsovereignty", Text(), nullable=True)
    zlagents = Column("zlagents", String(50), nullable=True)
    zlagency = Column("zlagency", String(256), nullable=True)
    zllegalstatus = Column("zllegalstatus", String(512), nullable=True)
    zlthesissize = Column("zlthesissize", Integer(), nullable=True)
    zlaccdate = Column("zlaccdate", Integer(), nullable=True)
    zlpatentstate = Column("zlpatentstate", String(512), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [lngid]}


class DwdPatent(Base):
    __tablename__ = "dwd_patent"

    patent_id = Column(String(64), primary_key=True, comment="专利记录唯一标识")
    publication_number = Column(String(64), nullable=False, comment="专利公布号")
    application_kind = Column(String(2), comment="专利申请类型代码")
    country_code = Column(String(2), comment="国家、地区或组织代码")
    country = Column(String(20), comment="专利所属或发布的国家名称")
    publication_reference = Column(JSON, comment="发布文献种类代码、发布日期、年份和年月")
    application_reference = Column(JSON, comment="申请号、受理局代码、申请日期、年份和年月")
    pct_or_regional_filing_data = Column(JSON, comment="PCT 申请号和申请日期")
    pct_or_regional_publishing_data = Column(JSON, comment="PCT 公布号和公布日期")
    priority_filings = Column(JSON, comment="优先权信息对象数组")
    applicants = Column(JSON, comment="原始申请人对象数组")
    assignees = Column(JSON, comment="当前申请人或专利权人对象数组")
    inventors = Column(JSON, comment="发明人对象数组")
    first_applicant_name = Column(String(255), comment="第一原始申请人")
    first_current_assignee_name = Column(String(255), comment="第一当前申请人或专利权人")
    first_inventor_name = Column(String(255), comment="第一发明人")
    classification_ipcr = Column(JSON, comment="IPCR/IPC 主分类号和附加分类号")
    classification_cpc = Column(JSON, comment="CPC 主分类号和附加分类号")
    keywords = Column(Text, comment="描述专利主题内容的关键词")
    claims_localized = Column(Text, comment="专利权利要求书的文本内容")
    description_localized = Column(Text, comment="专利说明书的正文内容")
    figures = Column(Text, comment="专利附图或图示相关信息")
    language = Column(String(16), comment="专利原始文本使用的语言")
    granted_number = Column(String(64), comment="专利授权编号")
    spif_application_number = Column(String(64), comment="SPIF 标准申请号")
    spif_publication_number = Column(String(64), comment="SPIF 标准公布号")
    prior_art_year = Column(String(4), comment="相关现有技术对应的年份")
    prior_art_date = Column(String(10), comment="相关现有技术对应的日期")
    relevants = Column(Text, comment="相关专利信息")
    db_source = Column(String(64), nullable=False, comment="数据来源贴源库")
    create_time = Column(DateTime, nullable=False, comment="记录创建时间")
    update_time = Column(DateTime, nullable=False, comment="记录最近更新时间")
    citation_nums = Column(BigInteger, comment="引用专利数量")
    patent_citations = Column(JSON, comment="引用专利对象数组")
    cited_by_nums = Column(BigInteger, comment="被引专利数量")
    cited_by = Column(JSON, comment="被引专利对象数组")
    non_patent_citations_nums = Column(BigInteger, comment="非专利文献引用数量")
    non_patent_citations = Column(JSON, comment="非专利文献引用对象数组")
    dates_of_public_availability = Column(JSON, comment="授权日期、年份和年月")
    status = Column(String(10), comment="专利当前法律状态")
    anticipated_expiration = Column(String(10), comment="预计到期日")
    expiration_year = Column(String(10), comment="预计或实际到期年份")
    family_citations = Column(Text, comment="家族内引用信息")
    cited_by_family = Column(Text, comment="家族内被引用信息")
    other_versions = Column(Text, comment="其他公开、公告或授权版本")
    worldwides = Column(Text, comment="全球同族专利信息")
    simple_family = Column(JSON, comment="简单同族成员文献号")


class DwdPatentTitle(Base):
    __tablename__ = "dwd_patent_title"

    patent_id = Column(String(64), primary_key=True, comment="关联专利唯一标识")
    title_localized = Column(JSON, comment="原文标题和英文标题")
    db_source = Column(String(64), nullable=False, comment="数据来源贴源库")
    create_time = Column(DateTime, nullable=False, comment="记录创建时间")
    update_time = Column(DateTime, nullable=False, comment="记录最近更新时间")


class DwdPatentAbstract(Base):
    __tablename__ = "dwd_patent_abstract"

    patent_id = Column(String(64), primary_key=True, comment="关联专利唯一标识")
    abstract_localized = Column(JSON, comment="原文摘要和英文摘要")
    db_source = Column(String(64), nullable=False, comment="数据来源贴源库")
    create_time = Column(DateTime, nullable=False, comment="记录创建时间")
    update_time = Column(DateTime, nullable=False, comment="记录最近更新时间")


class DwdPatentLegal(Base):
    __tablename__ = "dwd_patent_legal"

    patent_id = Column(String(64), primary_key=True, comment="关联专利唯一标识")
    legal_events = Column(Text, comment="专利生命周期中的法律状态变更事件")
    prs_data = Column("patent_legal/prs_data", JSON, comment="PRS 事件日期、代码和法律状态分类说明")
    db_source = Column(String(64), nullable=False, comment="数据来源贴源库")
    create_time = Column(DateTime, nullable=False, comment="记录创建时间")
    update_time = Column(DateTime, nullable=False, comment="记录最近更新时间")


class DwdPatentFamily(Base):
    __tablename__ = "dwd_patent_family"

    patent_id = Column(String(64), primary_key=True, comment="关联专利唯一标识")
    simple_family = Column(JSON, comment="专利家族 ID、成员国家代码和文献种类代码")
    db_source = Column(String(64), nullable=False, comment="数据来源贴源库")
    create_time = Column(DateTime, nullable=False, comment="记录创建时间")
    update_time = Column(DateTime, nullable=False, comment="记录最近更新时间")
