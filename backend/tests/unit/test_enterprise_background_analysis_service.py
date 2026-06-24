from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import service.enterprise_background_analysis as mod
from service.enterprise_background_analysis import EnterpriseBackgroundAnalysisService


def _org():
    o = MagicMock()
    o.name_cn = "某公司"
    o.org_type = "有限责任公司"
    o.listing_status = "上市"
    o.registered_capital_value = Decimal("1000000")
    o.province = "浙江"
    o.city = "杭州"
    o.incorporation_year = 2010
    return o


def _setup(monkeypatch, org, org_dao, pat_dao, llm=None):
    monkeypatch.setattr(mod, "OrganizationDAO", lambda session: org_dao)
    monkeypatch.setattr(mod, "PatentDAO", lambda session: pat_dao)
    monkeypatch.setattr(mod, "get_llm_client", lambda: llm)
    session = MagicMock()
    mc = MagicMock()
    mc.session.return_value = session
    monkeypatch.setattr(mod, "get_mysql_client", lambda: mc)
    org_dao.get_by_id.return_value = org


def test_analyze_raises_when_enterprise_missing(monkeypatch):
    org_dao, pat_dao = MagicMock(), MagicMock()
    _setup(monkeypatch, None, org_dao, pat_dao)
    with pytest.raises(KeyError):
        EnterpriseBackgroundAnalysisService().analyze(
            {"enterpriseId": "NO", "analysisDimensions": ["financial"], "patentCPC": []}
        )


def test_analyze_returns_degraded_when_no_financial_data(monkeypatch):
    org_dao, pat_dao = MagicMock(), MagicMock()
    _setup(monkeypatch, _org(), org_dao, pat_dao, llm=None)
    org_dao.get_stock_finance.return_value = []
    org_dao.get_annual_finance.return_value = []
    pat_dao.count_by_cpc_section.return_value = []
    resp = EnterpriseBackgroundAnalysisService().analyze(
        {"enterpriseId": "E001", "analysisDimensions": ["financial"], "patentCPC": []}
    )
    assert resp["dimensions"]["financial"]["available"] is False
    assert resp["dimensions"]["financial"]["summary"] == "暂无数据"
    assert resp["coreTechLayout"] == ""


def test_analyze_uses_llm_conclusion_and_falls_back(monkeypatch):
    org_dao, pat_dao = MagicMock(), MagicMock()
    llm = MagicMock()
    llm.synthesize.side_effect = [
        '{"financial": "营收稳健增长"}',
        "核心技术围绕人工智能布局",
    ]
    _setup(monkeypatch, _org(), org_dao, pat_dao, llm=llm)
    fin = MagicMock()
    fin.occur_period = "2024"
    fin.operating_revenue = Decimal("100")
    fin.pure_profit = Decimal("10")
    fin.total_assets = Decimal("500")
    fin.research_development_amount = Decimal("20")
    fin.employees_number = 200
    org_dao.get_stock_finance.return_value = [fin]
    pat_dao.count_by_cpc_section.return_value = [{"cpcSection": "G", "count": 5}]
    resp = EnterpriseBackgroundAnalysisService().analyze(
        {"enterpriseId": "E001", "analysisDimensions": ["financial"], "patentCPC": []}
    )
    assert resp["dimensions"]["financial"]["available"] is True
    assert resp["dimensions"]["financial"]["conclusion"] == "营收稳健增长"
    assert resp["coreTechLayout"] == "核心技术围绕人工智能布局"
    assert resp["patentDistribution"] == [{"cpcSection": "G", "count": 5}]


def test_analyze_llm_failure_falls_back_to_template(monkeypatch):
    org_dao, pat_dao = MagicMock(), MagicMock()
    llm = MagicMock()
    llm.synthesize.return_value = None
    _setup(monkeypatch, _org(), org_dao, pat_dao, llm=llm)
    fin = MagicMock()
    fin.occur_period = "2024"
    fin.operating_revenue = Decimal("100")
    fin.pure_profit = None
    fin.total_assets = None
    fin.research_development_amount = None
    fin.employees_number = None
    org_dao.get_stock_finance.return_value = [fin]
    pat_dao.count_by_cpc_section.return_value = []
    resp = EnterpriseBackgroundAnalysisService().analyze(
        {"enterpriseId": "E001", "analysisDimensions": ["financial"], "patentCPC": []}
    )
    assert resp["dimensions"]["financial"]["available"] is True
    assert resp["dimensions"]["financial"]["conclusion"]


def test_analyze_core_tech_and_industry_status_dimensions(monkeypatch):
    org_dao, pat_dao = MagicMock(), MagicMock()
    _setup(monkeypatch, _org(), org_dao, pat_dao, llm=None)
    prod = MagicMock()
    prod.industry_class = "人工智能"
    prod.main_activities = "算法研发"
    prod.main_prod = "AI芯片"
    org_dao.get_products.return_value = prod
    org_dao.get_tags.return_value = []
    org_dao.get_industry_chain.return_value = []
    org_dao.get_chain_products.return_value = []
    pat1 = MagicMock()
    pat1.patent_id = "P1"
    pat1.first_current_assignee_name = "某公司"
    pat_dao.list_by_assignee.return_value = [pat1]
    pat_dao.count_by_cpc_section.return_value = []
    resp = EnterpriseBackgroundAnalysisService().analyze(
        {
            "enterpriseId": "E001",
            "analysisDimensions": ["industry_status", "core_tech"],
            "patentCPC": ["G06N"],
        }
    )
    assert resp["dimensions"]["industry_status"]["available"] is True
    assert resp["dimensions"]["industry_status"]["facts"]["province"] == "浙江"
    assert resp["dimensions"]["core_tech"]["available"] is True
    assert resp["dimensions"]["core_tech"]["facts"]["mainProducts"] == "AI芯片"
    assert resp["dimensions"]["core_tech"]["facts"]["patentCount"] == 1
    # 模板结论（无 LLM）
    assert resp["dimensions"]["industry_status"]["conclusion"]
    assert "AI芯片" in resp["dimensions"]["core_tech"]["conclusion"]
    # core_tech 模板小结
    assert "AI芯片" in resp["coreTechLayout"]
