from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
)

from db_model.base import Base


class DwdScholar(Base):
    """深势-学者表"""
    __tablename__ = 'dwd_scholar'
    __table_args__ = {"comment": '深势-学者表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='主键')
    scholar_id = Column('scholar_id', String(32), nullable=False, comment='学者id')
    name_en = Column('name_en', String(128), nullable=False, comment='英文姓名')
    name_zh = Column('name_zh', String(128), nullable=False, comment='中文姓名')
    avatar = Column('avatar', String(256), nullable=False, comment='头像')
    scholar_org_name_en = Column('scholar_org_name_en', Text(), nullable=True, comment='英文机构')
    scholar_org_name_zh = Column('scholar_org_name_zh', String(1024), nullable=True, comment='中文机构')
    scholar_org_id = Column('scholar_org_id', String(64), nullable=True, comment='所属机构id，学者所属机构id')
    bio = Column('bio', Text(), nullable=True, comment='个人简介/学术简介，学者的个人或学术简介信息')
    bio_zh = Column('bio_zh', Text(), nullable=True, comment='个人简介/学术简介（中文），学者的中文个人或学术简介信息')
    work_experience_en = Column('work_experience_en', Text(), nullable=True, comment='工作经历英文（包含机构和职务）')
    work_experience_zh = Column('work_experience_zh', Text(), nullable=True, comment='工作经历中文（包含机构和职务）')
    education_background_en = Column('education_background_en', Text(), nullable=True, comment='教育背景（英文），学者的英文教育经历信息')
    education_background_zh = Column('education_background_zh', Text(), nullable=True, comment='教育背景（中文），学者的中文教育经历信息')
    paper_nums = Column('paper_nums', Integer(), nullable=False, comment='论文数量')
    citation_nums = Column('citation_nums', Integer(), nullable=False, comment='被引数量')
    h_index = Column('h_index', Integer(), nullable=False, comment='H指数')
    status = Column('status', Integer(), nullable=False, comment='状态：0:无效,1:有效')
    create_time = Column('create_time', DateTime(), nullable=False, comment='创建时间')
    update_time = Column('update_time', DateTime(), nullable=False, comment='记录最后更新时间')


class DwdScholarCoauthor(Base):
    """深势-学者合作者关系表"""
    __tablename__ = 'dwd_scholar_coauthor'
    __table_args__ = {"comment": '深势-学者合作者关系表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='自增主键ID')
    scholar_id = Column('scholar_id', String(32), nullable=False, comment='学者ID，当前学者记录的业务唯一标识')
    co_scholar_id = Column('co_scholar_id', String(32), nullable=False, comment='合作学者ID，合作学者记录的业务唯一标识')
    co_scholar_name_en = Column('co_scholar_name_en', String(256), nullable=True, comment='合作学者英文名')
    co_scholar_name_zh = Column('co_scholar_name_zh', String(128), nullable=True, comment='合作学者中文名')
    co_scholar_avatar = Column('co_scholar_avatar', String(512), nullable=True, comment='合作学者头像URL')
    co_scholar_org_name_en = Column('co_scholar_org_name_en', Text(), nullable=True, comment='合作学者所属机构英文名')
    co_scholar_org_name_zh = Column('co_scholar_org_name_zh', String(1024), nullable=True, comment='合作学者所属机构中文名')
    co_scholar_org_id = Column('co_scholar_org_id', String(64), nullable=True, comment='合作学者所属机构ID')
    co_paper_count = Column('co_paper_count', Integer(), nullable=False, comment='合作论文数量')
    status = Column('status', Integer(), nullable=False, comment='状态：0:无效,1:有效')
    create_time = Column('create_time', DateTime(), nullable=False, comment='记录创建时间')
    update_time = Column('update_time', DateTime(), nullable=False, comment='记录最后更新时间')


class DwdScholarPaperRelation(Base):
    """深势-学者论文关系表"""
    __tablename__ = 'dwd_scholar_paper_relation'
    __table_args__ = {"comment": '深势-学者论文关系表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='主键')
    paper_id = Column('paper_id', BigInteger(), nullable=False, comment='论文id')
    related_paper_id = Column('related_paper_id', BigInteger(), nullable=True, comment='关联论文库的唯一标识')
    year = Column('year', BigInteger(), nullable=False, comment='论文发表年份')
    scholar_id = Column('scholar_id', String(32), nullable=False, comment='学者id')
    citations = Column('citations', Integer(), nullable=False, comment='被引用次数')
    publish_time = Column('publish_time', DateTime(), nullable=True, comment='发布时间')
    status = Column('status', Integer(), nullable=False, comment='状态：0:无效,1:有效')
    create_time = Column('create_time', DateTime(), nullable=False, comment='创建时间')
    update_time = Column('update_time', DateTime(), nullable=False, comment='记录最后更新时间')
    publication_id = Column('publication_id', BigInteger(), nullable=False, comment='期刊id')


class DwdScholarPapers(Base):
    """深势-论文信息表"""
    __tablename__ = 'dwd_scholar_papers'
    __table_args__ = {"comment": '深势-论文信息表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False)
    zh_name = Column('zh_name', String(500), nullable=False, comment='中文题目')
    en_name = Column('en_name', String(500), nullable=False, comment='英文题目')
    authors = Column('authors', Text(), nullable=True, comment='作者列表')
    paper_url = Column('paper_url', String(1024), nullable=False, comment='论文原始链接')
    cover_date_start = Column('cover_date_start', DateTime(), nullable=True, comment='发表时间')
    create_time = Column('create_time', DateTime(), nullable=True, comment='创建时间')
    update_time = Column('update_time', DateTime(), nullable=True, comment='记录最后更新时间')
    status = Column('status', SmallInteger(), nullable=True, comment='状态：0:无效,1:有效')
    zh_abstract = Column('zh_abstract', Text(), nullable=True, comment='中文摘要')
    en_abstract = Column('en_abstract', Text(), nullable=True, comment='英文摘要')
    doi = Column('doi', String(512), nullable=False)
    publication_en_name = Column('publication_en_name', String(1024), nullable=False)


class DwdScholarResearchDirection(Base):
    """深势-学者研究方向表"""
    __tablename__ = 'dwd_scholar_research_direction'
    __table_args__ = {"comment": '深势-学者研究方向表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='逻辑ID')
    scholar_id = Column('scholar_id', String(32), nullable=False, comment='学者ID')
    fields = Column('fields', Text(), nullable=True, comment='研究方向')
    create_time = Column('create_time', DateTime(), nullable=False, comment='创建时间')
    update_time = Column('update_time', DateTime(), nullable=False, comment='记录最后更新时间')


class DwdScholarTalentFlag(Base):
    """深势-学者人才标签表"""
    __tablename__ = 'dwd_scholar_talent_flag'
    __table_args__ = {"comment": '深势-学者人才标签表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='逻辑ID')
    scholar_id = Column('scholar_id', String(32), nullable=False, comment='学者ID')
    academician = Column('academician', Integer(), nullable=False, comment='是否为院士：0:否,1:是')
    create_time = Column('create_time', DateTime(), nullable=False, comment='创建时间')
    update_time = Column('update_time', DateTime(), nullable=False, comment='记录最后更新时间')
