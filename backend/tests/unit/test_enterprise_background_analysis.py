from __future__ import annotations

from unittest.mock import MagicMock

from service.enterprise_background_analysis import EnterpriseBackgroundAnalysisService


def _org(org_id="O1", name_cn="某有限公司"):
    m = MagicMock()
    m.org_id = org_id
    m.name_cn = name_cn
    return m


def _mock_session():
    """构造 MagicMock 会话，使 DAO 列表方法返回空列表。"""
    sess = MagicMock()
    # get_by_id 用 execute().scalar_one_or_none()
    sess.execute.return_value.scalar_one_or_none.return_value = _org()
    sess.execute.return_value.all.return_value = []
    sess.execute.return_value.scalars.return_value = []
    return sess


def test_analyze_uses_injected_session_and_skips_close(monkeypatch):
    """传入 session 时 analyze 使用之且不 close（调用方持有）。"""
    # 屏蔽真实 LLM 调用，保证测试快速且不依赖网络
    monkeypatch.setattr("service.enterprise_background_analysis.get_llm_client", lambda: None)
    svc = EnterpriseBackgroundAnalysisService()
    sess = _mock_session()
    result = svc.analyze(
        {"enterpriseId": "O1", "analysisDimensions": ["industry_status"]},
        session=sess,
    )
    assert result["enterpriseId"] == "O1"
    assert result["enterpriseName"] == "某有限公司"
    sess.close.assert_not_called()  # 传入的 session 不应被关闭


def test_analyze_core_tech_tolerates_patent_error(monkeypatch):
    """gkx 无 dwd_patent 表时，core_tech 不应抛异常。"""
    monkeypatch.setattr("service.enterprise_background_analysis.get_llm_client", lambda: None)
    svc = EnterpriseBackgroundAnalysisService()
    sess = _mock_session()
    from dao import patent as patent_mod

    orig = patent_mod.PatentDAO.list_by_assignee
    patent_mod.PatentDAO.list_by_assignee = MagicMock(side_effect=Exception("no table"))
    try:
        result = svc.analyze(
            {"enterpriseId": "O1", "analysisDimensions": ["core_tech"]},
            session=sess,
        )
        assert "core_tech" in result["dimensions"]
    finally:
        patent_mod.PatentDAO.list_by_assignee = orig
