from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)

from db_model.base import Base


class DwdZhAuthor(Base):
    """深势-中文文献作者详情信息"""

    __tablename__ = "dwd_zh_author"
    __table_args__ = {"comment": "深势-中文文献作者详情信息"}

    id = Column("id", String(32), primary_key=True, nullable=False, comment="文献作者的唯一主键 id")
    paper_id = Column("paper_id", String(64), nullable=False, comment="文献记录的唯一主键标识。")
    en_name = Column("en_name", String(255), nullable=True, comment="文献作者的英文名称")
    zh_name = Column("zh_name", String(255), nullable=True, comment="文献作者中文名")
    affiliation = Column("affiliation", Text(), nullable=True, comment="文献作者地址")
    email = Column("email", Text(), nullable=True, comment="文献作者email")
    correspond = Column("correspond", SmallInteger(), nullable=True, comment="是否为通讯作者")


class DwdZhJournal(Base):
    """深势-中文期刊详情信息"""

    __tablename__ = "dwd_zh_journal"
    __table_args__ = {"comment": "深势-中文期刊详情信息"}

    id = Column(
        "id", BigInteger(), primary_key=True, nullable=False, comment="期刊记录的唯一标识。"
    )
    iscn = Column("iscn", String(16), nullable=True, comment="期刊的国内统一刊号。")
    issn = Column("issn", String(16), nullable=True, comment="期刊的国际标准连续出版物编号。")
    zh_name = Column("zh_name", String(1024), nullable=True, comment="期刊的中文名称。")
    en_name = Column("en_name", String(1024), nullable=True, comment="期刊的英文名称。")
    publication_type = Column(
        "publication_type", String(255), nullable=True, comment="出版物类别，例如期刊，会议等"
    )
    name_abbr = Column("name_abbr", String(255), nullable=True, comment="期刊名称的简称或缩写。")
    country = Column("country", String(255), nullable=True, comment="期刊所属或出版所在的国家。")
    zh_description = Column(
        "zh_description", Text(), nullable=True, comment="期刊的中文简介或说明。"
    )
    format = Column("format", String(63), nullable=True, comment="期刊的版面开本规格。")
    founding_time = Column(
        "founding_time", Integer(), nullable=True, comment="期刊首次创办或发行的时间。"
    )
    language_classify = Column(
        "language_classify", SmallInteger(), nullable=True, comment="期刊出版使用的语言类型。"
    )
    eissn = Column(
        "eissn", String(16), nullable=True, comment="期刊电子版的国际标准连续出版物编号。"
    )
    jn_official = Column("jn_official", Text(), nullable=True, comment="期刊官方网站地址。")
    postal_code = Column(
        "postal_code", String(32), nullable=True, comment="期刊邮政发行使用的代号。"
    )
    chief_editor = Column(
        "chief_editor", String(128), nullable=True, comment="期刊当前或记录中的主编信息。"
    )
    organizer = Column(
        "organizer", String(1024), nullable=True, comment="负责主办该期刊的单位名称。"
    )
    publisher_place = Column(
        "publisher_place", String(64), nullable=True, comment="期刊出版发行的地点。"
    )
    publication_cycle = Column(
        "publication_cycle", String(64), nullable=True, comment="期刊的出版频率或发行周期。"
    )
    award = Column("award", Text(), nullable=True, comment="期刊获得的奖项或荣誉信息。")
    cite_nums = Column(
        "cite_nums", Integer(), nullable=True, comment="期刊或文献的累计被引用次数。"
    )
    paper_nums = Column("paper_nums", Integer(), nullable=True, comment="期刊已发表论文的数量。")
    review = Column("review", SmallInteger(), nullable=True, comment="标识该期刊是否为综述类期刊。")
    annual_publication = Column(
        "annual_publication", Integer(), nullable=True, comment="期刊每年发表文章的数量。"
    )
    impact_factor = Column(
        "impact_factor", Numeric(20, 10), nullable=True, comment="期刊的影响因子指标。"
    )
    open_access = Column(
        "open_access", SmallInteger(), nullable=True, comment="标识期刊或论文是否为开放获取。"
    )
    scope = Column("scope", String(20), nullable=True, comment="期刊所属的大类学科领域。")
    scope_zone = Column("scope_zone", String(20), nullable=True, comment="期刊所属的细分学科领域。")
    warning = Column("warning", SmallInteger(), nullable=True, comment="标识期刊是否处于预警状态。")
    is_sci = Column("is_sci", SmallInteger(), nullable=True, comment="标识期刊是否被 SCI 收录。")
    sub_quartile = Column(
        "sub_quartile", SmallInteger(), nullable=True, comment="期刊在相关评价体系中的分区信息。"
    )
    classify_list = Column(
        "classify_list", Text(), nullable=True, comment="文献或期刊对应的学科分类编号。"
    )
    updated_time = Column(
        "updated_time", DateTime(), nullable=False, comment="该条数据最近一次更新的时间。"
    )


