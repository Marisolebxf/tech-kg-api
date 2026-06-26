from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)

from db_model.base import Base


class DwdIndustryChainInfo(Base):
    """产业链图谱"""

    __tablename__ = "dwd_industry_chain_info"
    __table_args__ = {"comment": "产业链图谱"}

    chain_code = Column("chain_code", String(255), nullable=True, comment="产业链代码")
    chain_name = Column("chain_name", String(255), nullable=True, comment="产业链名称")
    node_id = Column("node_id", String(255), nullable=True, comment="节点代码")
    node_name = Column("node_name", String(255), nullable=True, comment="节点名称")
    node_type = Column("node_type", Integer(), nullable=True, comment="节点类型")
    level = Column("level", Integer(), nullable=True, comment="节点层级")
    node_seq = Column("node_seq", Integer(), nullable=True, comment="节点序号")
    parent_id = Column("parent_id", String(255), nullable=True, comment="父级节点代码")
    parent_name = Column("parent_name", String(255), nullable=True, comment="父级节点名称")
    node_imp_level = Column("node_imp_level", Integer(), nullable=True, comment="节点重要性等级")
    downstream_lin = Column("downstream_lin", String(255), nullable=True, comment="下游节点代码")
    node_stage = Column("node_stage", Integer(), nullable=True, comment="节点环节")
    node_path = Column("node_path", Text(), nullable=True, comment="节点路径")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [chain_code]}


class DwdIndustryChainNewsInfo(Base):
    """产业动态资讯"""

    __tablename__ = "dwd_industry_chain_news_info"
    __table_args__ = {"comment": "产业动态资讯"}

    chain_code = Column("chain_code", String(255), nullable=True, comment="产业链代码")
    chain_name = Column("chain_name", String(255), nullable=True, comment="产业链名称")
    news_id = Column("news_id", String(255), nullable=True, comment="资讯id")
    title = Column("title", String(255), nullable=True, comment="标题")
    relaese_date = Column("relaese_date", Date(), nullable=True, comment="发布时间")
    summary = Column("summary", Text(), nullable=True, comment="摘要")
    source = Column("source", String(255), nullable=True, comment="来源")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [chain_code]}


class DwdOrgIndustryChainDtl(Base):
    """产业关联企业信息"""

    __tablename__ = "dwd_org_industry_chain_dtl"
    __table_args__ = {"comment": "产业关联企业信息"}

    chain_code = Column("chain_code", String(255), nullable=True, comment="产业链代码")
    chain_name = Column("chain_name", String(255), nullable=True, comment="产业链名称")
    node_id = Column("node_id", String(255), nullable=True, comment="节点代码")
    node_name = Column("node_name", String(255), nullable=True, comment="节点名称")
    antitypic = Column("antitypic", String(255), nullable=True, comment="企业id")
    credit_code = Column("credit_code", String(255), nullable=True, comment="统一社会信用代码")
    chain_score = Column("chain_score", Numeric(20, 2), nullable=True, comment="产业链评分")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [chain_code]}


class DwdOrgIndustryChainPatDtl(Base):
    """产业链关联专利信息"""

    __tablename__ = "dwd_org_industry_chain_pat_dtl"
    __table_args__ = {"comment": "产业链关联专利信息"}

    chain_code = Column("chain_code", String(255), nullable=True, comment="产业链代码")
    chain_name = Column("chain_name", String(255), nullable=True, comment="产业链名称")
    node_id = Column("node_id", String(255), nullable=True, comment="节点代码")
    node_name = Column("node_name", String(255), nullable=True, comment="节点名称")
    apno = Column("apno", String(255), nullable=True, comment="申请号")
    apdt = Column("apdt", Date(), nullable=True, comment="申请日")
    pat_name = Column("pat_name", String(500), nullable=True, comment="专利名称")
    pn = Column("pn", String(255), nullable=True, comment="公布(公告)号")
    pbdt = Column("pbdt", Date(), nullable=True, comment="公布(公告)日")
    current_assign = Column("current_assign", Text(), nullable=True, comment="申请(专利权)人")
    inventors = Column("inventors", Text(), nullable=True, comment="发明(设计)人")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [chain_code]}


class DwdOrgIndustryChainProdDtl(Base):
    """产业链企业关联产品信息"""

    __tablename__ = "dwd_org_industry_chain_prod_dtl"
    __table_args__ = {"comment": "产业链企业关联产品信息"}

    chain_code = Column("chain_code", String(255), nullable=True, comment="产业链代码")
    chain_name = Column("chain_name", String(255), nullable=True, comment="产业链名称")
    antitypic = Column("antitypic", String(255), nullable=True, comment="企业id")
    company_name = Column("company_name", String(500), nullable=True, comment="企业名称")
    credit_code = Column("credit_code", String(255), nullable=True, comment="统一社会信用代码")
    tech_product = Column("tech_product", String(255), nullable=True, comment="主营产品名称")
    tech_product_s = Column("tech_product_s", Integer(), nullable=True, comment="主营产品排序")
    data_source = Column("data_source", String(255), nullable=True, comment="数据来源")
    created_time = Column("created_time", DateTime(), nullable=True, comment="创建时间")
    updated_time = Column("updated_time", DateTime(), nullable=True, comment="更新时间")

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [chain_code]}
