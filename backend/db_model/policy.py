from sqlalchemy import (
    Column,
    String,
    Text,
)

from db_model.base import Base


class OdsEnPolicy(Base):
    """拓尔思国外政策信息"""

    __tablename__ = "ods_en_policy"
    __table_args__ = {"comment": "拓尔思国外政策信息"}

    IR_URLTITLE = Column("IR_URLTITLE", String(256), nullable=True)
    SY_URLTITLE = Column("SY_URLTITLE", String(256), nullable=True)
    FY_URLTITLE = Column("FY_URLTITLE", String(256), nullable=True)
    IR_URLTIME = Column("IR_URLTIME", String(50), nullable=True)
    IR_SITENAME = Column("IR_SITENAME", String(50), nullable=True)
    SY_MEDIA_PRODUCT_NAME = Column("SY_MEDIA_PRODUCT_NAME", String(50), nullable=True)
    IR_CONTENT = Column("IR_CONTENT", Text(), nullable=True)
    SY_CONTENT = Column("SY_CONTENT", Text(), nullable=True)
    FY_CONTENT = Column("FY_CONTENT", Text(), nullable=True)
    IR_ABSTRACT = Column("IR_ABSTRACT", Text(), nullable=True)
    SY_ABSTRACT = Column("SY_ABSTRACT", Text(), nullable=True)
    IR_URLNAME = Column("IR_URLNAME", String(1024), nullable=True)
    IR_URLDATE = Column("IR_URLDATE", String(50), nullable=True)
    IR_ATTACHMENT = Column("IR_ATTACHMENT", String(1024), nullable=True)
    IR_AUTHORS = Column("IR_AUTHORS", String(256), nullable=True)
    IR_CHANNEL = Column("IR_CHANNEL", String(256), nullable=True)
    IR_LANGUAGE = Column("IR_LANGUAGE", String(50), nullable=True)
    IR_URLCONTENT = Column("IR_URLCONTENT", Text(), nullable=True)
    SY_AREA_LIST = Column("SY_AREA_LIST", String(256), nullable=True)
    SY_AREA_LIST_CODE = Column("SY_AREA_LIST_CODE", String(256), nullable=True)
    SY_KEYWORDS = Column("SY_KEYWORDS", String(1024), nullable=True)
    SY_MEDIA_AREA = Column("SY_MEDIA_AREA", String(50), nullable=True)
    SY_MEDIA_AREA_CODE = Column("SY_MEDIA_AREA_CODE", String(50), nullable=True)
    SY_MEDIA_DIRECT_UNIT = Column("SY_MEDIA_DIRECT_UNIT", String(50), nullable=True)
    SY_MEDIA_INDUSTRY = Column("SY_MEDIA_INDUSTRY", String(50), nullable=True)
    SY_MEDIA_RANK_CODE = Column("SY_MEDIA_RANK_CODE", String(50), nullable=True)
    SY_MEDIA_TAG = Column("SY_MEDIA_TAG", String(50), nullable=True)
    SY_MEDIA_TYPE1 = Column("SY_MEDIA_TYPE1", String(50), nullable=True)
    SY_MEDIA_TYPE2 = Column("SY_MEDIA_TYPE2", String(50), nullable=True)
    SY_MEDIA_TYPE3 = Column("SY_MEDIA_TYPE3", String(50), nullable=True)
    SY_NAME = Column("SY_NAME", String(256), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [IR_URLTITLE]}


class OdsZhPolicy(Base):
    """维普国内政策信息"""

    __tablename__ = "ods_zh_policy"
    __table_args__ = {"comment": "维普国内政策信息"}

    lngid = Column("lngid", String(50), nullable=True)
    centre_level = Column("centre_level", String(50), nullable=True)
    district_level = Column("district_level", String(50), nullable=True)
    fulltext = Column("fulltext", Text(), nullable=True)
    industry = Column("industry", String(50), nullable=True)
    keyword = Column("keyword", Text(), nullable=True)
    level = Column("level", String(50), nullable=True)
    organ = Column("organ", String(50), nullable=True)
    policy_type = Column("policy_type", String(50), nullable=True)
    publish_time = Column("publish_time", String(50), nullable=True)
    issued_number = Column("issued_number", String(64), nullable=True)
    pub_year = Column("pub_year", String(50), nullable=True)
    url = Column("url", Text(), nullable=True)
    title = Column("title", Text(), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [lngid]}


