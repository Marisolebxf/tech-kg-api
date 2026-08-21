from __future__ import annotations

import pytest

from biz.handler import expert_cooperation_achievement as handler


@pytest.mark.asyncio
async def test_describe_cooperation_achievement(async_client):
    resp = await async_client.get("/api/v1/kg-construction/expert-cooperation-achievements")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "expert_cooperation_achievement"
    assert body["status"] == "ready"


@pytest.mark.asyncio
async def test_query_cooperation_achievement_success(async_client, monkeypatch):
    monkeypatch.setattr(
        handler.application,
        "query",
        lambda **kwargs: {
            "source": {"id": "S1", "name": "甲"},
            "target": {"id": "S2", "name": "乙"},
            "summary": {"papers": 1, "patents": 0, "projects": 0, "awards": 0},
            "items": [],
            "coreContribution": "共同论文产出",
            "cooperationMode": "单类型合作（论文）",
            "sourceMeta": {"space": "dev", "graph": "trs-graph", "truncated": False},
        },
    )
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={"sourceExpertId": "S1", "targetExpertId": "S2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["success"] is True
    assert body["data"]["summary"]["papers"] == 1


@pytest.mark.asyncio
async def test_query_cooperation_achievement_not_found(async_client, monkeypatch):
    def _raise(**kwargs):
        raise KeyError("专家不存在: S404")

    monkeypatch.setattr(handler.application, "query", _raise)
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={"sourceExpertId": "S404", "targetExpertId": "S2"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert "专家不存在" in body["detail"]


@pytest.mark.asyncio
async def test_query_cooperation_achievement_rejects_invalid_dates(async_client):
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={
            "sourceExpertId": "S1",
            "targetExpertId": "S2",
            "timeRangeStart": "not-a-date",
            "timeRangeEnd": "also-invalid",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 422
