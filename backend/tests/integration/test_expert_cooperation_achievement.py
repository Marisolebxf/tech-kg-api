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
@pytest.mark.parametrize("limit", [1, 50])
async def test_query_cooperation_achievement_accepts_limit_boundaries(
    async_client, monkeypatch, limit
):
    received = {}

    def _query(**kwargs):
        received.update(kwargs)
        return {}

    monkeypatch.setattr(handler.application, "query", _query)
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={"sourceExpertId": "S1", "targetExpertId": "S2", "limitPerType": limit},
    )

    assert resp.status_code == 200
    assert received["limit_per_type"] == limit


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 51, -1, 1.5, "20", True, None])
async def test_query_cooperation_achievement_rejects_invalid_limit(async_client, limit):
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={"sourceExpertId": "S1", "targetExpertId": "S2", "limitPerType": limit},
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == 422


@pytest.mark.asyncio
async def test_query_cooperation_achievement_not_found(async_client, monkeypatch):
    def _raise(**kwargs):
        raise KeyError("未找到专家: S404")

    monkeypatch.setattr(handler.application, "query", _raise)
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={"sourceExpertId": "S404", "targetExpertId": "S2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
    assert body["success"] is False
    assert body["data"] is None
    assert body["msg"] == "未找到专家: S404"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["sourceExpertId", "targetExpertId"])
@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("X" * 65, "64"),
        ("person_1!@#￥%&", "异常字符"),
        ("person 1", "空格"),
    ],
)
async def test_query_cooperation_achievement_rejects_invalid_expert_ids(
    async_client, field, value, message
):
    payload = {"sourceExpertId": "S1", "targetExpertId": "S2", field: value}
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query", json=payload
    )
    assert resp.status_code == 422
    assert any(message in error["msg"] for error in resp.json()["data"])


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["timeRangeStart", "timeRangeEnd"])
async def test_query_cooperation_achievement_rejects_future_month(async_client, field):
    payload = {"sourceExpertId": "S1", "targetExpertId": "S2", field: "2999-01"}
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query", json=payload
    )
    assert resp.status_code == 422
    assert any("输入时间不能超过当前时间" in error["msg"] for error in resp.json()["data"])


@pytest.mark.asyncio
async def test_query_cooperation_achievement_rejects_reversed_range(async_client):
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        json={
            "sourceExpertId": "S1",
            "targetExpertId": "S2",
            "timeRangeStart": "2025-02",
            "timeRangeEnd": "2025-01",
        },
    )
    assert resp.status_code == 422
    assert any("开始时间不能晚于结束时间" in error["msg"] for error in resp.json()["data"])
