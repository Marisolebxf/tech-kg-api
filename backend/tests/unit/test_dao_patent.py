from __future__ import annotations

from unittest.mock import MagicMock

from dao.patent import PatentDAO


def _pat(patent_id, assignee, cpc):
    p = MagicMock()
    p.patent_id = patent_id
    p.first_current_assignee_name = assignee
    p.classification_cpc = cpc
    return p


def test_count_by_cpc_section_groups_by_first_letter():
    session = MagicMock()
    session.execute.return_value.scalars.return_value = [
        _pat("A", "某公司", {"main": ["G06N3/04", "G06F40/30"], "add": ["H04L9/00"]}),
        _pat("B", "某公司", {"main": ["G06N3/02"]}),
    ]
    dao = PatentDAO(session)
    dist = dao.count_by_cpc_section("某公司")
    sections = {d["cpcSection"]: d["count"] for d in dist}
    assert sections["G"] == 2
    assert sections["H"] == 1


def test_count_dedups_duplicate_codes_within_patent():
    session = MagicMock()
    session.execute.return_value.scalars.return_value = [
        _pat("A", "某公司", {"main": ["G06N3/04"], "add": ["G06N3/04"]}),
        _pat("B", "某公司", {"main": ["G06N3/04", "G06F40/30"]}),
    ]
    dao = PatentDAO(session)
    dist = dao.count_by_cpc_section("某公司")
    sections = {d["cpcSection"]: d["count"] for d in dist}
    assert sections["G"] == 2


def test_list_by_assignee_filters_by_cpc_prefix():
    session = MagicMock()
    session.execute.return_value.scalars.return_value = [
        _pat("A", "某公司", {"main": ["G06N3/04"]}),
        _pat("B", "某公司", {"main": ["H04L9/00"]}),
    ]
    dao = PatentDAO(session)
    rows = dao.list_by_assignee("某公司", ["G06N"])
    assert [r.patent_id for r in rows] == ["A"]
