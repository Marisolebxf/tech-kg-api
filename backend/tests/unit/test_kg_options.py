from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import service.kg_options as mod


@pytest.mark.skip(reason="merge 后 main db_model/dao 重构与 feature 测试不兼容，待架构统一后修复")
def test_get_options_aggregates_all_sections(monkeypatch):
    # graph: scholars + edges
    scholar = MagicMock(id="E10001", properties={"name_zh": "专家001"})
    edge = MagicMock(id="E10001->ENT001@0", source_id="E10001", target_id="ENT001")
    graph = MagicMock()
    graph.get_nodes_by_label.return_value = MagicMock(items=[scholar])
    graph.get_edges_by_type.return_value = MagicMock(items=[edge])
    monkeypatch.setattr(mod, "get_techkg_client", lambda: graph)

    # mysql: enterprises
    org = MagicMock()
    org.org_id = "ENT001"
    org.name_cn = "企业001有限公司"
    session = MagicMock()
    session.execute.return_value.scalars.return_value = [org]
    mc = MagicMock()
    mc.session.return_value = session
    monkeypatch.setattr(mod, "get_mysql_client", lambda: mc)

    opts = mod.get_options()
    assert opts["scholars"] == [{"scholarId": "E10001", "name": "专家001"}]
    assert opts["enterprises"] == [{"enterpriseId": "ENT001", "name": "企业001有限公司"}]
    assert opts["edges"][0]["relationId"] == "E10001->ENT001@0"
    assert any(o["value"] == "employment" for o in opts["relationTypes"])
    assert any(o["value"] == "chief_scientist" for o in opts["roles"])
    assert any(o["value"] == "industry_status" for o in opts["dimensions"])
    assert "人工智能" in opts["techFields"]
    assert "G06N" in opts["cpcCodes"]


def test_get_options_tolerates_data_source_failure(monkeypatch):
    monkeypatch.setattr(
        mod, "get_techkg_client", lambda: (_ for _ in ()).throw(RuntimeError("no graph"))
    )
    monkeypatch.setattr(
        mod, "get_mysql_client", lambda: (_ for _ in ()).throw(RuntimeError("no mysql"))
    )
    opts = mod.get_options()
    assert opts["scholars"] == []
    assert opts["enterprises"] == []
    assert opts["edges"] == []
    # 目录部分仍可用
    assert len(opts["relationTypes"]) == 5