class DwdZhPaper(Base):
    """深势-中文论文详情信息"""

    __tablename__ = "dwd_zh_paper"
    __table_args__ = {"comment": "深势-中文论文详情信息"}

    id = Column(
        "id", String(64), primary_key=True, nullable=False, comment="文献记录的唯一主键标识。"
    )
    paper_type = Column(
        "paper_type", String(255), nullable=True, comment="文献所属出版物的章节名称，栏目等。"
    )
    publication_id = Column(
        "publication_id",
        BigInteger(),
        nullable=False,
        comment="关联出版物的id，用于获取期刊详情信息",
    )
    paper_url = Column("paper_url", Text(), nullable=True, comment="文献数据的原始来源地址。")
    doi = Column("doi", String(512), nullable=True, comment="论文的唯一标识编码。")
    cover_date_start = Column(
        "cover_date_start", String(255), nullable=True, comment="文献正式发表的日期。"
    )
    ch_name = Column("ch_name", String(1024), nullable=True, comment="文献的中文标题名称。")
    ch_abstract = Column("ch_abstract", Text(), nullable=True, comment="文献内容的中文摘要信息。")
    keywords = Column("keywords", Text(), nullable=True, comment="描述论文主题内容的关键词。")
    volume = Column("volume", String(128), nullable=True, comment="文献发表所在期刊的卷号。")
    issue = Column("issue", String(128), nullable=True, comment="文献发表所在期刊的期号。")
    first_page = Column(
        "first_page", String(255), nullable=True, comment="论文在期刊中的起始页码。"
    )
    last_page = Column("last_page", String(255), nullable=True, comment="论文在期刊中的结束页码。")
    reference_nums = Column(
        "reference_nums", Integer(), nullable=True, comment="论文参考文献的总数量。"
    )
    reference_content = Column(
        "reference_content", Text(), nullable=True, comment="论文所引用参考文献的具体内容。"
    )
    citation_nums = Column(
        "citation_nums", Integer(), nullable=True, comment="论文被其他文献引用的数量。"
    )
    citation_content = Column(
        "citation_content", Text(), nullable=True, comment="引用该论文的相关文献信息。"
    )
    relevant = Column(
        "relevant", Text(), nullable=True, comment="与当前文献内容或主题相关的文献信息。"
    )
    authors = Column("authors", Text(), nullable=True, comment="论文作者的结构化id列表。")


class OdsZhJournal(Base):
    """维普中文报告信息"""

    __tablename__ = "ods_zh_journal"
    __table_args__ = {"comment": "维普中文报告信息"}

    lngid = Column("lngid", String(50), nullable=True)
    media_c = Column("media_c", String(50), nullable=True)
    media_e = Column("media_e", String(50), nullable=True)
    gch = Column("gch", String(50), nullable=True)
    gch5 = Column("gch5", String(50), nullable=True)
    years = Column("years", Integer(), nullable=True)
    vol = Column("vol", Integer(), nullable=True)
    num = Column("num", Integer(), nullable=True)
    title_c = Column("title_c", Text(), nullable=True)
    title_e = Column("title_e", Text(), nullable=True)
    keyword_c = Column("keyword_c", Text(), nullable=True)
    keyword_e = Column("keyword_e", Text(), nullable=True)
    remark_c = Column("remark_c", Text(), nullable=True)
    remark_e = Column("remark_e", Text(), nullable=True)
    firstclass = Column("firstclass", String(50), nullable=True)
    class_ = Column("class", String(50), nullable=True)
    beginpage = Column("beginpage", String(50), nullable=True)
    endpage = Column("endpage", String(50), nullable=True)
    jumppage = Column("jumppage", String(50), nullable=True)
    pagecount = Column("pagecount", Integer(), nullable=True)
    firstwriter = Column("firstwriter", String(50), nullable=True)
    showwriter = Column("showwriter", Text(), nullable=True)
    firstorgan = Column("firstorgan", Text(), nullable=True)
    showorgan = Column("showorgan", Text(), nullable=True)
    showwriter_e = Column("showwriter_e", Text(), nullable=True)
    showorgan_e = Column("showorgan_e", Text(), nullable=True)
    author_e = Column("author_e", Text(), nullable=True)
    publishdate = Column("publishdate", Integer(), nullable=True)
    doi = Column("doi", String(50), nullable=True)
    intpdf = Column("intpdf", Integer(), nullable=True)
    pdfsize = Column("pdfsize", Integer(), nullable=True)
    range = Column("range", Text(), nullable=True)
    language = Column("language", Integer(), nullable=True)
    type = Column("type", Integer(), nullable=True)
    issn = Column("issn", String(50), nullable=True)
    cnno = Column("cnno", String(50), nullable=True)
    classtypes = Column("classtypes", Text(), nullable=True)
    showclasstypes = Column("showclasstypes", Text(), nullable=True)
    subject_edu = Column("subject_edu", String(50), nullable=True)
    corr_author = Column("corr_author", String(50), nullable=True)
    fulltextaddress = Column("fulltextaddress", Text(), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [lngid]}
