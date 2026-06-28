from sqlalchemy import BigInteger, Column, DateTime, SmallInteger, String, Text

from db_model.base import Base


class DwdScholar(Base):
    __tablename__ = "dwd_scholar"

    scholar_id = Column(String(32), primary_key=True, comment="学者记录的业务唯一标识")
    name_en = Column(String(128), comment="学者的英文姓名")
    name_zh = Column(String(128), comment="学者的中文姓名")
    avatar = Column(String(256), comment="学者头像图片的访问链接")
    scholar_org_name_en = Column(String(4096), comment="学者所属机构的英文名称")
    scholar_org_name_zh = Column(String(1024), comment="学者所属机构的中文名称")
    bio = Column(Text, comment="学者的个人或学术简介信息")
    bio_zh = Column(Text, comment="学者的中文个人或学术简介信息")
    work_experience_en = Column(Text, comment="学者英文工作经历信息")
    work_experience_zh = Column(Text, comment="学者中文工作经历信息")
    education_background_en = Column(Text, comment="学者的英文教育经历信息")
    education_background_zh = Column(Text, comment="学者的中文教育经历信息")
    paper_nums = Column(BigInteger, comment="学者已发表论文的数量")
    citation_nums = Column(BigInteger, comment="学者论文被引用的总次数")
    h_index = Column(BigInteger, comment="衡量学者学术影响力的 H 指数")
    status = Column(SmallInteger, comment="记录状态，0 表示无效，1 表示有效")
    create_time = Column(DateTime, comment="记录创建时间")
    update_time = Column(DateTime, comment="记录最后更新时间")


class DwdScholarTalentFlag(Base):
    __tablename__ = "dwd_scholar_talent_flag"

    scholar_id = Column(String(32), primary_key=True, comment="关联学者记录的业务唯一标识")
    academician = Column(String(128), comment="标识学者是否为院士")
    create_time = Column(DateTime, comment="记录创建时间")
    update_time = Column(DateTime, comment="记录最后更新时间")


class DwdScholarResearchDirection(Base):
    __tablename__ = "dwd_scholar_research_direction"

    scholar_id = Column(String(32), primary_key=True, comment="关联学者记录的业务唯一标识")
    fields = Column(Text, comment="学者研究方向")
    create_time = Column(DateTime, comment="记录创建时间")
    update_time = Column(DateTime, comment="记录最后更新时间")


class DwdScholarPaperRelation(Base):
    __tablename__ = "dwd_scholar_paper_relation"

    paper_id = Column(BigInteger, primary_key=True, comment="论文记录的唯一标识")
    year = Column(BigInteger, comment="论文发表年份")
    scholar_id = Column(String(32), comment="学者记录的业务唯一标识")
    citations = Column(BigInteger, comment="论文被引用次数")
    publish_time = Column(String(10), comment="论文发布时间")
    status = Column(SmallInteger, comment="记录状态，0 表示无效，1 表示有效")
    create_time = Column(DateTime, comment="记录创建时间")
    update_time = Column(DateTime, comment="记录最后更新时间")
    publication_id = Column(BigInteger, comment="期刊或会议记录的唯一标识")
    related_paper_id = Column(BigInteger, comment="关联论文库的唯一标识")


class DwdScholarPapers(Base):
    __tablename__ = "dwd_scholar_papers"

    doi = Column(String(512), primary_key=True, comment="论文的 DOI 唯一识别号")
    zh_name = Column(String(500), comment="论文的中文标题名称")
    en_name = Column(String(500), comment="论文的英文标题名称")
    authors = Column(Text, comment="论文作者的姓名或信息列表")
    paper_url = Column(String(1024), comment="论文原始来源页面的访问链接")
    cover_date_start = Column(String(10), comment="论文正式发表或出版的时间")
    create_time = Column(DateTime, comment="记录创建时间")
    update_time = Column(DateTime, comment="记录最后更新时间")
    status = Column(SmallInteger, comment="记录状态，0 表示无效，1 表示有效")
    zh_abstract = Column(Text, comment="论文内容的中文摘要信息")
    en_abstract = Column(Text, comment="论文内容的英文摘要信息")
    publication_en_name = Column(String(1024), comment="论文发表所在期刊或会议的英文名称")


class DwdScholarCoauthor(Base):
    __tablename__ = "dwd_scholar_coauthor"

    scholar_id = Column(String(32), primary_key=True, comment="当前学者记录的业务唯一标识")
    co_scholar_id = Column(String(32), primary_key=True, comment="合作学者记录的业务唯一标识")
    co_scholar_name_en = Column(String(256), comment="合作学者的英文姓名")
    co_scholar_name_zh = Column(String(128), comment="合作学者的中文姓名")
    co_scholar_avatar = Column(String(512), comment="合作学者头像图片的访问链接")
    co_scholar_org_name_en = Column(String(2048), comment="合作学者所属机构的英文名称")
    co_scholar_org_name_zh = Column(String(1024), comment="合作学者所属机构的中文名称")
    co_paper_count = Column(BigInteger, comment="与该学者合作发表的论文数量")
    status = Column(SmallInteger, comment="记录状态，0 表示无效，1 表示有效")
    create_time = Column(DateTime, comment="记录创建时间")
    update_time = Column(DateTime, comment="记录最后更新时间")


class Scholar(Base):
    """techkg 本地 scholar 表（真实业务学者，如 COOP-SCH001 陈建国）。"""

    __tablename__ = "scholar"

    scholar_id = Column(String(32), primary_key=True, comment="学者唯一标识")
    name_zh = Column(String(128), comment="中文姓名")
    name_en = Column(String(128), comment="英文姓名")
    org_name_zh = Column(String(1024), comment="所属机构中文名称")
    title = Column(String(64), comment="职称")
    gender = Column(String(8), comment="性别")
    research_direction = Column(Text, comment="研究方向")
    paper_nums = Column(BigInteger, comment="论文数")
    citation_nums = Column(BigInteger, comment="被引次数")
    h_index = Column(BigInteger, comment="H 指数")
    updated_at = Column(DateTime, comment="更新时间")
