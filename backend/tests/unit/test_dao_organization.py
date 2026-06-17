from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dao.organization import OrganizationDAO
from db_model.base import Base
from db_model.organization import DwdOrgRegInfo


def _session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[DwdOrgRegInfo.__table__])
    return Session(eng)


def test_get_by_name_and_id():
    with _session() as s:
        now = datetime(2024, 1, 1)
        s.add(
            DwdOrgRegInfo(
                org_id="O1",
                name_cn="清华大学",
                province="北京市",
                data_source="t",
                created_time=now,
                updated_time=now,
            )
        )
        s.commit()
        dao = OrganizationDAO(s)
        assert dao.get_by_id("O1").name_cn == "清华大学"
        assert dao.get_by_name("清华大学").org_id == "O1"
        assert dao.get_by_name("不存在") is None
        assert len(dao.list(limit=10)) == 1