class OdsZhPolicy6(Base):
    """拓尔思6月政策样例数据"""

    __tablename__ = "ods_zh_policy_6"
    __table_args__ = {"comment": "拓尔思6月政策样例数据"}

    id = Column("id", String(50), nullable=True, comment="唯一id")
    data_type = Column("data_type", String(50), nullable=True, comment="数据类型")
    status = Column("status", String(50), nullable=True, comment="政策状态（已发布、已撤销）")
    title = Column("title", Text(), nullable=True, comment="标题（纯文本）")
    title_na = Column("title_na", Text(), nullable=True, comment="标题（富文本）")
    content = Column("content", Text(), nullable=True, comment="内容")
    url = Column("url", String(256), nullable=True, comment="原文链接地址")
    issue_no = Column("issue_no", String(50), nullable=True, comment="发文字号")
    index_no = Column("index_no", String(50), nullable=True, comment="索引号")
    site_name = Column("site_name", String(50), nullable=True, comment="站点名称")
    create_time = Column("create_time", String(50), nullable=True, comment="成文日期")
    publish_time = Column("publish_time", String(50), nullable=True, comment="发文日期")
    publish_year = Column("publish_year", String(50), nullable=True, comment="发布年份")
    area = Column("area", String(50), nullable=True, comment="地区")
    area_code = Column("area_code", String(50), nullable=True, comment="地区编码")
    policy_level = Column("policy_level", String(50), nullable=True, comment="政策层级")
    region = Column("region", String(200), nullable=True, comment="完整地区")
    platform = Column("platform", String(50), nullable=True, comment="数据来源平台")
    attachments = Column("attachments", String(512), nullable=True, comment="附件")
    keywords = Column("keywords", String(512), nullable=True, comment="关键词")
    abstracts = Column("abstracts", Text(), nullable=True, comment="摘要")
    elements = Column("elements", Text(), nullable=True, comment="主旨要素")
    keypoints = Column("keypoints", String(1024), nullable=True, comment="政策要点")
    allfactors = Column("allfactors", String(1024), nullable=True, comment="扶持要素")
    tags = Column("tags", Text(), nullable=True, comment="标签集")
    pedigree = Column("pedigree", String(1024), nullable=True, comment="政策谱系")
    content_type = Column("content_type", String(50), nullable=True, comment="内容分类")
    publish_department = Column("publish_department", String(50), nullable=True, comment="发文机构")
    region_origin = Column("region_origin", String(50), nullable=True, comment="地区原始信息")
    updated_time = Column("updated_time", String(50), nullable=True, comment="更新时间")
    industry = Column("industry", String(200), nullable=True, comment="产业分类")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [id]}


class OdsZhPolicyTuoersi(Base):
    """拓尔思国内政策信息5月样例数据"""

    __tablename__ = "ods_zh_policy_tuoersi"
    __table_args__ = {"comment": "拓尔思国内政策信息5月样例数据"}

    title = Column("title", Text(), nullable=True)
    policy_level = Column("policy_level", String(100), nullable=True)
    industry_classify = Column("industry_classify", String(512), nullable=True)
    create_time = Column("create_time", String(50), nullable=True)
    area = Column("area", String(100), nullable=True)
    publish_department = Column("publish_department", String(100), nullable=True)
    publish_time = Column("publish_time", String(50), nullable=True)
    issue_no = Column("issue_no", String(100), nullable=True)
    keywords = Column("keywords", Text(), nullable=True)
    source = Column("source", String(100), nullable=True)
    data_type = Column("data_type", String(50), nullable=True)
    index_no = Column("index_no", String(50), nullable=True)
    content_type = Column("content_type", String(50), nullable=True)
    url = Column("url", String(256), nullable=True)
    abstract = Column("abstract", Text(), nullable=True)
    content = Column("content", Text(), nullable=True)
    content_na = Column("content_na", Text(), nullable=True)
    elements = Column("elements", String(100), nullable=True)
    attachments = Column("attachments", String(512), nullable=True)
    attachment_url = Column("attachment_url", String(512), nullable=True)
    labels = Column("labels", Text(), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [title]}
