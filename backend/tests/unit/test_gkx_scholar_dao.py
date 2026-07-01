from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dao.gkx_scholar import GkxScholarDAO
from db_model.base import Base
from db_model.scholar import DwdScholar, DwdScholarResearchDirection

_TS = datetime(2024, 1, 1)


def _session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng, tables=[DwdScholar.__table__, DwdScholarResearchDirection.__table__]
    )
    s = Session(eng)
    s.add(
        DwdScholar(
            id=1,
            scholar_id="007Rb117",
            name_en="Wu Bian",
            name_zh="吴边",
            avatar="",
            scholar_org_name_zh="中国科学院微生物研究所",
            scholar_org_name_en="IMCAS",
            scholar_org_id=None,
            bio="...",
            bio_zh="该学者从事合成生物学研究。",
            work_experience_en="",
            work_experience_zh="2014-至今 中国科学院微生物研究所 研究员",
            education_background_en="",
            education_background_zh="",
            paper_nums=10,
            citation_nums=100,
            h_index=5,
            status=1,
            create_time=_TS,
            update_time=_TS,
        )
    )
    s.add(
        DwdScholarResearchDirection(
            id=1,
            scholar_id="007Rb117",
            fields="合成生物学, 酶工程",
            create_time=_TS,
            update_time=_TS,
        )
    )
    s.commit()
    return s


def test_get_by_id_found():
    with _session() as s:
        scholar = GkxScholarDAO(s).get_by_id("007Rb117")
        assert scholar is not None
        assert scholar.name_zh == "吴边"


def test_get_by_id_absent():
    with _session() as s:
        assert GkxScholarDAO(s).get_by_id("nope") is None


def test_research_directions_split():
    with _session() as s:
        dirs = GkxScholarDAO(s).get_research_directions("007Rb117")
        assert dirs == ["合成生物学", "酶工程"]
