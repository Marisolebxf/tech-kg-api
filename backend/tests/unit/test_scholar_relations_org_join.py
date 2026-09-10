from unittest.mock import MagicMock

from script.load_scholar_relations import build_org_name_vid_index, resolve_org_vid_by_name


def test_resolve_by_name_zh():
    idx = {"新智认知数字科技股份有限公司": "org_abc", "其他": "org_x"}
    assert resolve_org_vid_by_name("新智认知数字科技股份有限公司", None, idx) == "org_abc"


def test_resolve_by_name_en_fallback():
    idx = {"new intelligence": "org_en1"}
    assert resolve_org_vid_by_name(None, "New Intelligence", idx) == "org_en1"


def test_resolve_returns_none_when_not_found():
    idx = {"其他": "org_x"}
    assert resolve_org_vid_by_name("不存在的机构", None, idx) is None


def test_resolve_empty_name_returns_none():
    assert resolve_org_vid_by_name("", "", {}) is None
    assert resolve_org_vid_by_name(None, None, {"a": "b"}) is None


def _rec(vid, name_cn, name_en):
    m = MagicMock()
    m.get = lambda k, d=None: {"vid": vid, "name_cn": name_cn, "name_en": name_en}.get(k, d)
    return m


def test_build_index_from_graph():
    graph = MagicMock()
    result = MagicMock()
    result.records = [
        _rec("org_1", "甲公司", "Jia"),
        _rec("org_2", None, "Yi"),
        _rec("org_3", "  ", "  "),
    ]
    graph.execute_read.return_value = result
    idx = build_org_name_vid_index(graph)
    assert idx["甲公司"] == "org_1"
    assert idx["Jia"] == "org_1"
    assert idx["Yi"] == "org_2"
    # 空名不入索引
    assert "  " not in idx


def test_build_index_empty_graph():
    graph = MagicMock()
    result = MagicMock()
    result.records = []
    graph.execute_read.return_value = result
    assert build_org_name_vid_index(graph) == {}


def test_build_index_read_failure_returns_empty():
    graph = MagicMock()
    graph.execute_read.side_effect = RuntimeError("boom")
    assert build_org_name_vid_index(graph) == {}


def test_source_fallback_verifies_existing_node():
    from types import SimpleNamespace
    from script.load_scholar_relations import resolve_org_vid_from_source
    session = MagicMock()
    session.execute.side_effect = [[('org_id',), ('name_cn',)], [('123',)], [], []]
    graph = MagicMock()
    graph.get_node.return_value = SimpleNamespace(labels=['Organization'], properties={'name_cn': '甲公司'})
    assert resolve_org_vid_from_source(session, graph, ['甲公司']) == 'org_123'
    graph.get_node.assert_called_once_with('org_123')


def test_source_fallback_does_not_create_missing_organization():
    from script.load_scholar_relations import resolve_org_vid_from_source
    session = MagicMock()
    session.execute.side_effect = [[('org_id',), ('name_cn',)], [('123',)], [], []]
    graph = MagicMock()
    graph.get_node.return_value = None
    assert resolve_org_vid_from_source(session, graph, ['甲公司']) is None
    graph.create_node.assert_not_called()


def test_targeted_affiliations_use_requested_scholars():
    from unittest.mock import patch
    from script.load_scholar_relations import load_affiliations
    with patch('script.load_scholar_relations._iter_scholar_affiliations', return_value=[]) as records:
        assert load_affiliations(None, MagicMock(), dry_run=True, scholar_ids=['abc'])['written'] == 0
        records.assert_called_once_with(None, scholar_ids=['abc'])
