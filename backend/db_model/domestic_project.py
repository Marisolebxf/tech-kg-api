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


class OdsZhProject(Base):
    """深势-国内项目信息表"""

    __tablename__ = "ods_zh_project"
    __table_args__ = {"comment": "深势-国内项目信息表"}

    id = Column("id", String(64), primary_key=True, nullable=False, comment="主键")
    project_number = Column("project_number", String(64), nullable=False, comment="项目编号")
    title = Column("title", String(1000), nullable=False, comment="项目名称")
    project_source = Column("project_source", String(128), nullable=True, comment="项目来源")
    funded_institution = Column(
        "funded_institution", String(255), nullable=True, comment="依托单位"
    )
    project_level = Column("project_level", String(64), nullable=True, comment="项目级别")
    funded_amount = Column("funded_amount", Numeric(12, 2), nullable=True, comment="资助金额")
    discipline = Column("discipline", String(500), nullable=True, comment="学科")
    discipline_code = Column("discipline_code", String(128), nullable=True, comment="学科代码")
    fund_category = Column("fund_category", String(128), nullable=True, comment="基金类别")
    funded_province = Column("funded_province", String(64), nullable=True, comment="资助省份")
    participating_institution = Column(
        "participating_institution", String(255), nullable=True, comment="参与单位"
    )
    approval_year = Column("approval_year", Date(), nullable=True, comment="批准年度")
    approval_time = Column("approval_time", Date(), nullable=True, comment="批准日期")
    research_period = Column("research_period", String(128), nullable=True, comment="研究周期")
    project_host = Column("project_host", String(100), nullable=True, comment="项目负责人")
    participants = Column("participants", Text(), nullable=True, comment="参与人员")
    keywords = Column("keywords", Text(), nullable=True, comment="关键词")
    abstract = Column("abstract", Text(), nullable=True, comment="项目摘要")
    final_report_abstract = Column(
        "final_report_abstract", Text(), nullable=True, comment="结题摘要"
    )
    project_page_url = Column("project_page_url", String(1024), nullable=True, comment="项目详情页")
    create_time = Column("create_time", DateTime(), nullable=True)
    update_time = Column("update_time", DateTime(), nullable=True)


class OdsZhProjectOutput(Base):
    """深势-国内项目产出信息表"""

    __tablename__ = "ods_zh_project_output"
    __table_args__ = {"comment": "深势-国内项目产出信息表"}

    id = Column("id", String(64), primary_key=True, nullable=False, comment="UUID主键")
    total_outputs = Column("total_outputs", Integer(), nullable=True, comment="项目总产出数量")
    journal_articles_count = Column(
        "journal_articles_count", Integer(), nullable=True, comment="期刊文章数量"
    )
    conference_papers_count = Column(
        "conference_papers_count", Integer(), nullable=True, comment="会议论文数量"
    )
    books_count = Column("books_count", Integer(), nullable=True, comment="图书专著数量")
    degree_papers_count = Column(
        "degree_papers_count", Integer(), nullable=True, comment="学位论文数量"
    )
    patents_count = Column("patents_count", Integer(), nullable=True, comment="专利数量")
    clinical_trials_count = Column(
        "clinical_trials_count", Integer(), nullable=True, comment="临床试验数量"
    )
    products_count = Column("products_count", Integer(), nullable=True, comment="产品数量")
    awards_count = Column("awards_count", Integer(), nullable=True, comment="奖项数量")
    reports_count = Column("reports_count", Integer(), nullable=True, comment="报告数量")
    other_outputs_count = Column(
        "other_outputs_count", Integer(), nullable=True, comment="其他产出数量"
    )
    output_journal_articles = Column(
        "output_journal_articles", Text(), nullable=True, comment="期刊文章"
    )
    output_conference_papers = Column(
        "output_conference_papers", Text(), nullable=True, comment="会议论文"
    )
    output_books = Column("output_books", Text(), nullable=True, comment="图书专著")
    output_degree_papers = Column("output_degree_papers", Text(), nullable=True, comment="学位论文")
    output_patents = Column("output_patents", Text(), nullable=True, comment="专利")
    output_clinical_trials = Column(
        "output_clinical_trials", Text(), nullable=True, comment="临床试验"
    )
    output_products = Column("output_products", Text(), nullable=True, comment="产品")
    output_awards = Column("output_awards", Text(), nullable=True, comment="奖项")
    output_reports = Column("output_reports", Text(), nullable=True, comment="报告")
    output_other = Column("output_other", Text(), nullable=True, comment="其他成果")
    create_time = Column("create_time", DateTime(), nullable=True)
    update_time = Column("update_time", DateTime(), nullable=True)
