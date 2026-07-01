from __future__ import annotations

from unittest.mock import MagicMock


async def test_mine_endpoint_returns_unified_response(async_client, monkeypatch):
    fake_service = MagicMock()
    fake_service.mine.return_value = {
        "status": "success",
        "scholarId": "007Rb117",
        "scholarName": "吴边",
        "scholarOrg": "中国科学院微生物研究所",
        "profile": {"bio_zh": "...", "researchDirections": []},
        "degraded": False,
        "minedRelations": [],
        "skipped": [],
        "totalMined": 0,
    }
    from biz.handler import expert_enterprise_mining as h

    monkeypatch.setattr(h.application, "_service", fake_service)
    response = await async_client.post(
        "/api/v1/kg-construction/expert-enterprise-mining/mine",
        json={"scholarId": "007Rb117", "topN": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200 and body["success"] is True
    assert body["data"]["scholarName"] == "吴边"
    assert body["msg"] == "success"


async def test_mine_endpoint_404(async_client, monkeypatch):
    fake_service = MagicMock()
    fake_service.mine.side_effect = KeyError("学者不存在: nope")
    from biz.handler import expert_enterprise_mining as h

    monkeypatch.setattr(h.application, "_service", fake_service)
    response = await async_client.post(
        "/api/v1/kg-construction/expert-enterprise-mining/mine",
        json={"scholarId": "nope"},
    )
    body = response.json()
    assert body["code"] == 404 and body["success"] is False


async def test_mine_endpoint_validation_error(async_client):
    response = await async_client.post(
        "/api/v1/kg-construction/expert-enterprise-mining/mine",
        json={"topN": 5},
    )
    assert response.json()["code"] == 422
