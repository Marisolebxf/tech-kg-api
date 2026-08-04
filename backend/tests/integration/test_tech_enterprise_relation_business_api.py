"""重点关注科技企业关系业务端点的集成测试（需真实后端 + dev 图，标 external）。"""

from __future__ import annotations

import pytest

# dev 空间里真实存在的专家（左晶，苏州绿的谐波传动科技副董事长）
EXPERT_ZUO = "person_00fdcec8aa4d1ba8554596c3310e36cf"
# 李冰：有项目合作->北京大学（带合作时间）
EXPERT_LIB = "person_940cc7b88047eccfdbbaaa75dd0a90a4"


@pytest.mark.external
async def test_describe_returns_business_info(async_client):
    resp = await async_client.get("/api/v1/kg-service/key-enterprise-relation")
    assert resp.status_code == 200
    assert resp.json()["business"] == "重点关注科技企业关系"


@pytest.mark.external
async def test_run_returns_governance_relation(async_client):
    resp = await async_client.post(
        "/api/v1/kg-service/key-enterprise-relation",
        json={"expert_id": EXPERT_ZUO},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["expert_name"] == "左晶"
    assert data["enterprises"] >= 1
    rel = data["relations"][0]
    assert rel["cooperation_type"] == "governance"
    assert rel["cooperation_mode"] == "高管任职"
    assert rel["role_label"] == "副董事长"
    assert rel["role_level"] == "L1"
    assert "苏州绿的谐波传动科技" in (rel["enterprise_name"] or "")
    assert rel["enterprise_background"]["listing_status"] == "已上市"


@pytest.mark.external
async def test_run_returns_project_cooperation_with_period(async_client):
    """关掉重点企业筛选，验证项目合作的合作时间从 research_period 解出。"""
    resp = await async_client.post(
        "/api/v1/kg-service/key-enterprise-relation",
        json={"expert_id": EXPERT_LIB, "key_tech_enterprise_only": False},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    proj = next(r for r in data["relations"] if r["cooperation_type"] == "project_cooperation")
    assert proj["cooperation_mode"] == "项目合作"
    assert proj["period"]["start"] == "2016-01-01"
    assert proj["period"]["end"] == "2018-12-31"
