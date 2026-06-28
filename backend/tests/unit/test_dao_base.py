from datetime import datetime

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, sessionmaker

from dao.base import BaseDAO
from dao.scholar import ScholarDAO
from db_model.base import Base
from db_model.scholar import DwdScholar
from infra.mysql import MySQLClient


class DemoRecord(Base):
    __tablename__ = "test_demo_record"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    status = Column(Integer, nullable=False, default=1)


class DemoDAO(BaseDAO[DemoRecord]):
    model = DemoRecord


def create_test_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[DemoRecord.__table__, DwdScholar.__table__])
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)()


def test_base_dao_crud() -> None:
    session = create_test_session()
    dao = DemoDAO(session=session)

    created = dao.create(name="alpha", status=1)
    assert created.id == 1
    assert dao.get(1).name == "alpha"
    assert dao.count() == 1

    updated = dao.update(1, name="beta")
    assert updated is not None
    assert updated.name == "beta"
    assert [item.name for item in dao.list()] == ["beta"]

    assert dao.delete(1) is True
    assert dao.get(1) is None


def test_scholar_dao_queries() -> None:
    session = create_test_session()
    session.add(
        DwdScholar(
            id=1,
            scholar_id="scholar-001",
            name_en="Ada Lovelace",
            name_zh="阿达",
            avatar="",
            scholar_org_name_en="Analytical Engine Lab",
            scholar_org_name_zh="分析机实验室",
            scholar_org_id="org-001",
            bio="",
            bio_zh="",
            work_experience_en="",
            work_experience_zh="",
            education_background_en="",
            education_background_zh="",
            paper_nums=1,
            citation_nums=2,
            h_index=3,
            status=1,
            create_time=datetime(2026, 1, 1),
            update_time=datetime(2026, 1, 2),
        )
    )
    session.commit()

    dao = ScholarDAO(session=session)

    assert dao.get_by_id(1).scholar_id == "scholar-001"
    assert dao.get_by_scholar_id("scholar-001").name_zh == "阿达"
    assert dao.search_by_name("Ada")[0].scholar_id == "scholar-001"
    assert dao.search_by_name("阿")[0].name_en == "Ada Lovelace"


def test_mysql_client_builds_escaped_url() -> None:
    client = MySQLClient(
        host="127.0.0.1",
        port=3306,
        database="gkx_local",
        username="root",
        password="p@ss word",
    )

    assert client.url == "mysql+pymysql://root:p%40ss+word@127.0.0.1:3306/gkx_local?charset=utf8mb4"
