from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    SmallInteger,
    String,
)

from db_model.base import Base


class DwdAuthorAffiliation(Base):
    """作者-机构关联表"""
    __tablename__ = 'dwd_author_affiliation'
    __table_args__ = {"comment": '作者-机构关联表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='主键ID')
    auid = Column('auid', BigInteger(), nullable=False, comment='作者ID')
    affiliation_id = Column('affiliation_id', BigInteger(), nullable=True, comment='机构ID')
    afid = Column('afid', BigInteger(), nullable=True, comment='机构显示ID')
    affiliation_id_parent = Column('affiliation_id_parent', BigInteger(), nullable=True, comment='父机构ID')
    preferred_name = Column('preferred_name', String(500), nullable=True, comment='机构标准名称')
    afdispname = Column('afdispname', String(500), nullable=True, comment='机构显示名称')
    sort_name = Column('sort_name', String(500), nullable=True, comment='机构排序名称')
    address_part = Column('address_part', String(500), nullable=True, comment='详细地址')
    city = Column('city', String(100), nullable=True, comment='城市')
    state = Column('state', String(100), nullable=True, comment='州/省份')
    country = Column('country', String(100), nullable=True, comment='国家')
    country_tag = Column('country_tag', String(32), nullable=True, comment='国家编码')
    postal_code = Column('postal_code', String(64), nullable=True, comment='邮政编码')
    type_afid = Column('type_afid', String(32), nullable=True, comment='机构类型：dept/parent')
    relationship = Column('relationship', String(32), nullable=True, comment='关系：author/derived')
    create_time = Column('create_time', DateTime(), nullable=True, comment='入库时间')


class DwdAuthorInfo(Base):
    """Scopus作者元数据表"""
    __tablename__ = 'dwd_author_info'
    __table_args__ = {"comment": 'Scopus作者元数据表'}

    id = Column('id', BigInteger(), primary_key=True, nullable=False, comment='主键ID')
    auid = Column('auid', BigInteger(), nullable=False, comment='作者唯一ID')
    orcid = Column('orcid', String(64), nullable=True, comment='ORCID 标识')
    orcid_matching_type = Column('orcid_matching_type', String(64), nullable=True, comment='ORCID匹配类型')
    given_name = Column('given_name', String(255), nullable=True, comment='名')
    surname = Column('surname', String(255), nullable=True, comment='姓')
    indexed_name = Column('indexed_name', String(255), nullable=True, comment='索引名称')
    initials = Column('initials', String(32), nullable=True, comment='姓名缩写')
    alias_status = Column('alias_status', String(32), nullable=True, comment='别名状态')
    name_variants = Column('name_variants', String(500), nullable=True, comment='姓名别名列表（逗号分隔）')
    history_ids = Column('history_ids', String(500), nullable=True, comment='历史ID列表（逗号分隔）')
    email = Column('email', String(255), nullable=True, comment='邮箱')
    email_type = Column('email_type', String(32), nullable=True, comment='邮箱类型')
    asjc_list = Column('asjc_list', String(500), nullable=True, comment='ASJC学科代码列表，逗号分隔')
    asjc_freq_list = Column('asjc_freq_list', String(500), nullable=True, comment='ASJC频次列表，逗号分隔')
    subjabbr_list = Column('subjabbr_list', String(500), nullable=True, comment='学科缩写列表，逗号分隔')
    subjabbr_freq_list = Column('subjabbr_freq_list', String(500), nullable=True, comment='学科缩写频次，逗号分隔')
    n_affiliation_current = Column('n_affiliation_current', Integer(), nullable=True, comment='当前机构数量')
    current_affiliations = Column('current_affiliations', String(500), nullable=True, comment='当前有效机构ID列表，逗号分隔')
    current_affiliations_parent = Column('current_affiliations_parent', String(500), nullable=True, comment='父机构ID列表，逗号分隔')
    corrupt_xml = Column('corrupt_xml', SmallInteger(), nullable=True, comment='XML文件是否损坏（1=损坏，0=正常）')
    xmlsize = Column('xmlsize', Integer(), nullable=True, comment='XML文件大小')
    datetime_max = Column('datetime_max', String(32), nullable=True, comment='数据最新日期')
    suppress = Column('suppress', SmallInteger(), nullable=True, comment='是否隐藏')
    type = Column('type', String(32), nullable=True, comment='作者类型')
    curated = Column('curated', SmallInteger(), nullable=True, comment='是否经过人工校准')
    curtype = Column('curtype', String(255), nullable=True, comment='校准类型')
    cur_source = Column('cur_source', String(255), nullable=True, comment='校准来源')
    cur_timestamp = Column('cur_timestamp', String(255), nullable=True, comment='校准时间戳')
    create_time = Column('create_time', DateTime(), nullable=True, comment='入库时间')
