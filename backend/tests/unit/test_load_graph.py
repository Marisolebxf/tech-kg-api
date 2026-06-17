from __future__ import annotations

from unittest.mock import MagicMock

from script.load_graph import build_org_node_props, build_scholar_node_props, load_graph


def test_build_scholar_node_props():
    s = MagicMock(
        scholar_id="S1",
        name_zh="张伟",
        name_en="Zhang",
        scholar_org_name_zh="清华大学",
        scholar_org_name_en="Tsinghua",
        h_index=10,
        citation_nums=100,
        paper_nums=5,
    )
    p = build_scholar_node_props(s)
    assert p == {
        "scholar_id": "S1",
        "name_zh": "张伟",
        "name_en": "Zhang",
        "scholar_org_name_zh": "清华大学",
        "scholar_org_name_en": "Tsinghua",
        "h_index": 10,
        "citation_nums": 100,
        "paper_nums": 5,
    }


def test_build_org_node_props():
    o = MagicMock(
        org_id="O1",
        name_cn="清华大学",
        province="北京市",
        city="北京",
        org_type="高校",
        listing_status="",
        incorporation_year=1911,
    )
    p = build_org_node_props(o)
    assert p["org_id"] == "O1" and p["name_cn"] == "清华大学" and p["province"] == "北京市"


def test_load_graph_empty_mysql(monkeypatch):
    # MySQL 空：scholar/org 都返回空，graph 不应被写入
    graph = MagicMock()
    graph.create_node = MagicMock()
    graph.create_edge = MagicMock()
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[]))

    class FakeScholarDAO:
        def __init__(self, *a, **k):
            pass

        def list(self, *, limit, offset):
            return []

    class FakeOrgDAO:
        def __init__(self, *a, **k):
            pass

        def list(self, *, limit, offset):
            return []

        def get_by_name(self, name):
            return None

    monkeypatch.setattr("script.load_graph.ScholarDAO", FakeScholarDAO)
    monkeypatch.setattr("script.load_graph.OrganizationDAO", FakeOrgDAO)
    monkeypatch.setattr("script.load_graph.get_techkg_client", lambda: graph)
    monkeypatch.setattr("script.load_graph.get_mysql_client", lambda: MagicMock())

    n = load_graph()
    assert n == 0
    graph.create_node.assert_not_called()
