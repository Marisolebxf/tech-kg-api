"""科技产业链点 TOP-N 事件关系业务端点的集成测试（需真实后端 + dev 图 + MySQL，标 external）。"""

from __future__ import annotations

import pytest

# 真实链节点：集成电路设计（dwd_industry_chain_info 有，dwd_org_industry_chain_dtl 关联企业有事件）
CHAIN_NODE_ID = "IC0007007"


@pytest.mark.external
async def test_describe_returns_business_info(async_client):
    resp = await async_client.get("/api/v1/kg-service/industry-node-top-events")
    assert resp.status_code == 200
    assert resp.json()["business"] == "科技产业链点TOP-N事件关系"


@pytest.mark.external
async def test_run_returns_top_events(async_client):
    resp = await async_client.post(
        "/api/v1/kg-service/industry-node-top-events",
        json={"chain_node_id": CHAIN_NODE_ID, "top_n": 5, "max_orgs": 15},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["chain_node_id"] == CHAIN_NODE_ID
    assert data["chain_node_name"] == "集成电路设计"
    assert data["chain_name"] == "集成电路"
    assert data["enterprises"] >= 1
    assert data["events"] >= 1
    assert data["risk_level"] in {"高", "中", "低"}
    assert len(data["top_events"]) == data["events"]
    # TOP 事件有影响力评分且按降序
    scores = [e["impact_score"] for e in data["top_events"]]
    assert scores == sorted(scores, reverse=True)
    assert data["top_events"][0]["rank"] == 1
