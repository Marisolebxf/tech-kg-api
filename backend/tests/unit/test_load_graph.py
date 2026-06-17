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

    monkeypatch.setattr("script.load_graph.ScholarDAO", FakeScholarDAO)
    monkeypatch.setattr("script.load_graph.OrganizationDAO", FakeOrgDAO)
    monkeypatch.setattr("script.load_graph.get_techkg_client", lambda: graph)
    monkeypatch.setattr("script.load_graph.get_mysql_client", lambda: MagicMock())

    n = load_graph()
    assert n == 0
    graph.merge_node.assert_not_called()
    graph.merge_edge.assert_not_called()


def test_load_graph_happy_path(monkeypatch):
    org1 = MagicMock(
        org_id="O1",
        name_cn="清华大学",
        province="北京市",
        city="北京",
        org_type="高校",
        listing_status="",
        incorporation_year=1911,
    )
    org2 = MagicMock(
        org_id="O2",
        name_cn="华智科技",
        province="浙江省",
        city="杭州",
        org_type="企业",
        listing_status="上市",
        incorporation_year=2010,
    )
    sch1 = MagicMock(
        scholar_id="S1",
        name_zh="张伟",
        name_en="Zhang",
        scholar_org_name_zh="清华大学",
        scholar_org_name_en="Tsinghua",
        h_index=10,
        citation_nums=100,
        paper_nums=5,
    )
    sch2 = MagicMock(
        scholar_id="S2",
        name_zh="李明",
        name_en="Li",
        scholar_org_name_zh="华智科技",
        scholar_org_name_en="Huazhi",
        h_index=3,
        citation_nums=20,
        paper_nums=2,
    )

    graph = MagicMock()
    # org 节点 merge 返回带 id 的 node
    graph.merge_node.side_effect = lambda labels, ident, props: MagicMock(
        id=f"node_{ident[list(ident)[0]]}"
    )
    # scholar2 的 org 走 find_nodes 兜底（map 里已有华智科技，实际会命中 map；这里再验证 fallback 用另一个名字）
    graph.merge_edge = MagicMock()
    graph.find_nodes = MagicMock(return_value=MagicMock(items=[MagicMock(id="node_O2")]))

    class FakeScholarDAO:
        def __init__(self, *a, **k):
            pass

        def list(self, *, limit, offset):
            return [sch1, sch2] if offset == 0 else []

    class FakeOrgDAO:
        def __init__(self, *a, **k):
            pass

        def list(self, *, limit, offset):
            return [org1, org2] if offset == 0 else []

    monkeypatch.setattr("script.load_graph.ScholarDAO", FakeScholarDAO)
    monkeypatch.setattr("script.load_graph.OrganizationDAO", FakeOrgDAO)
    monkeypatch.setattr("script.load_graph.get_techkg_client", lambda: graph)
    monkeypatch.setattr("script.load_graph.get_mysql_client", lambda: MagicMock())

    n = load_graph(batch_limit=10)
    assert n == 2
    assert graph.merge_node.call_count == 4  # 2 org + 2 scholar
    assert graph.merge_edge.call_count == 2  # 2 EMPLOYED_BY
    # 边类型与 relation_type
    args = graph.merge_edge.call_args_list[0].args
    assert args[2] == "EMPLOYED_BY"
    assert args[4]["relation_type"] == "任职"
