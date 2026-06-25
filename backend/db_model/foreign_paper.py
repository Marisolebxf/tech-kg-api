from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)

from db_model.base import Base


class DwdEnAuthor(Base):
    """深势-英文文献作者详情信息"""
    __tablename__ = 'dwd_en_author'
    __table_args__ = {"comment": '深势-英文文献作者详情信息'}

    id = Column('id', String(32), primary_key=True, nullable=False, comment='文献作者的唯一主键 id')
    paper_id = Column('paper_id', String(64), nullable=False, comment='文献记录的唯一主键标识。')
    en_name = Column('en_name', String(255), nullable=False, comment='文献作者的英文名称')
    zh_name = Column('zh_name', String(255), nullable=True, comment='文献作者中文名')
    affiliation = Column('affiliation', Text(), nullable=True, comment='文献作者地址')
    email = Column('email', Text(), nullable=True, comment='文献作者email')
    correspond = Column('correspond', SmallInteger(), nullable=True, comment='是否为通讯作者。否=0，是=1，未知=Null')


class DwdEnJournal(Base):
    """深势-英文期刊详情信息"""
    __tablename__ = 'dwd_en_journal'
    __table_args__ = {"comment": '深势-英文期刊详情信息'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='期刊、会议或预印本记录的唯一标识。')
    issn = Column('issn', String(16), nullable=True, comment='期刊的国际标准连续出版物编号。')
    zh_name = Column('zh_name', String(1024), nullable=True, comment='期刊、顶会或预印本平台的中文名称。')
    en_name = Column('en_name', String(1024), nullable=True, comment='期刊、顶会或预印本平台的英文名称。')
    name_abbr = Column('name_abbr', String(255), nullable=True, comment='期刊、会议或预印本名称的简称或缩写。')
    publication_type = Column('publication_type', String(255), nullable=True, comment='标识出版载体的类型，如期刊、会议或预印本等。journal，conference')
    en_description = Column('en_description', Text(), nullable=True, comment='期刊、会议或预印本平台的英文简介或说明。')
    establish_time = Column('establish_time', Integer(), nullable=True, comment='期刊首次创办或发行的时间。')
    language = Column('language', String(255), nullable=True, comment='文献或期刊出版使用的语言类型。')
    country = Column('country', String(255), nullable=True, comment='期刊、会议或出版机构所属的国家或地区。')
    eissn = Column('eissn', String(16), nullable=True, comment='期刊电子版的国际标准连续出版物编号。')
    annual_publication = Column('annual_publication', Integer(), nullable=True, comment='期刊或会议每年发表文章的数量。')
    review = Column('review', SmallInteger(), nullable=True, comment='标识该期刊是否为综述类期刊。否=0，是=1，未知=2')
    impact_factor = Column('impact_factor', Numeric(20, 10), nullable=True, comment='期刊或会议的影响力评价指标。')
    jcr_zone = Column('jcr_zone', String(2), nullable=True, comment='期刊在 JCR 等评价体系中的分区信息。Q1,Q2,Q3,Q4')
    open_access = Column('open_access', SmallInteger(), nullable=True, comment='标识期刊或论文是否为开放获取。否=0，是=1，未知=2')
    review_period = Column('review_period', String(255), nullable=True, comment='期刊从投稿到审稿完成的平均周期。')
    scope = Column('scope', String(20), nullable=True, comment='期刊或会议所属的大类学科领域。')
    sub_scope = Column('sub_scope', String(20), nullable=True, comment='期刊或会议所属的细分学科主题。')
    self_rate = Column('self_rate', Numeric(20, 10), nullable=True, comment='期刊文献中自我引用所占的比例。')
    top = Column('top', SmallInteger(), nullable=True, comment='标识期刊或会议是否为所在领域的顶级刊物。否=0，是=1')
    warning = Column('warning', SmallInteger(), nullable=True, comment='标识期刊是否处于预警状态。否=0，是=1，未知=Null')
    is_sci = Column('is_sci', SmallInteger(), nullable=True, comment='标识期刊是否被 SCI 收录。否=0，是=1，未知=Null')
    publish_period = Column('publish_period', String(64), nullable=True, comment='期刊的出版频率或发行周期。')
    jn_official = Column('jn_official', Text(), nullable=True, comment='期刊官方网站地址。')
    layout_cost = Column('layout_cost', String(15), nullable=True, comment='期刊发表论文所需的版面费用。')
    paper_nums = Column('paper_nums', Integer(), nullable=True, comment='期刊、会议或平台已发表论文的数量。')
    updated_time = Column('updated_time', DateTime(), nullable=False, comment='该条数据最近一次更新的时间。')


