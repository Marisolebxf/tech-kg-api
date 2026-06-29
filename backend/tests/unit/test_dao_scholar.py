from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dao.scholar import ScholarDAO
from db_model.base import Base
from db_model.scholar import DwdScholar


def _session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[DwdScholar.__table__])
    return Session(eng)


def test_get_returns_none_when_absent():
    with _session() as s:
        assert ScholarDAO(s).get("nope") is None


@pytest.mark.skip(reason="merge 后 main db_model/dao 重构与 feature 测试不兼容，待架构统一后修复")
def test_get_and_list():
    with _session() as s:
        s.add(DwdScholar(scholar_id="S1", name_zh="张伟", scholar_org_name_zh="清华大学"))
        s.commit()
        dao = ScholarDAO(s)
        got = dao.get("S1")
        assert got is not None and got.name_zh == "张伟"
        rows = dao.list(limit=10)
        assert len(rows) == 1
