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
    svc = ExpertEnterpriseMiningService(gkx_session=sess, graph=MagicMock(), llm=MagicMock())
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
    assert result["totalMined"] == 1
    r = result["minedRelations"][0]
    assert r["enterpriseId"] == "id1"
    assert r["relationType"] == "tech_cooperation"
    assert r["build"]["effective"] is True
    assert r["annotate"]["annotated"] is True
    assert r["analyze"] is not None


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
