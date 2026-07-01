from __future__ import annotations

from unittest.mock import MagicMock

from service.expert_enterprise_mining import ExpertEnterpriseMiningService


class _FakeScholarDAO:
    def __init__(self, scholar):
        self._scholar = scholar

    def get_by_id(self, _):
        return self._scholar

    def get_research_directions(self, _):
        return ["合成生物学"]


class _FakeOrgDAO:
    def __init__(self, candidates):
        self._cands = candidates

    def list_name_id(self):
        return self._cands

    def get_by_id(self, org_id):
        for oid, name in self._cands:
            if oid == org_id:
                m = MagicMock()
                m.org_id = oid
                m.name_cn = name
                m.province = "浙江"
                m.listing_status = ""
                return m
        return None


def _scholar():
    m = MagicMock()
    m.scholar_id = "007Rb117"
    m.name_zh = "吴边"
    m.name_en = "Wu Bian"
    m.scholar_org_name_zh = "中国科学院微生物研究所"
    m.bio_zh = "与某生物科技公司合作。"
    m.bio = ""
    m.work_experience_zh = ""
    m.education_background_zh = ""
    m.h_index = 5
    m.citation_nums = 100
    m.paper_nums = 10
    return m


def _make_service(scholar, candidates, llm_items, llm_degraded=False):
    sess = MagicMock()
    graph = MagicMock()
    graph.get_node_edges.return_value = []  # regenerate=False 默认无已建关系 → 走完整流程
    svc = ExpertEnterpriseMiningService(gkx_session=sess, graph=graph, llm=MagicMock())
    svc._scholar_dao_factory = lambda s: _FakeScholarDAO(scholar)
    svc._org_dao_factory = lambda s: _FakeOrgDAO(candidates)
    svc._extract_fn = lambda llm, profile: (llm_items, llm_degraded)
    svc._build_svc = MagicMock()
    svc._build_svc.build.return_value = {
        "effective": True,
        "builtRelationId": "007Rb117->id1@0",
    }
    svc._annotate_svc = MagicMock()
    svc._annotate_svc.annotate.return_value = {"annotated": True}
    svc._analyze_svc = MagicMock()
    svc._analyze_svc.analyze.return_value = {
        "dimensions": {"industry_status": {}},
        "coreTechLayout": "x",
    }
    return svc


def test_mine_full_flow():
    scholar = _scholar()
    candidates = [("id1", "某生物科技有限公司")]
    items = [
        {
            "enterprise_name": "某生物科技",
            "relation_type": "tech_cooperation",
            "role": "technical_advisor",
            "tech_field": "酶工程",
            "period_start": "2018-01-01",
            "period_end": "",
            "evidence": "合作",
        }
    ]
    svc = _make_service(scholar, candidates, items)
    result = svc.mine({"scholarId": "007Rb117", "topN": 5})
    assert result["scholarId"] == "007Rb117"
    assert result["scholarName"] == "吴边"
    assert result["degraded"] is False
    assert result["cached"] is False
    assert result["totalMined"] == 1
    r = result["minedRelations"][0]
    assert r["enterpriseId"] == "id1"
    assert r["relationType"] == "tech_cooperation"
    assert r["build"]["effective"] is True
    assert r["annotate"]["annotated"] is True
    assert r["analyze"] is not None


def _edge(target_id, relation_type="employment", role="engineer", tech_field="", start="", end=""):
    e = MagicMock()
    e.target_id = target_id
    e.id = f"007Rb117->{target_id}@0"
    e.properties = {
        "relation_type": relation_type,
        "role": role,
        "tech_field": tech_field,
        "start_date": start,
        "end_date": end,
        "source": "build",
    }
    return e


def _org_node(org_id, name):
    n = MagicMock()
    n.properties = {"org_id": org_id, "name_cn": name}
    return n


def test_mine_regenerate_false_returns_existing_and_skips_pipeline():
    """regenerate=False 且图库已有 EMPLOYED_BY 边时，直接返回已建关系，不跑 LLM/三接口。"""
    graph = MagicMock()
    edge = _edge(
        "id1",
        relation_type="tech_cooperation",
        role="technical_advisor",
        tech_field="酶工程",
        start="2018-01-01",
    )
    graph.get_node_edges.return_value = [edge]
    scholar_node = MagicMock()
    scholar_node.properties = {"name_zh": "吴边", "scholar_org_name_zh": "中国科学院微生物研究所"}
    # _collect_existing_relations 先 get_node(target_id) 取企业，mine() 再 get_node(scholar_id) 取学者
    graph.get_node.side_effect = [_org_node("id1", "某生物科技有限公司"), scholar_node]

    svc = ExpertEnterpriseMiningService(gkx_session=MagicMock(), graph=graph, llm=MagicMock())
    extract_fn = MagicMock(return_value=([], False))
    svc._extract_fn = extract_fn
    svc._build_svc = MagicMock()
    svc._annotate_svc = MagicMock()
    svc._analyze_svc = MagicMock()

    result = svc.mine({"scholarId": "007Rb117", "regenerate": False})
    assert result["cached"] is True
    assert result["scholarName"] == "吴边"
    assert result["totalMined"] == 1
    r = result["minedRelations"][0]
    assert r["enterpriseId"] == "id1"
    assert r["enterpriseName"] == "某生物科技有限公司"
    assert r["relationLabel"] == "技术合作"
    assert r["roleLabel"] == "技术顾问"
    assert r["techField"] == "酶工程"
    assert r["period"]["start"] == "2018-01-01"
    assert r["build"]["effective"] is True
    assert r["analyze"] is None
    # 没跑完整流程
    extract_fn.assert_not_called()
    svc._build_svc.build.assert_not_called()
    svc._analyze_svc.analyze.assert_not_called()


def test_mine_regenerate_true_ignores_existing_and_runs_full_pipeline():
    """regenerate=True 时即使图库已有关系也强制重跑完整流程。"""
    scholar = _scholar()
    candidates = [("id1", "某生物科技有限公司")]
    items = [
        {
            "enterprise_name": "某生物科技",
            "relation_type": "tech_cooperation",
            "role": "technical_advisor",
            "tech_field": "酶工程",
            "period_start": "2018-01-01",
            "period_end": "",
            "evidence": "合作",
        }
    ]
    svc = _make_service(scholar, candidates, items)
    # 即便图库里"已有"关系，regenerate=True 也应忽略
    svc._graph.get_node_edges.return_value = [_edge("id1")]
    result = svc.mine({"scholarId": "007Rb117", "regenerate": True})
    assert result["cached"] is False
    assert result["totalMined"] == 1
    assert result["minedRelations"][0]["build"]["effective"] is True


def test_mine_scholar_not_found_raises_keyerror():
    svc = ExpertEnterpriseMiningService(gkx_session=MagicMock(), graph=MagicMock(), llm=None)
    svc._scholar_dao_factory = lambda s: _FakeScholarDAO(None)
    import pytest

    with pytest.raises(KeyError):
        svc.mine({"scholarId": "nope"})


def test_mine_unmatched_enterprise_goes_to_skipped():
    scholar = _scholar()
    candidates = [("id1", "某生物科技有限公司")]
    items = [
        {
            "enterprise_name": "完全无关的名字XYZ",
            "relation_type": "tech_cooperation",
            "role": "engineer",
            "tech_field": "",
            "period_start": "",
            "period_end": "",
            "evidence": "",
        }
    ]
    svc = _make_service(scholar, candidates, items, llm_degraded=False)
    result = svc.mine({"scholarId": "007Rb117"})
    assert result["totalMined"] == 0
    assert len(result["skipped"]) == 1
