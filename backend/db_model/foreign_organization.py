from sqlalchemy import (
    Column,
    String,
    Text,
)

from db_model.base import Base


class DwdForgAggIdentifier(Base):
    """国外企业代码表"""
    __tablename__ = 'dwd_forg_agg_identifier'
    __table_args__ = {"comment": '国外企业代码表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    code_category = Column('code_category', String(100), nullable=True, comment='代码大类')
    code_subcategory = Column('code_subcategory', String(100), nullable=True, comment='代码小类')
    code_cn_name = Column('code_cn_name', String(255), nullable=True, comment='代码中文名称')
    code_name = Column('code_name', String(255), nullable=True, comment='代码名称')
    code_value = Column('code_value', String(255), nullable=True, comment='代码值')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgBaseInfo(Base):
    """国外企业基本信息表"""
    __tablename__ = 'dwd_forg_base_info'
    __table_args__ = {"comment": '国外企业基本信息表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    ename_local = Column('ename_local', String(500), nullable=True, comment='企业名称（本地语种）')
    ename_pv = Column('ename_pv', String(500), nullable=True, comment='曾用名')
    ipo_status = Column('ipo_status', String(50), nullable=True, comment='企业状态')
    employees_num = Column('employees_num', String(255), nullable=True, comment='员工人数')
    start_year = Column('start_year', String(50), nullable=True, comment='成立年份')
    start_date = Column('start_date', String(50), nullable=True, comment='成立日期')
    address = Column('address', String(255), nullable=True, comment='国家或地区')
    reg_city = Column('reg_city', String(255), nullable=True, comment='城市')
    address1 = Column('address1', String(255), nullable=True, comment='地址第1行')
    address2 = Column('address2', String(255), nullable=True, comment='地址第2行')
    address3 = Column('address3', String(255), nullable=True, comment='地址第3行')
    address4 = Column('address4', String(255), nullable=True, comment='地址第4行')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgBeneficiaryInfo(Base):
    """国外企业受益人表"""
    __tablename__ = 'dwd_forg_beneficiary_info'
    __table_args__ = {"comment": '国外企业受益人表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    bo_name = Column('bo_name', String(500), nullable=True, comment='受益人名称')
    bo_gender = Column('bo_gender', String(255), nullable=True, comment='受益人性别')
    bo_birthdate = Column('bo_birthdate', String(255), nullable=True, comment='受益人出生日期')
    bo_country_code = Column('bo_country_code', String(255), nullable=True, comment='受益人所在国家代码')
    bo_manager = Column('bo_manager', String(255), nullable=True, comment='受益人是否同时是管理层')
    path = Column('path', Text(), nullable=True, comment='路径')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgContact(Base):
    """国外企业联系方式表"""
    __tablename__ = 'dwd_forg_contact'
    __table_args__ = {"comment": '国外企业联系方式表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    phone = Column('phone', String(255), nullable=True, comment='电话')
    domain = Column('domain', String(255), nullable=True, comment='域名')
    website = Column('website', String(255), nullable=True, comment='网址')
    email = Column('email', String(255), nullable=True, comment='邮箱')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgExecutiveInfo(Base):
    """国外企业高管表"""
    __tablename__ = 'dwd_forg_executive_info'
    __table_args__ = {"comment": '国外企业高管表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    executives_name = Column('executives_name', String(500), nullable=True, comment='高管名称')
    dm_age = Column('dm_age', String(200), nullable=True, comment='高管年龄')
    dm_sex = Column('dm_sex', String(500), nullable=True, comment='高管性别')
    executives_position = Column('executives_position', String(500), nullable=True, comment='高管职位')
    dm_birthdate = Column('dm_birthdate', String(500), nullable=True, comment='高管出生日期')
    dm_nationalities = Column('dm_nationalities', String(500), nullable=True, comment='高管国籍')
    dm_biography = Column('dm_biography', Text(), nullable=True, comment='高管履历')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgIndustry(Base):
    """国外企业行业分类表"""
    __tablename__ = 'dwd_forg_industry'
    __table_args__ = {"comment": '国外企业行业分类表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    industry_type = Column('industry_type', String(255), nullable=True, comment='行业分类标准')
    industry_level = Column('industry_level', String(255), nullable=True, comment='行业分类层级')
    industry_code = Column('industry_code', String(255), nullable=True, comment='行业代码')
    industry_label_cn = Column('industry_label_cn', String(500), nullable=True, comment='行业描述')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgInvestment(Base):
    """国外企业子公司情况表"""
    __tablename__ = 'dwd_forg_investment'
    __table_args__ = {"comment": '国外企业子公司情况表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    invested_name = Column('invested_name', String(500), nullable=True, comment='子公司名称')
    invested_eid = Column('invested_eid', String(32), nullable=True, comment='子公司国家代码')
    direct_pct = Column('direct_pct', String(255), nullable=True, comment='直接持股比例（%）')
    total_pct = Column('total_pct', String(255), nullable=True, comment='总持股比例（%）')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgProfile(Base):
    """国外企业简介表"""
    __tablename__ = 'dwd_forg_profile'
    __table_args__ = {"comment": '国外企业简介表'}

    ename_en = Column('ename_en', String(1000), nullable=True, comment='企业英文名称')
    business_desc = Column('business_desc', String(2000), nullable=True, comment='业务简介')
    products_services = Column('products_services', String(2000), nullable=True, comment='主要产品与服务')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgShareholder(Base):
    """国外企业股东表"""
    __tablename__ = 'dwd_forg_shareholder'
    __table_args__ = {"comment": '国外企业股东表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    sh_name = Column('sh_name', String(255), nullable=True, comment='股东名称')
    sh_entity_type = Column('sh_entity_type', String(255), nullable=True, comment='股东类型')
    sh_country_code = Column('sh_country_code', String(255), nullable=True, comment='股东所在国家代码')
    sh_direct_pct = Column('sh_direct_pct', String(50), nullable=True, comment='股东直接持股比例（%）')
    sh_total_pct = Column('sh_total_pct', String(50), nullable=True, comment='股东总持股比例（%）')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}


class DwdForgUltimateControl(Base):
    """国外企业实控人表"""
    __tablename__ = 'dwd_forg_ultimate_control'
    __table_args__ = {"comment": '国外企业实控人表'}

    ename_en = Column('ename_en', String(500), nullable=True, comment='企业英文名称')
    entity_name = Column('entity_name', String(255), nullable=True, comment='实控人名称')
    entity_country_code = Column('entity_country_code', String(32), nullable=True, comment='实控人国家代码')
    direct_pct = Column('direct_pct', String(255), nullable=True, comment='实控人直接持股比例（%）')
    total_pct = Column('total_pct', String(255), nullable=True, comment='实控人总持股比例（%）')

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [ename_en]}
