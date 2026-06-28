from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
)

from db_model.base import Base


class OdsEnReport(Base):
    """万方外文报告信息"""

    __tablename__ = "ods_en_report"
    __table_args__ = {"comment": "万方外文报告信息"}

    Identifier_ID = Column("Identifier_ID", String(50), nullable=True)
    Report_Num = Column("Report_Num", String(50), nullable=True)
    Title_Title = Column("Title_Title", Text(), nullable=True)
    Title_AlterNativeTitle = Column("Title_AlterNativeTitle", Text(), nullable=True)
    Creator_Creator = Column("Creator_Creator", Text(), nullable=True)
    Creator_AlterNativeCreator = Column("Creator_AlterNativeCreator", Text(), nullable=True)
    Creator_Org = Column("Creator_Org", Text(), nullable=True)
    Creator_AlterNativeOrg = Column("Creator_AlterNativeOrg", Text(), nullable=True)
    Date_Issued = Column("Date_Issued", String(50), nullable=True)
    Description_Abstract = Column("Description_Abstract", Text(), nullable=True)
    Description_AlternativeAbstract = Column(
        "Description_AlternativeAbstract", Text(), nullable=True
    )
    Subject_Keywords = Column("Subject_Keywords", Text(), nullable=True)
    Subject_AlternativeKeywords = Column("Subject_AlternativeKeywords", Text(), nullable=True)
    Subject_CLC = Column("Subject_CLC", Text(), nullable=True)
    Subject_SelfFL = Column("Subject_SelfFL", Text(), nullable=True)
    Report_Source = Column("Report_Source", String(50), nullable=True)
    Language_Language = Column("Language_Language", String(50), nullable=True)
    Place_Counry = Column("Place_Counry", String(50), nullable=True)
    Source_Page = Column("Source_Page", String(512), nullable=True)
    Source_PageCount = Column("Source_PageCount", String(50), nullable=True)
    Yn_publition = Column("Yn_publition", String(50), nullable=True)
    Report_Type = Column("Report_Type", String(50), nullable=True)
    Publisher_Publisher = Column("Publisher_Publisher", String(50), nullable=True)
    f_id = Column("f_id", String(50), nullable=True)
    Date_Download = Column("Date_Download", String(50), nullable=True)
    DataLink = Column("DataLink", Text(), nullable=True)
    Collection_Number = Column("Collection_Number", String(50), nullable=True)
    Document_Type = Column("Document_Type", String(50), nullable=True)
    Sponsor = Column("Sponsor", String(50), nullable=True)
    IS_OA = Column("IS_OA", String(50), nullable=True)
    F_Publish_Date = Column("F_Publish_Date", String(512), nullable=True)
    F_FulltextUrl = Column("F_FulltextUrl", Text(), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [Identifier_ID]}


class OdsZhReport(Base):
    """万方中文报告信息"""

    __tablename__ = "ods_zh_report"
    __table_args__ = {"comment": "万方中文报告信息"}

    title = Column("title", Text(), nullable=True)
    alternativeTitle = Column("alternativeTitle", Text(), nullable=True)
    creator = Column("creator", Text(), nullable=True)
    creatOrorganization = Column("creatOrorganization", Text(), nullable=True)
    prepareOrganization = Column("prepareOrganization", Text(), nullable=True)
    publicScope = Column("publicScope", Integer(), nullable=True)
    publicDate = Column("publicDate", String(50), nullable=True)
    delaypubliclyYears = Column("delaypubliclyYears", Integer(), nullable=True)
    note = Column("note", String(50), nullable=True)
    abstractCn = Column("abstractCn", Text(), nullable=True)
    proposalDate = Column("proposalDate", String(50), nullable=True)
    downtime = Column("downtime", String(50), nullable=True)
    keywordsCn = Column("keywordsCn", Text(), nullable=True)
    keywordsEn = Column("keywordsEn", Text(), nullable=True)
    abstractEn = Column("abstractEn", Text(), nullable=True)
    projectName = Column("projectName", String(256), nullable=True)
    projectSubjectName = Column("projectSubjectName", Text(), nullable=True)
    competentOrg = Column("competentOrg", String(50), nullable=True)
    responsiblePerson = Column("responsiblePerson", String(50), nullable=True)
    startDate = Column("startDate", String(50), nullable=True)
    endDate = Column("endDate", String(50), nullable=True)
    linkmanName = Column("linkmanName", String(50), nullable=True)
    linkmanEmail = Column("linkmanEmail", String(50), nullable=True)
    lnkmanPhone = Column("lnkmanPhone", String(50), nullable=True)
    linkmanAddresss = Column("linkmanAddresss", Text(), nullable=True)
    fieldId = Column("fieldId", Text(), nullable=True)
    classification = Column("classification", String(50), nullable=True)
    kjbgType = Column("kjbgType", String(50), nullable=True)
    ID = Column("ID", String(50), nullable=True)

    # Source table has no physical primary key; this is ORM identity only.
    __mapper_args__ = {"primary_key": [title]}