class DwdEnPaper(Base):
    """深势-英文论文详情信息"""
    __tablename__ = 'dwd_en_paper'
    __table_args__ = {"comment": '深势-英文论文详情信息'}

    id = Column('id', String(64), primary_key=True, nullable=False, comment='文献记录的唯一主键标识。')
    publisher = Column('publisher', String(1024), nullable=True, comment='文献或期刊所属的出版商信息。')
    publication_id = Column('publication_id', BigInteger(), nullable=False, comment='关联出版物的id，用于获取期刊详情信息')
    paper_type = Column('paper_type', String(255), nullable=True, comment='文献所属出版物的章节名称，栏目等。')
    paper_url = Column('paper_url', Text(), nullable=True, comment='文献在官网或来源平台中的访问链接。')
    doi = Column('doi', String(512), nullable=False, comment='论文的唯一标识编码。')
    cover_date_start = Column('cover_date_start', String(255), nullable=True, comment='文献正式发表的时间。')
    funds = Column('funds', Text(), nullable=True, comment='支持该论文研究的基金或资助项目信息。')
    en_name = Column('en_name', String(1024), nullable=True, comment='文献的英文标题名称。')
    en_abstract = Column('en_abstract', Text(), nullable=True, comment='文献内容的英文摘要信息。')
    keywords = Column('keywords', Text(), nullable=True, comment='描述论文主题内容的关键词。')
    volume = Column('volume', String(128), nullable=True, comment='文献发表所在期刊的卷号。')
    issue = Column('issue', String(128), nullable=True, comment='文献发表所在期刊的期号。')
    first_page = Column('first_page', String(255), nullable=True, comment='论文在期刊中的起始页码。')
    last_page = Column('last_page', String(255), nullable=True, comment='论文在期刊中的结束页码。')
    reference_nums = Column('reference_nums', Integer(), nullable=True, comment='论文参考文献的总数量。')
    reference_content = Column('reference_content', Text(), nullable=True, comment='论文所引用参考文献的具体内容。')
    citation_nums = Column('citation_nums', Integer(), nullable=True, comment='论文被其他文献引用的数量。')
    citation_content = Column('citation_content', Text(), nullable=True, comment='引用该论文的相关文献信息。')
    relevant = Column('relevant', Text(), nullable=True, comment='与当前文献内容或主题相关的文献信息。')
    authors = Column('authors', Text(), nullable=True, comment='论文作者的结构化id列表。')


class DwdEnPaperCitedBy(Base):
    """爱思唯尔外文论文引用关系表"""
    __tablename__ = 'dwd_en_paper_cited_by'
    __table_args__ = {"comment": '爱思唯尔外文论文引用关系表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='主键ID')
    paper_eid = Column('paper_eid', String(64), nullable=False, comment='被引文献EID（指向dwd_paper_info_qh.eid）')
    citing_eid = Column('citing_eid', String(64), nullable=False, comment='引用文献EID')
    citing_year = Column('citing_year', Integer(), nullable=True, comment='引用文献发表年份')
    create_time = Column('create_time', DateTime(), nullable=True, comment='记录创建时间')


class DwdEnPaperInfo(Base):
    """爱思唯尔外文文献基础信息"""
    __tablename__ = 'dwd_en_paper_info'
    __table_args__ = {"comment": '爱思唯尔外文文献基础信息'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='自增主键ID')
    eid = Column('eid', String(64), nullable=False, comment='Scopus文献唯一标识')
    doi = Column('doi', String(128), nullable=True, comment='文献数字对象唯一标识符')
    online_status = Column('online_status', String(32), nullable=True, comment='文献在线状态')
    pui = Column('pui', String(64), nullable=True, comment='出版商唯一标识')
    sdfullavail = Column('sdfullavail', SmallInteger(), nullable=True, comment='全文可获取状态，0-不可获取，1-可获取')
    issn = Column('issn', String(32), nullable=True, comment='期刊国际标准刊号')
    volume = Column('volume', String(16), nullable=True, comment='期刊卷号')
    issue = Column('issue', String(16), nullable=True, comment='期刊期号')
    first_page = Column('first_page', String(16), nullable=True, comment='文献起始页码')
    last_page = Column('last_page', String(16), nullable=True, comment='文献结束页码')
    sort_year = Column('sort_year', Integer(), nullable=True, comment='数据排序年份')
    sort_yyyymm = Column('sort_yyyymm', String(8), nullable=True, comment='数据排序年月')
    pub_year = Column('pub_year', Integer(), nullable=True, comment='文献正式出版年份')
    timestamp = Column('timestamp', DateTime(), nullable=True, comment='文献数据更新时间戳')
    orig_load_date = Column('orig_load_date', Date(), nullable=True, comment='数据原始入库日期')
    datesort = Column('datesort', String(16), nullable=True, comment='日期排序字符串')
    indexeddate = Column('indexeddate', DateTime(), nullable=True, comment='Scopus索引收录时间')
    absavail = Column('absavail', SmallInteger(), nullable=True, comment='摘要可获取状态，0-不可获取，1-可获取')
    suppressdummy = Column('suppressdummy', String(16), nullable=True, comment='是否隐藏虚拟数据')
    srctype = Column('srctype', String(1), nullable=True, comment='文献来源类型，j-期刊')
    subj_area = Column('subj_area', String(255), nullable=True, comment='文献所属学科领域，多学科逗号分隔')
    srctitle = Column('srctitle', String(512), nullable=True, comment='期刊来源全称')
    country = Column('country', String(64), nullable=True, comment='文献所属国家')
    language = Column('language', String(64), nullable=True, comment='文献语种')
    is_open_access = Column('is_open_access', SmallInteger(), nullable=True, comment='是否开放获取，0-否，1-是')
    oa_article_status = Column('oa_article_status', String(64), nullable=True, comment='开放获取状态描述')
    doctype = Column('doctype', String(16), nullable=True, comment='文献文档类型')
    group_id = Column('group_id', String(64), nullable=True, comment='文献分组ID')
    author_count = Column('author_count', Integer(), nullable=True, comment='文献作者总数量')
    author_list = Column('author_list', Text(), nullable=True, comment='作者完整信息列表，多作者分号分隔，含姓名、职称、作者ID等')
    author_surname = Column('author_surname', String(64), nullable=True, comment='第一作者姓氏')
    author_initials = Column('author_initials', String(32), nullable=True, comment='第一作者首字母缩写')
    author_id = Column('author_id', String(64), nullable=True, comment='作者唯一标识')
    title = Column('title', String(1024), nullable=True, comment='文献中文/英文标题')
    source_id = Column('source_id', String(64), nullable=True, comment='期刊来源唯一ID')
    source_title_abbrev = Column('source_title_abbrev', String(512), nullable=True, comment='期刊来源简称')
    asjc_code = Column('asjc_code', String(255), nullable=True, comment='ASJC学科分类编码，多编码逗号分隔')
    cited_by_count = Column('cited_by_count', Integer(), nullable=True, comment='被引用次数')
    create_time = Column('create_time', DateTime(), nullable=True, comment='数据入库时间')


class OdsEnJournal(Base):
    """万方外文期刊信息"""
    __tablename__ = 'ods_en_journal'
    __table_args__ = {"comment": '万方外文期刊信息'}

    F_ID = Column('F_ID', String(50), nullable=True)
    F_PaperID = Column('F_PaperID', Text(), nullable=True)
    F_Title = Column('F_Title', Text(), nullable=True)
    F_title_alternative = Column('F_title_alternative', Text(), nullable=True)
    F_abbrev_title = Column('F_abbrev_title', Text(), nullable=True)
    F_author = Column('F_author', Text(), nullable=True)
    F_author_alternative = Column('F_author_alternative', Text(), nullable=True)
    F_affiliation = Column('F_affiliation', Text(), nullable=True)
    F_affiliation_alternative = Column('F_affiliation_alternative', Text(), nullable=True)
    F_Abstract = Column('F_Abstract', Text(), nullable=True)
    F_Abstract_alternative = Column('F_Abstract_alternative', Text(), nullable=True)
    F_Keyword = Column('F_Keyword', Text(), nullable=True)
    F_Keyword_alternative = Column('F_Keyword_alternative', Text(), nullable=True)
    F_Language = Column('F_Language', Text(), nullable=True)
    F_Other_language = Column('F_Other_language', Text(), nullable=True)
    F_year = Column('F_year', String(10), nullable=True)
    F_volume = Column('F_volume', String(10), nullable=True)
    F_issue = Column('F_issue', String(10), nullable=True)
    F_Paper_type = Column('F_Paper_type', String(50), nullable=True)
    F_Classification = Column('F_Classification', Text(), nullable=True)
    F_DOI = Column('F_DOI', String(50), nullable=True)
    F_Start_page = Column('F_Start_page', String(10), nullable=True)
    F_End_page = Column('F_End_page', String(10), nullable=True)
    F_page = Column('F_page', String(50), nullable=True)
    F_Total_page_number = Column('F_Total_page_number', String(10), nullable=True)
    F_Journal = Column('F_Journal', Text(), nullable=True)
    F_Journal_alternative = Column('F_Journal_alternative', Text(), nullable=True)
    F_journal_abbrev = Column('F_journal_abbrev', Text(), nullable=True)
    F_journal_id = Column('F_journal_id', Text(), nullable=True)
    F_ISSNp = Column('F_ISSNp', String(50), nullable=True)
    F_ISSNe = Column('F_ISSNe', String(50), nullable=True)
    F_DateReceived = Column('F_DateReceived', String(50), nullable=True)
    F_DateSubmitted = Column('F_DateSubmitted', String(50), nullable=True)
    F_DatePublish = Column('F_DatePublish', String(50), nullable=True)
    F_DateRevision = Column('F_DateRevision', String(50), nullable=True)
    F_Updatedtime = Column('F_Updatedtime', String(50), nullable=True)
    F_Content = Column('F_Content', Text(), nullable=True)
    F_Subject = Column('F_Subject', Text(), nullable=True)
    F_column = Column('F_column', Text(), nullable=True)
    F_column_alternative = Column('F_column_alternative', Text(), nullable=True)
    F_AbstractUrl = Column('F_AbstractUrl', Text(), nullable=True)
    F_FulltextUrl = Column('F_FulltextUrl', Text(), nullable=True)
    F_PaperUrlContent = Column('F_PaperUrlContent', Text(), nullable=True)
    F_issue_url = Column('F_issue_url', Text(), nullable=True)
    F_journal_url = Column('F_journal_url', Text(), nullable=True)
    yn_free = Column('yn_free', Text(), nullable=True)
    F_Fund = Column('F_Fund', Text(), nullable=True)
    F_Fundid = Column('F_Fundid', Text(), nullable=True)
    F_Fundaffiliation = Column('F_Fundaffiliation', Text(), nullable=True)
    F_refrences = Column('F_refrences', Text(), nullable=True)
    F_publiser = Column('F_publiser', Text(), nullable=True)
    F_batchid = Column('F_batchid', Text(), nullable=True)
    F_article_id = Column('F_article_id', Text(), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [F_ID]}
